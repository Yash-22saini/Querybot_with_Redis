import os, json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from google import genai

from memory import (
    get_or_create_session, create_new_session,
    save_message, get_messages, get_context_window,
    get_cached, set_cached,
    save_summary, get_summary,
    clear_session, get_session_history,
)
from token_tracker import (
    record_usage, get_daily_stats, get_daily_cost,
    get_free_tier_status, get_query_history,
)
from logger import setup_logger

load_dotenv()
logger = setup_logger()

if not os.getenv("GOOGLE_API_KEY"):
    raise RuntimeError("GOOGLE_API_KEY missing from .env")

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

SYSTEM_PROMPT = """You are Nova, a smart, friendly, and concise AI assistant.
Personality: warm, helpful, direct. Never say "As an AI..." or add disclaimers.
- Be concise but complete.
- Use markdown for code and lists when helpful.
- Match the user's tone.
- If you don't know something, say so clearly.
"""

app = FastAPI()

# Serve the HTML file
@app.get("/", response_class=HTMLResponse)
async def home():
    with open("templates/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/api/login")
async def login(request: Request):
    data     = await request.json()
    username = data.get("username", "").strip().lower()
    if not username:
        return JSONResponse({"error": "Username required"}, status_code=400)
    session_id = get_or_create_session(username)
    logger.info(f"LOGIN {username} session={session_id[:8]}")
    return {"username": username, "session_id": session_id}


@app.post("/api/logout")
async def logout(request: Request):
    data       = await request.json()
    username   = data.get("username", "")
    session_id = data.get("session_id", "")
    if username and session_id:
        _save_summary(username, session_id)
        clear_session(username, session_id)
        logger.info(f"LOGOUT {username}")
    return {"ok": True}


@app.post("/api/new_chat")
async def new_chat(request: Request):
    data       = await request.json()
    username   = data.get("username", "")
    session_id = data.get("session_id", "")
    if username and session_id:
        _save_summary(username, session_id)
        new_sid = create_new_session(username)
        logger.info(f"NEW_CHAT {username} new={new_sid[:8]}")
        return {"session_id": new_sid}
    return JSONResponse({"error": "Missing fields"}, status_code=400)


# ── Data ──────────────────────────────────────────────────────────────────────
@app.get("/api/messages/{session_id}")
async def get_msgs(session_id: str):
    return {"messages": get_messages(session_id)}

@app.get("/api/history/{username}")
async def get_hist(username: str):
    return {"history": get_session_history(username)}

@app.get("/api/summary/{username}")
async def get_sum(username: str):
    raw = get_summary(username)
    clean = _clean_summary(raw)
    return {"summary": clean}

@app.get("/api/tokens/{username}")
async def get_tokens(username: str):
    return {
        "free_tier": get_free_tier_status(username),
        "stats":     get_daily_stats(username),
        "cost":      get_daily_cost(username),
        "history":   get_query_history(username)[:10],
    }


# ── Chat stream ───────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(request: Request):
    data       = await request.json()
    user_input = data.get("message", "").strip()
    username   = data.get("username", "")
    session_id = data.get("session_id", "")

    if not user_input:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    # Cache hit
    cached = get_cached(user_input)
    if cached:
        save_message(session_id, "user", user_input)
        save_message(session_id, "Bot",  cached)
        try: record_usage(username, max(1, len(cached)//4), 0, user_input)
        except: pass
        msgs = get_messages(session_id)
        ts   = msgs[-1]["ts"] if msgs else ""

        async def cached_gen():
            payload = json.dumps({"type": "token", "text": cached})
            yield f"data: {payload}\n\n"
            done = json.dumps({"type": "done", "ts": ts, "cached": True})
            yield f"data: {done}\n\n"

        return StreamingResponse(cached_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Save user msg
    save_message(session_id, "user", user_input)
    msgs    = get_messages(session_id)
    user_ts = msgs[-1]["ts"] if msgs else ""
    prompt  = _build_prompt(username, session_id, user_input)
    full    = []

    async def stream_gen():
        try:
            for chunk in client.models.generate_content_stream(
                model="gemini-2.5-flash", contents=prompt
            ):
                if chunk.text:
                    full.append(chunk.text)
                    payload = json.dumps({"type": "token", "text": chunk.text})
                    yield f"data: {payload}\n\n"

            bot_reply = "".join(full).strip() or "Sorry, I couldn't generate a response."
            save_message(session_id, "Bot", bot_reply)
            set_cached(user_input, bot_reply)

            try:
                in_tok  = max(1, len(prompt)    // 4)
                out_tok = max(1, len(bot_reply) // 4)
                record_usage(username, in_tok, out_tok, user_input)
            except: pass

            msgs2  = get_messages(session_id)
            bot_ts = msgs2[-1]["ts"] if msgs2 else ""
            done   = json.dumps({"type": "done", "ts": bot_ts, "user_ts": user_ts, "cached": False})
            yield f"data: {done}\n\n"
            logger.info(f"[{username}] {len(bot_reply)} chars")

        except Exception as e:
            logger.error(f"[{username}] LLM error: {e}")
            err = json.dumps({"type": "error", "text": f"⚠️ Error: {e}"})
            yield f"data: {err}\n\n"

    return StreamingResponse(stream_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Helpers ───────────────────────────────────────────────────────────────────
def _build_prompt(username, session_id, user_input):
    context  = get_context_window(session_id, max_tokens=5000)
    prev_sum = _clean_summary(get_summary(username))
    parts    = [SYSTEM_PROMPT]
    if prev_sum:
        parts.append(f"\n[Memory from previous session]\n{prev_sum}")
    if context:
        parts.append(f"\n[Conversation so far]\n{context}")
    parts.append(f"\nUser: {user_input}\nNova:")
    return "\n".join(parts)


def _clean_summary(raw):
    if not raw:
        return ""
    lines = raw.strip().split("\n")
    clean = "\n".join(
        l for l in lines
        if not l.startswith("===")
        and not l.startswith("Date")
        and not l.startswith("Session")
        and not l.startswith("User")
    ).strip()
    return clean


def _save_summary(username, session_id):
    msgs = get_messages(session_id)
    if not msgs:
        return
    history = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
    try:
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Summarize briefly in plain text. Key topics only.\n\n{history}\n\nSummary:"
        )
        save_summary(username, session_id, res.text.strip())
    except Exception as e:
        logger.error(f"Summary error: {e}")