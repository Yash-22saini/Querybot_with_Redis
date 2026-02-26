import uuid
import hashlib
from datetime import datetime
from redis_client import get_redis
import logging

logger = logging.getLogger(__name__)

TTL          = 3600    # active session: 1 hour
SUMMARY_TTL  = 86400   # summary: 24 hours
CACHE_TTL    = 1800    # response cache: 30 minutes

r = get_redis()


# ── Session ────────────────────────────────────────────────────────────────────
def get_or_create_session(username: str) -> str:
    key = f"user:{username}:session_id"
    sid = r.get(key)
    if not sid:
        sid = str(uuid.uuid4())
        r.setex(key, TTL, sid)
    else:
        r.expire(key, TTL)
    return sid


def create_new_session(username: str) -> str:
    """Force-create a brand new session (New Chat)."""
    old_sid = r.get(f"user:{username}:session_id")
    if old_sid:
        # Archive old session before wiping
        _archive_session(username, old_sid)
    sid = str(uuid.uuid4())
    r.setex(f"user:{username}:session_id", TTL, sid)
    return sid


def _archive_session(username: str, session_id: str):
    """Move session messages to history archive."""
    msgs = get_messages(session_id)
    if not msgs:
        return
    archive_key = f"user:{username}:history"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = {
        "session_id": session_id[:8],
        "date": ts,
        "preview": msgs[0]["content"][:60] + "…" if msgs else "",
        "count": len(msgs),
    }
    import json
    r.lpush(archive_key, json.dumps(entry))
    r.ltrim(archive_key, 0, 19)   # keep last 20 sessions
    r.expire(archive_key, SUMMARY_TTL * 7)
    r.delete(f"session:{session_id}:messages")


def get_session_history(username: str) -> list:
    """Get list of past sessions for sidebar."""
    import json
    raw = r.lrange(f"user:{username}:history", 0, -1)
    result = []
    for item in raw:
        try:
            result.append(json.loads(item))
        except Exception:
            continue
    return result


# ── Messages ───────────────────────────────────────────────────────────────────
def save_message(session_id: str, role: str, content: str):
    key = f"session:{session_id}:messages"
    ts  = datetime.now().strftime("%H:%M")
    r.rpush(key, f"[{ts}] {role}::{content}")
    r.expire(key, TTL)


def get_messages(session_id: str) -> list[dict]:
    raw    = r.lrange(f"session:{session_id}:messages", 0, -1)
    result = []
    for entry in raw:
        try:
            ts_part, rest  = entry.split("] ", 1)
            role, content  = rest.split("::", 1)
            result.append({"role": role, "content": content, "ts": ts_part[1:]})
        except Exception:
            continue
    return result


def get_context_window(session_id: str, max_tokens: int = 6000) -> str:
    """Smart context: fit as many recent messages as possible within token budget."""
    msgs   = get_messages(session_id)
    lines  = []
    tokens = 0
    for m in reversed(msgs):
        # rough estimate: 1 token ≈ 4 chars
        est = len(m["content"]) // 4
        if tokens + est > max_tokens:
            break
        lines.insert(0, f"{m['role']}: {m['content']}")
        tokens += est
    return "\n".join(lines)


# ── Response cache ─────────────────────────────────────────────────────────────
def _cache_key(text: str) -> str:
    return "cache:" + hashlib.sha256(text.strip().lower().encode()).hexdigest()


def get_cached(prompt: str) -> str | None:
    return r.get(_cache_key(prompt))


def set_cached(prompt: str, response: str):
    r.setex(_cache_key(prompt), CACHE_TTL, response)


# ── Summary ────────────────────────────────────────────────────────────────────
def save_summary(username: str, session_id: str, text: str):
    key = f"user:{username}:summary"
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = (
        f"=== Chat Summary ===\n"
        f"Date    : {ts}\n"
        f"Session : {session_id[:8]}...\n"
        f"User    : {username}\n\n"
        f"{text}\n"
    )
    r.setex(key, SUMMARY_TTL, block)
    logger.info(f"Summary saved for user={username} session={session_id[:8]}")


def get_summary(username: str) -> str:
    return r.get(f"user:{username}:summary") or ""


# ── Cleanup ────────────────────────────────────────────────────────────────────
def clear_session(username: str, session_id: str):
    r.delete(f"session:{session_id}:messages")
    r.delete(f"user:{username}:session_id")
    logger.info(f"Session cleared user={username} session={session_id[:8]}")