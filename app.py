import streamlit as st
import os
import time
from dotenv import load_dotenv
from google import genai

from logger import setup_logger
from memory import (
    get_or_create_session, create_new_session,
    save_message, get_messages, get_context_window,
    get_cached, set_cached,
    save_summary, get_summary,
    clear_session, get_session_history,
)

# ── Init ───────────────────────────────────────────────────────────────────────
load_dotenv()
logger = setup_logger()

# Validate env
if not os.getenv("GOOGLE_API_KEY"):
    st.error("❌ GOOGLE_API_KEY is missing from your .env file.")
    st.stop()

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

SYSTEM_PROMPT = """You are Nova, a smart, friendly, and concise AI assistant.
Your personality: warm, helpful, direct. You never say "As an AI..." or add unnecessary disclaimers.
Rules:
- Be concise but complete. Don't pad responses.
- Use markdown for code, lists, and structure when it helps.
- If you don't know something, say so clearly.
- Match the user's tone — casual if they're casual, formal if they're formal.
"""

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Nova · AI Chat",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"] {
    background: #0a0a0a !important;
    color: #e8e8e8 !important;
    font-family: 'Sora', sans-serif !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display: none !important; }

[data-testid="stAppViewContainer"] > .main { padding: 0 !important; }

.block-container {
    max-width: 820px !important;
    margin: 0 auto !important;
    padding: 0 28px 140px !important;
}

/* ══ SIDEBAR ══ */
[data-testid="stSidebar"] {
    background: #0f0f0f !important;
    border-right: 1px solid #1c1c1c !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] > div { padding: 0 !important; }

.sb-header {
    padding: 20px 16px 12px;
    border-bottom: 1px solid #1c1c1c;
    display: flex; align-items: center; gap: 10px;
}
.sb-logo {
    width: 28px; height: 28px;
    background: #fff; border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem; font-weight: 700; color: #000; flex-shrink: 0;
}
.sb-title { font-size: 0.95rem; font-weight: 600; color: #fff; }

.sb-section-label {
    font-size: 0.65rem;
    color: #444;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    padding: 16px 16px 6px;
    font-family: 'JetBrains Mono', monospace;
}

.history-item {
    padding: 10px 16px;
    border-radius: 8px;
    margin: 2px 8px;
    cursor: pointer;
    transition: background 0.15s;
    border: 1px solid transparent;
}
.history-item:hover { background: #161616; border-color: #232323; }
.history-item.active { background: #161616; border-color: #2a2a2a; }
.history-date { font-size: 0.65rem; color: #444; font-family: 'JetBrains Mono', monospace; }
.history-preview { font-size: 0.8rem; color: #aaa; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.sb-user-row {
    position: absolute; bottom: 0; left: 0; right: 0;
    padding: 14px 16px;
    border-top: 1px solid #1c1c1c;
    background: #0f0f0f;
    display: flex; align-items: center; gap: 10px;
}
.sb-avatar {
    width: 30px; height: 30px;
    background: #222; border: 1px solid #333;
    border-radius: 8px; display: flex; align-items: center;
    justify-content: center; font-size: 0.8rem; font-weight: 600;
    color: #e0e0e0; flex-shrink: 0;
}
.sb-uname { font-size: 0.82rem; color: #aaa; flex: 1; }
.sb-session { font-size: 0.65rem; color: #444; font-family: 'JetBrains Mono', monospace; }

/* ══ TOP BAR ══ */
.topbar {
    position: sticky; top: 0; z-index: 100;
    background: #0a0a0a;
    border-bottom: 1px solid #181818;
    padding: 12px 0 10px;
    margin-bottom: 4px;
}
.topbar-inner {
    display: flex; align-items: center; justify-content: space-between;
}
.topbar-name { font-size: 0.95rem; font-weight: 600; color: #fff; }
.topbar-meta { font-size: 0.72rem; color: #444; font-family: 'JetBrains Mono', monospace; }

/* ══ MESSAGES ══ */
.msg-row {
    display: flex; gap: 14px;
    padding: 20px 0;
    border-bottom: 1px solid #141414;
    animation: msgIn 0.2s ease;
    position: relative;
}
@keyframes msgIn {
    from { opacity: 0; transform: translateY(5px); }
    to   { opacity: 1; transform: translateY(0); }
}
.msg-row:last-child { border-bottom: none; }

.msg-avatar {
    width: 32px; height: 32px;
    border-radius: 8px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem; font-weight: 600; margin-top: 1px;
}
.av-user { background: #1e1e1e; color: #e0e0e0; border: 1px solid #2a2a2a; }
.av-bot  { background: #fff; color: #000; }

.msg-body { flex: 1; min-width: 0; }
.msg-name {
    font-size: 0.72rem; font-weight: 600; color: #555;
    text-transform: uppercase; letter-spacing: 0.6px;
    font-family: 'JetBrains Mono', monospace; margin-bottom: 5px;
}
.msg-text {
    font-size: 0.92rem; line-height: 1.7;
    color: #ddd; white-space: pre-wrap; word-break: break-word;
}
.msg-text code {
    background: #161616; border: 1px solid #252525;
    border-radius: 4px; padding: 1px 5px;
    font-family: 'JetBrains Mono', monospace; font-size: 0.83rem; color: #a78bfa;
}
.msg-text pre {
    background: #111; border: 1px solid #222;
    border-radius: 10px; padding: 14px 16px; overflow-x: auto; margin: 10px 0;
}
.msg-text pre code { background: none; border: none; padding: 0; color: #c9d1d9; }
.msg-footer {
    display: flex; align-items: center; gap: 12px; margin-top: 7px;
}
.msg-ts { font-size: 0.66rem; color: #333; font-family: 'JetBrains Mono', monospace; }
.copy-btn {
    font-size: 0.66rem; color: #333; cursor: pointer;
    padding: 2px 7px; border: 1px solid #222; border-radius: 4px;
    background: transparent; transition: color 0.15s, border-color 0.15s;
    font-family: 'JetBrains Mono', monospace;
}
.copy-btn:hover { color: #888; border-color: #444; }
.cached-badge {
    font-size: 0.63rem; color: #444;
    background: #141414; border: 1px solid #222;
    padding: 1px 6px; border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
}

/* ══ TYPING INDICATOR ══ */
.typing-row {
    display: flex; gap: 14px; padding: 18px 0;
    animation: msgIn 0.2s ease;
}
.typing-dots {
    display: flex; align-items: center; gap: 5px;
    height: 20px; padding-top: 4px;
}
.typing-dots span {
    width: 7px; height: 7px;
    background: #444; border-radius: 50%;
    animation: dot-bounce 1.3s infinite ease-in-out;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-bounce {
    0%, 80%, 100% { transform: translateY(0); background: #333; }
    40%            { transform: translateY(-6px); background: #666; }
}

/* ══ WELCOME ══ */
.welcome-wrap {
    text-align: center; padding: 70px 20px 40px;
}
.welcome-icon { font-size: 2.8rem; margin-bottom: 12px; }
.welcome-h { font-size: 1.7rem; font-weight: 600; color: #fff; letter-spacing: -0.4px; }
.welcome-s { font-size: 0.88rem; color: #555; margin-top: 6px; margin-bottom: 32px; }

.cards {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 10px; max-width: 500px; margin: 0 auto;
}
.card {
    background: #111; border: 1px solid #1e1e1e;
    border-radius: 12px; padding: 14px 16px;
    text-align: left; transition: border-color 0.2s, background 0.15s;
    cursor: default;
}
.card:hover { border-color: #333; background: #161616; }
.card-t { font-size: 0.82rem; font-weight: 500; color: #ccc; margin-bottom: 3px; }
.card-s { font-size: 0.75rem; color: #555; }

/* ══ SUMMARY BOX ══ */
.sum-box {
    background: #0e0e0e; border: 1px solid #1c1c1c;
    border-left: 3px solid #2a2a2a; border-radius: 10px;
    padding: 14px 18px; margin: 8px 0 20px;
    font-size: 0.8rem; color: #555; line-height: 1.65;
    font-family: 'JetBrains Mono', monospace;
}
.sum-label {
    font-size: 0.63rem; color: #383838;
    text-transform: uppercase; letter-spacing: 1px; margin-bottom: 7px;
}

/* ══ INPUT ══ */
[data-testid="stChatInput"] {
    position: fixed !important; bottom: 0 !important;
    left: 50% !important; transform: translateX(-50%) !important;
    width: calc(100% - 280px) !important; max-width: 820px !important;
    padding: 14px 28px 18px !important;
    background: #0a0a0a !important; border-top: 1px solid #181818 !important;
    z-index: 999 !important;
}
[data-testid="stChatInputTextArea"] {
    background: #111 !important; border: 1px solid #252525 !important;
    border-radius: 12px !important; color: #e8e8e8 !important;
    font-family: 'Sora', sans-serif !important; font-size: 0.92rem !important;
    padding: 13px 16px !important; resize: none !important;
}
[data-testid="stChatInputTextArea"]:focus {
    border-color: #3a3a3a !important; box-shadow: none !important; outline: none !important;
}
[data-testid="stChatInputTextArea"]::placeholder { color: #3a3a3a !important; }
[data-testid="stChatInputSubmitButton"] button {
    background: #fff !important; border-radius: 8px !important;
    border: none !important; color: #000 !important;
    width: 34px !important; height: 34px !important; transition: opacity 0.2s !important;
}
[data-testid="stChatInputSubmitButton"] button:hover { opacity: 0.8 !important; }

/* ══ BUTTONS ══ */
div.stButton > button {
    background: #111 !important; color: #ccc !important;
    border: 1px solid #222 !important; border-radius: 9px !important;
    font-family: 'Sora', sans-serif !important; font-size: 0.82rem !important;
    font-weight: 500 !important; padding: 7px 14px !important;
    transition: border-color 0.15s, background 0.15s !important;
    width: 100% !important;
}
div.stButton > button:hover { background: #161616 !important; border-color: #333 !important; }
div.stButton > button[kind="primary"] {
    background: #fff !important; color: #000 !important; border-color: #fff !important;
}
div.stButton > button[kind="primary"]:hover { background: #e8e8e8 !important; }

/* ══ TEXT INPUT ══ */
[data-testid="stTextInput"] input {
    background: #111 !important; border: 1px solid #252525 !important;
    border-radius: 10px !important; color: #e8e8e8 !important;
    font-family: 'Sora', sans-serif !important; font-size: 0.9rem !important;
    padding: 12px 14px !important;
}
[data-testid="stTextInput"] input:focus { border-color: #444 !important; box-shadow: none !important; }
[data-testid="stTextInput"] input::placeholder { color: #3a3a3a !important; }

/* ══ LOGIN ══ */
.login-wrap {
    min-height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 10px; padding: 40px 20px;
}
.login-logo { font-size: 2.8rem; }
.login-h { font-size: 1.9rem; font-weight: 600; color: #fff; letter-spacing: -0.5px; margin: 0; }
.login-s { font-size: 0.87rem; color: #555; margin-bottom: 20px; }

/* ══ SCROLLBAR ══ */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #1e1e1e; border-radius: 2px; }

/* ══ SIDEBAR EXPANDER ══ */
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: #111 !important;
    border: 1px solid #1e1e1e !important;
    border-radius: 10px !important;
    margin: 3px 8px !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    font-size: 0.78rem !important;
    color: #aaa !important;
    font-family: 'Sora', sans-serif !important;
    padding: 8px 12px !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
    color: #fff !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] > div > div {
    padding: 6px 12px 12px !important;
    font-size: 0.8rem !important;
    color: #777 !important;
    line-height: 1.6 !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] p {
    color: #888 !important;
    font-size: 0.78rem !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] em {
    color: #666 !important;
    font-style: italic !important;
}

</style>

<script>
function copyText(id) {
    const el = document.getElementById(id);
    if (el) {
        navigator.clipboard.writeText(el.innerText).then(() => {
            const btn = el.closest('.msg-row').querySelector('.copy-btn');
            if (btn) { btn.innerText = 'copied!'; setTimeout(() => btn.innerText = 'copy', 1500); }
        });
    }
}
</script>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def build_prompt(username: str, session_id: str, user_input: str) -> str:
    context  = get_context_window(session_id, max_tokens=5000)
    prev_sum = get_summary(username)
    parts    = [SYSTEM_PROMPT]
    if prev_sum:
        parts.append(f"\n[Previous session context]\n{prev_sum}")
    if context:
        parts.append(f"\n[Conversation so far]\n{context}")
    parts.append(f"\nUser: {user_input}\nNova:")
    return "\n".join(parts)


def generate_summary(username: str, session_id: str):
    msgs = get_messages(session_id)
    if not msgs:
        return
    history = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
    prompt  = (
        "Summarize this chat in plain text. Be concise. Capture key topics only.\n\n"
        f"Conversation:\n{history}\n\nSummary only:"
    )
    try:
        res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        save_summary(username, session_id, res.text.strip())
        logger.info(f"Summary generated for {username}")
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")


def do_logout():
    u = st.session_state.get("username")
    s = st.session_state.get("session_id")
    if u and s:
        generate_summary(u, s)
        clear_session(u, s)
        logger.info(f"User {u} logged out")
    for k in ["username", "session_id", "messages"]:
        st.session_state.pop(k, None)


def do_new_chat():
    u = st.session_state.get("username")
    s = st.session_state.get("session_id")
    if u and s:
        generate_summary(u, s)
        new_sid = create_new_session(u)
        st.session_state.session_id = new_sid
        st.session_state.messages   = []
        logger.info(f"New chat started for {u}")


def render_msg(role: str, content: str, ts: str = "", username: str = "", cached: bool = False, idx: int = 0):
    is_user      = role == "user"
    avatar_class = "av-user" if is_user else "av-bot"
    avatar_text  = (username[0].upper() if username else "U") if is_user else "✦"
    name_label   = (username or "You") if is_user else "Nova"
    msg_id       = f"msg-{idx}"

    cached_html = '<span class="cached-badge">⚡ cached</span>' if cached else ""
    copy_html   = "" if is_user else f'<button class="copy-btn" onclick="copyText(\'{msg_id}\')">copy</button>'
    ts_html     = f'<span class="msg-ts">{ts}</span>' if ts else ""

    st.markdown(f"""
    <div class="msg-row">
        <div class="msg-avatar {avatar_class}">{avatar_text}</div>
        <div class="msg-body">
            <div class="msg-name">{name_label}</div>
            <div class="msg-text" id="{msg_id}">{content}</div>
            <div class="msg-footer">{ts_html}{copy_html}{cached_html}</div>
        </div>
    </div>""", unsafe_allow_html=True)


def render_typing():
    st.markdown("""
    <div class="typing-row">
        <div class="msg-avatar av-bot">✦</div>
        <div class="msg-body">
            <div class="msg-name">Nova</div>
            <div class="typing-dots"><span></span><span></span><span></span></div>
        </div>
    </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════
if "username" not in st.session_state:
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="login-logo">✦</div>', unsafe_allow_html=True)
    st.markdown('<p class="login-h">Nova</p>', unsafe_allow_html=True)
    st.markdown('<p class="login-s">Your intelligent assistant — enter a username to continue</p>', unsafe_allow_html=True)

    name = st.text_input("Username", placeholder="Enter your username…",
                         label_visibility="collapsed", max_chars=30)
    _, c, _ = st.columns([1, 2, 1])
    with c:
        if st.button("Continue →", use_container_width=True, type="primary"):
            if name.strip():
                uname = name.strip().lower()
                sid   = get_or_create_session(uname)
                st.session_state.username   = uname
                st.session_state.session_id = sid
                st.session_state.messages   = []
                logger.info(f"User {uname} logged in, session={sid[:8]}")
                st.rerun()
            else:
                st.warning("Please enter a username.")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
username   = st.session_state.username
session_id = st.session_state.session_id

with st.sidebar:
    st.markdown(f"""
    <div class="sb-header">
        <div class="sb-logo">✦</div>
        <span class="sb-title">Nova</span>
    </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("✦  New Chat", use_container_width=True):
        do_new_chat()
        st.rerun()

    # Past sessions
    history = get_session_history(username)
    if history:
        st.markdown('<div class="sb-section-label">Recent chats</div>', unsafe_allow_html=True)
        for i, item in enumerate(history):
            label = f"💬 {item['date']} · {item['count']} msgs"
            with st.expander(label, expanded=False):
                st.markdown(f"**Started:** {item['date']}")
                st.markdown(f"**Messages:** {item['count']}")
                st.caption(f"Session: {item['session_id']}")
                if i == 0:
                    raw_sum = get_summary(username)
                    if raw_sum:
                        lines = raw_sum.strip().split("\n")
                        clean = "\n".join(
                            l for l in lines
                            if not l.startswith("===")
                            and not l.startswith("Date")
                            and not l.startswith("Session")
                            and not l.startswith("User")
                        ).strip()
                        if clean:
                            st.markdown("**Summary:**")
                            st.markdown(f"_{clean}_")

    # User info at bottom
    st.markdown(f"""
    <div class="sb-user-row">
        <div class="sb-avatar">{username[0].upper()}</div>
        <div>
            <div class="sb-uname">{username}</div>
            <div class="sb-session">{session_id[:8]}…</div>
        </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:60px'></div>", unsafe_allow_html=True)

    if st.button("Logout", use_container_width=True):
        do_logout()
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CHAT
# ══════════════════════════════════════════════════════════════════════════════

# Restore messages from Redis on first load
if not st.session_state.messages:
    for m in get_messages(session_id):
        st.session_state.messages.append(m)

# Top bar
st.markdown(f"""
<div class="topbar">
    <div class="topbar-inner">
        <span class="topbar-name">Nova</span>
        <span class="topbar-meta">{username} · {session_id[:8]}…</span>
    </div>
</div>""", unsafe_allow_html=True)

# Summary is shown in sidebar only — not on main screen

# Welcome screen
if not st.session_state.messages:
    st.markdown(f"""
    <div class="welcome-wrap">
        <div class="welcome-icon">✦</div>
        <div class="welcome-h">Hello, {username.capitalize()}!</div>
        <div class="welcome-s">I'm Nova — how can I help you today?</div>
        <div class="cards">
            <div class="card"><div class="card-t">Explain a concept</div><div class="card-s">Break down complex topics simply</div></div>
            <div class="card"><div class="card-t">Write something</div><div class="card-s">Emails, essays, code & more</div></div>
            <div class="card"><div class="card-t">Brainstorm ideas</div><div class="card-s">Get creative help fast</div></div>
            <div class="card"><div class="card-t">Solve a problem</div><div class="card-s">Step-by-step guidance</div></div>
        </div>
    </div>""", unsafe_allow_html=True)

# Render all messages
for i, msg in enumerate(st.session_state.messages):
    render_msg(msg["role"], msg["content"], msg.get("ts",""), username, msg.get("cached", False), i)

# Chat input
user_input = st.chat_input("Message Nova…")

if user_input:
    user_input = user_input.strip()
    logger.info(f"[{username}] User: {user_input[:80]}")

    # Save + render user message
    save_message(session_id, "user", user_input)
    msgs = get_messages(session_id)
    ts   = msgs[-1]["ts"] if msgs else ""
    idx  = len(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": user_input, "ts": ts})
    render_msg("user", user_input, ts, username, False, idx)

    # Check cache
    cached_reply = get_cached(user_input)
    if cached_reply:
        logger.info(f"[{username}] Cache HIT for: {user_input[:60]}")
        save_message(session_id, "Bot", cached_reply)
        msgs = get_messages(session_id)
        ts2  = msgs[-1]["ts"] if msgs else ""
        idx2 = len(st.session_state.messages)
        st.session_state.messages.append({"role": "Bot", "content": cached_reply, "ts": ts2, "cached": True})
        render_msg("Bot", cached_reply, ts2, username, True, idx2)
        st.rerun()

    # Typing indicator + streaming
    typing_placeholder = st.empty()
    with typing_placeholder:
        render_typing()

    # Stream response
    prompt     = build_prompt(username, session_id, user_input)
    bot_reply  = ""
    stream_ph  = st.empty()

    try:
        # Use streaming
        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash",
            contents=prompt,
        ):
            typing_placeholder.empty()
            if chunk.text:
                bot_reply += chunk.text
                # Stream into placeholder word by word
                stream_ph.markdown(f"""
                <div class="msg-row">
                    <div class="msg-avatar av-bot">✦</div>
                    <div class="msg-body">
                        <div class="msg-name">Nova</div>
                        <div class="msg-text">{bot_reply}▌</div>
                    </div>
                </div>""", unsafe_allow_html=True)

        # Final render without cursor
        stream_ph.empty()
        bot_reply = bot_reply.strip() or "Sorry, I couldn't generate a response."
        logger.info(f"[{username}] Nova replied ({len(bot_reply)} chars)")

    except Exception as e:
        typing_placeholder.empty()
        stream_ph.empty()
        bot_reply = f"⚠️ Error: {str(e)}"
        logger.error(f"[{username}] LLM error: {e}")

    # Save + cache
    save_message(session_id, "Bot", bot_reply)
    set_cached(user_input, bot_reply)
    msgs = get_messages(session_id)
    ts2  = msgs[-1]["ts"] if msgs else ""
    idx2 = len(st.session_state.messages)
    st.session_state.messages.append({"role": "Bot", "content": bot_reply, "ts": ts2, "cached": False})

    st.rerun()