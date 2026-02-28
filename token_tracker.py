"""
Token tracking for Gemini API usage.
Stores per-query and daily stats in Redis.

Gemini 2.5 Flash Free Tier (as of 2025):
  RPD : 20 requests / day
  RPM : 2  requests / minute
  TPM : 250,000 tokens / minute

Paid pricing:
  Input  : $0.15 / 1M tokens
  Output : $0.60 / 1M tokens
"""

import json
import hashlib
from datetime import datetime, timezone
from redis_client import get_redis
import logging

logger = logging.getLogger(__name__)
r = get_redis()

# ── Free Tier Limits ───────────────────────────────────────────────────────────
FREE_RPD = 20
FREE_RPM = 2
FREE_TPM = 250_000

# Paid pricing per 1M tokens
PRICE_INPUT_PER_M  = 0.15
PRICE_OUTPUT_PER_M = 0.60

# TTLs
DAY_TTL = 86400
MIN_TTL = 120


def _today()   -> str: return datetime.now(timezone.utc).strftime("%Y-%m-%d")
def _minute()  -> str: return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M")
def _day_key(u: str)  -> str: return f"tokens:{u}:day:{_today()}"
def _min_key(u: str)  -> str: return f"tokens:{u}:min:{_minute()}"
def _hist_key(u: str) -> str: return f"tokens:{u}:history"


def record_usage(username: str, input_tokens: int, output_tokens: int, query_preview: str = ""):
    """Record token usage for one API call."""
    total = input_tokens + output_tokens
    ts    = datetime.now(timezone.utc).strftime("%H:%M:%S")

    pipe = r.pipeline()

    # Daily totals
    dk = _day_key(username)
    pipe.hincrby(dk, "input_tokens",  input_tokens)
    pipe.hincrby(dk, "output_tokens", output_tokens)
    pipe.hincrby(dk, "total_tokens",  total)
    pipe.hincrby(dk, "requests",      1)
    pipe.expire(dk, DAY_TTL)

    # Per-minute request counter
    mk = _min_key(username)
    pipe.incr(mk)
    pipe.expire(mk, MIN_TTL)

    pipe.execute()

    # Per-query history (last 50)
    entry = json.dumps({
        "ts":      ts,
        "input":   input_tokens,
        "output":  output_tokens,
        "total":   total,
        "preview": query_preview[:60] + ("…" if len(query_preview) > 60 else ""),
    })
    hk = _hist_key(username)
    r.lpush(hk, entry)
    r.ltrim(hk, 0, 49)
    r.expire(hk, DAY_TTL)

    logger.info(f"[{username}] tokens in:{input_tokens} out:{output_tokens} total:{total}")


def get_daily_stats(username: str) -> dict:
    data = r.hgetall(_day_key(username))
    return {
        "input_tokens":  int(data.get("input_tokens",  0)),
        "output_tokens": int(data.get("output_tokens", 0)),
        "total_tokens":  int(data.get("total_tokens",  0)),
        "requests":      int(data.get("requests",      0)),
    }


def get_rpm(username: str) -> int:
    return int(r.get(_min_key(username)) or 0)


def get_query_history(username: str) -> list:
    raw = r.lrange(_hist_key(username), 0, -1)
    result = []
    for item in raw:
        try:
            result.append(json.loads(item))
        except Exception:
            continue
    return result


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens  / 1_000_000) * PRICE_INPUT_PER_M +
        (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_M,
        6
    )


def get_daily_cost(username: str) -> float:
    s = get_daily_stats(username)
    return estimate_cost(s["input_tokens"], s["output_tokens"])


def get_free_tier_status(username: str) -> dict:
    stats   = get_daily_stats(username)
    rpm_now = get_rpm(username)
    reqs    = stats["requests"]
    rpd_left = max(0, FREE_RPD - reqs)

    return {
        "rpd_used":     reqs,
        "rpd_left":     rpd_left,
        "rpd_limit":    FREE_RPD,
        "rpd_pct":      min(100, round((reqs    / FREE_RPD) * 100)),
        "rpm_now":      rpm_now,
        "rpm_limit":    FREE_RPM,
        "rpm_pct":      min(100, round((rpm_now / FREE_RPM) * 100)),
        "tpm_limit":    FREE_TPM,
        "is_exhausted": reqs >= FREE_RPD,
    }