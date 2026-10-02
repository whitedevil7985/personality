import os
import random
import asyncio
import time
import html
import re
from collections import deque
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from protected_bot import ProtectedBot
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, WebAppInfo,
    BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault, BotCommandScopeChat,
)
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ChatMemberHandler, ContextTypes, filters
from telegram.request import HTTPXRequest

from config import (
    TOKEN, OWNER_ID, DEVELOPER_NAME, OWNER_PROFILE_URL, UPDATES_URL, SUPPORT_URL, AI_GROUP_MODE, AI_GROUP_REPLY_ALL, AI_DM_MODE,
    AI_DISCLOSURE, AI_MODEL, ELITE_LLM_API_KEY, ELITE_LLM_BASE_URL, ELITE_LLM_MODEL, CHATGP_API_KEY, CHATGP_API_URL, CHATGP_TIMEOUT_SECONDS, MAX_HISTORY, MEMORY_ENABLED, MAX_MEMORY,
    MEMORY_DAYS, SUDO_IDS, LOGGER_CHAT_ID
)
from db import ensure_user, mark_started, track_group, get_user, add_coins, add_xp, top_users, users, groups, games, get_game_leaderboard, save_custom_emoji, get_custom_emoji_map

# ───────────────────── modular games ─────────────────────
from games.rps import rps, rps_cb, RPS_GAMES
from games.dice import dice
from games.coinflip import coinflip
from games.slots import slots
from games.card import card, cardjoin, cardstart, cardcancel, card_cb, CARD_ROOMS
from games.jumble import jumble
from games.tap import tap, tap_cb
from games.bet import bet
from games.uno import uno as uno_legacy, unojoin, uno_cb, uno_games
from games.ludo import ludo as ludo_legacy, ludojoin, ludo_cb, ludo_games
from games.chess import chess_cmd, chessjoin, chess_cb, chess_games
from games.mines import mines, mines_cb
from games.wordseek import wordseek, answer as wordseek_answer, reveal_wordseek, WORDSEEK_GAMES
from games.wordgrid import wordgrid, wordgrid_answer, send_wordgrid, reveal_wordgrid
from games.crash import crash
from games.charades import charades
from games.wordchain import wordchain, wordchain_join, wordchain_answer, WORDCHAIN_GAMES
from games.wordscramble import wordscramble, wordscramble_answer, WORDSCRAMBLE_GAMES
from games.hack import hack
from games.scribble import scribble
from games.kingdomwars import kingdomwars
from features import spin, achievements, quest, progress_quest
from handlers.blacklist import blacklist, unblacklist, blacklist_message_guard, blacklist_callback_guard
from webserver import start_web_server

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add BOT_TOKEN in Railway → Service → Variables "
        "(or create a local .env file for local development)."
    )

# ╔══════════════════════════════════════════════════════════════╗
# ║                        VANYA UI                             ║
# ╚══════════════════════════════════════════════════════════════╝

async def category(update, context, name):
    title, lines = CATEGORIES[name]
    body = title + "\n\n" + "\n".join(lines)
    await update.message.reply_html(body, reply_markup=category_kb(name))

def category_kb(name):
    if name == "games":
        return game_menu_kb()
    if name == "chat":
        return kb([
            [InlineKeyboardButton("💬 Start Chat", callback_data="chat:start")],
            [InlineKeyboardButton("👤 My Profile", callback_data="profile:view")],
            [InlineKeyboardButton("⬅️ Back to categories", callback_data="help")],
        ])
    return kb([[InlineKeyboardButton("⬅️ Back to categories", callback_data="help")]])

async def help_cmd(update, context):
    await ensure_user(update.effective_user)
    await update.message.reply_html(
        "✨ <b>Vanya help menu</b> ✨\n\n"
        "<i>Pick a category below to see my commands.</i> 💜\n\n"
        "💬 <b>or just DM me — or say \"Vanya\" in a group — to chat anytime!</b>",
        reply_markup=help_menu_kb()
    )

def help_menu_kb():
    return kb([
        [InlineKeyboardButton("💬 Chat with me", callback_data="cat:chat")],
        [InlineKeyboardButton("💰 Economy", callback_data="cat:economy"),
         InlineKeyboardButton("🗡 Actions", callback_data="cat:actions")],
        [InlineKeyboardButton("💕 Romance", callback_data="cat:romance"),
         InlineKeyboardButton("🎮 Games", callback_data="cat:games")],
        [developer_button()],
        [InlineKeyboardButton("⟵ Back to start", callback_data="startmenu")],
    ])



# ───────────────────── games menu ─────────────────────

GAME_ITEMS = [
    ("🃏 UNO","UNO"), ("💎 Mines","MINES"), ("🪨 RPS","RPS"), ("🔎 Wordseek","WORDSEEK"),
    ("🔤 Wordgrid","WORDGRID"), ("⚡ Tap","TAP"), ("💥 Crash","CRASH"), ("🐙 Jumble","JUMBLE"),
    ("🎭 Charades","CHARADES"), ("🔗 Wordchain","WORDCHAIN"), ("🔤 Wordscramble","WORDS"),
    ("💣 Hack","HACK"), ("🃏 Card","CARD"), ("♟ Chess","CHESS"), ("🖌 Scribble","SCRIBBLE"),
    ("🎰 Bet","BET"), ("🎲 Ludo","LUDO"), ("🎯 Dice","DICE"), ("🪙 Coinflip","COIN"), ("🎰 Slots","SLOTS"), ("🏰 Kingdom Wars","KINGDOMWARS"), ("🚇 Subway","SUBWAY"),
]

GAME_INFO = {
    "UNO": "/uno — Create an UNO room\n/unojoin — Join the latest room.",
    "MINES": "/mines — Start a 5×5 Mines room. Tap safe tiles and cash out.",
    "RPS": "/rps rock|paper|scissors — Challenge Vanya.",
    "WORDSEEK": "/wordseek — Find the hidden word.",
    "WORDGRID": "/wordgrid — Generate an 8×8 word grid.",
    "TAP": "/tap — Reaction-speed challenge.",
    "CRASH": "/crash &lt;amount&gt; — Virtual-coin multiplier game.",
    "JUMBLE": "/jumble — Unscramble the shown word.",
    "CHARADES": "/charades — Get a random charade prompt.",
    "WORDCHAIN": "/wordchain [5-50] — Start Wordchain; minimum 2 players. /wordchainjoin — Join.",
    "WORDS": "/wordscramble — Unscramble a word.",
    "HACK": "/hack — Fictional puzzle mini-game.",
    "CARD": "/card — Create a 2–4 player Card Match; cards are dealt by DM and played in the group for 4 rounds.",
    "CHESS": "/chess — Create a chess room\n/chessjoin — Join.",
    "SCRIBBLE": "/scribble — Open the social scribble room.",
    "BET": "/bet &lt;amount&gt; — Simple virtual-coin wager.",
    "LUDO": "/ludo — Create a Ludo room\n/ludojoin — Join.",
    "DICE": "/dice — Roll a dice.",
    "COIN": "/coinflip — Flip a coin.",
    "SLOTS": "/slots — Spin the slot machine.",
    "KINGDOMWARS": "/kingdomwars — Open a live 2–6 player strategy room. Build, recruit, fortify and conquer.",
    "STREETRUSH": "/subway — Open the live Subway endless runner. Switch lanes, jump, slide and collect coins.",
}

def game_menu_kb():
    rows=[]
    for i in range(0, len(GAME_ITEMS), 2):
        rows.append([InlineKeyboardButton(label, callback_data=f"game:{key}") for label,key in GAME_ITEMS[i:i+2]])
    rows.append([InlineKeyboardButton("⟵  Back to categories", callback_data="help")])
    return kb(rows)

async def street_rush_cmd(update, context):
    domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "personality-production-6405.up.railway.app").strip().strip("/")
    webapp_url = (os.getenv("STREET_RUSH_WEBAPP_URL") or "").strip().strip('"').strip("'")
    if not webapp_url and domain:
        webapp_url = "https://" + domain + "/street-rush"
    if not webapp_url:
        await update.message.reply_text("🏃 Street Rush web app is not configured.")
        return
    if not webapp_url.startswith(("https://","http://")):
        webapp_url = "https://" + webapp_url
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏃 Play Street Rush", url=webapp_url)]])
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏃 Play Street Rush", web_app=WebAppInfo(url=webapp_url))]])
    await update.message.reply_html(
        "🏃 <b>Vanya Street Rush</b>\n\nRun, dodge, jump, slide and collect coins.",
        reply_markup=markup
    )

async def games_cmd(update, context):
    await update.message.reply_html(
        "🎮 <b>Vanya Game Arena</b> 🎮\n\n"
        "<i>Pick a game. Every game is now maintained as its own module.</i> ✨",
        reply_markup=game_menu_kb()
    )

async def game_info(update, context, key):
    text = GAME_INFO.get(key, "Game coming soon.")
    body = f"🎯 <b>How to play</b>\n{text}\n\n💬 <b>Game Chat</b> is available from the arena screen."
    msg, markup = game_room_ui(key, body)
    await update.message.reply_html(msg, reply_markup=markup)

# ───────────────────── economy ─────────────────────

async def kill(update, context):
    target = await target_user(update)
    if not target or target.id == update.effective_user.id:
        await update.message.reply_text("Reply to another player: /kill")
        return

    await ensure_user(update.effective_user)
    await ensure_user(target)
    me = await get_user(update.effective_user.id)
    victim = await get_user(target.id)

    if _is_dead(me):
        await update.message.reply_text("💀 You're dead. Use /revive first.")
        return

    protected_until = _protection_until(victim)
    if protected_until:
        await update.message.reply_text("🛡️ Target is protected. You can't kill them right now.")
        return

    if _is_dead(victim):
        await update.message.reply_text("💀 This player is already dead. They must use /revive first.")
        return

    reward = random.randint(50, 100)
    await users.update_one(
        {"_id": target.id},
        {"$set": {"dead": True, "protected_until": None}},
        upsert=True,
    )
    await add_coins(update.effective_user.id, reward)
    await users.update_one(
        {"_id": update.effective_user.id},
        {"$inc": {"kills": 1}},
    )
    await update.message.reply_html(
        f"☠️ <b>{html.escape(target.first_name or 'Player')}</b> has been killed!\n"
        f"💰 Killer reward: <b>+{reward:,} coins</b>\n"
        "💀 Target status: <b>DEAD</b>\n"
        "❤️ They need <code>/revive</code> to return."
    )

async def revive(update, context):
    await ensure_user(update.effective_user)
    me = await get_user(update.effective_user.id)

    if not _is_dead(me):
        await update.message.reply_text("🟢 You're already alive.")
        return

    revive_cost = 500
    if int(me.get("coins", 0)) < revive_cost:
        await update.message.reply_text("❌ Revival costs 500 coins.")
        return

    await add_coins(update.effective_user.id, -revive_cost)
    await users.update_one(
        {"_id": update.effective_user.id},
        {"$set": {"dead": False}},
    )
    await update.message.reply_html(
        "✨ <b>You have been revived!</b>\n"
        "❤️ Status: <b>ALIVE</b>\n"
        "💰 Revival cost: <b>500 coins</b>"
    )

def _set_ai_provider_status(provider, active, detail=""):
    """Track health without treating one slow request as a provider outage."""
    global _AI_PROVIDER_STATUS
    if provider not in _AI_PROVIDER_STATUS:
        return

    now = time.monotonic()
    previous = _AI_PROVIDER_STATUS[provider]

    if active:
        _AI_PROVIDER_FAILURES[provider] = 0
        _AI_PROVIDER_LAST_FAILURE[provider] = 0.0
        _AI_PROVIDER_STATUS[provider] = True
        should_log = previous is None or previous is False
    else:
        _AI_PROVIDER_FAILURES[provider] = _AI_PROVIDER_FAILURES.get(provider, 0) + 1
        _AI_PROVIDER_LAST_FAILURE[provider] = now
        if _AI_PROVIDER_FAILURES[provider] < _AI_PROVIDER_FAILURE_THRESHOLD:
            return
        _AI_PROVIDER_STATUS[provider] = False
        should_log = previous is not False

    bot = _AI_LOGGER_BOT
    if bot is None or not should_log:
        return
    if now - _AI_PROVIDER_LAST_LOG.get(provider, 0.0) < _AI_PROVIDER_LOG_COOLDOWN:
        return
    _AI_PROVIDER_LAST_LOG[provider] = now

    label = "Elite LLM" if provider == "elite" else "ChatGP"
    if active:
        message = (
            f"🟢 <b>{label} API ACTIVE</b>\n"
            f"Endpoint: <code>{html.escape((ELITE_LLM_BASE_URL + '/chat/completions') if provider == 'elite' else CHATGP_API_URL)}</code>"
        )
    else:
        message = (
            f"🟠 <b>{label} API SLOW/UNSTABLE</b>\n"
            f"Endpoint: <code>{html.escape((ELITE_LLM_BASE_URL + '/chat/completions') if provider == 'elite' else CHATGP_API_URL)}</code>\n"
            f"Failures: <code>{_AI_PROVIDER_FAILURES[provider]}</code>\n"
            f"Last error: <code>{html.escape(str(detail)[:250])}</code>"
        )
    await log_event(type("AIStatusContext", (), {"bot": bot})(), message)

_AI_PROVIDER_MESSAGES = {
    "elite": "Elite LLM",
    "chatgp": "ChatGP",
}

_AI_HTTP_SESSION_LOCK = asyncio.Lock()

# Elite LLM public defaults are 10 chat requests/10 seconds and
# 60 chat requests/60 seconds. Keep a local limiter so a busy group does
# not create a thundering herd of 429s at the provider.
_AI_RATE_LOCK = asyncio.Lock()
_AI_RATE_EVENTS_10S = deque()
_AI_RATE_EVENTS_60S = deque()
_AI_CONCURRENCY = max(1, int(os.getenv("AI_CONCURRENCY", "16")))
_AI_SEMAPHORE = asyncio.Semaphore(_AI_CONCURRENCY)

def _ai_rate_cleanup(now):
    while _AI_RATE_EVENTS_10S and now - _AI_RATE_EVENTS_10S[0] >= 10:
        _AI_RATE_EVENTS_10S.popleft()
    while _AI_RATE_EVENTS_60S and now - _AI_RATE_EVENTS_60S[0] >= 60:
        _AI_RATE_EVENTS_60S.popleft()

async def _wait_for_ai_slot():
    while True:
        async with _AI_RATE_LOCK:
            now = time.monotonic()
            _ai_rate_cleanup(now)
            if len(_AI_RATE_EVENTS_10S) < 10 and len(_AI_RATE_EVENTS_60S) < 60:
                _AI_RATE_EVENTS_10S.append(now)
                _AI_RATE_EVENTS_60S.append(now)
                return True
            wait_10 = (10 - (now - _AI_RATE_EVENTS_10S[0])) if _AI_RATE_EVENTS_10S else 0
            wait_60 = (60 - (now - _AI_RATE_EVENTS_60S[0])) if _AI_RATE_EVENTS_60S else 0
            delay = max(0.05, wait_10, wait_60)
        await asyncio.sleep(delay)

async def _try_get_ai_slot(max_wait=0.8):
    """Get an Elite slot quickly; skip to fallback instead of queueing users."""
    deadline = time.monotonic() + max(0.05, float(max_wait))
    while time.monotonic() < deadline:
        async with _AI_RATE_LOCK:
            now = time.monotonic()
            _ai_rate_cleanup(now)
            if len(_AI_RATE_EVENTS_10S) < 10 and len(_AI_RATE_EVENTS_60S) < 60:
                _AI_RATE_EVENTS_10S.append(now)
                _AI_RATE_EVENTS_60S.append(now)
                return True
            wait_10 = (10 - (now - _AI_RATE_EVENTS_10S[0])) if _AI_RATE_EVENTS_10S else 0
            wait_60 = (60 - (now - _AI_RATE_EVENTS_60S[0])) if _AI_RATE_EVENTS_60S else 0
            delay = min(0.15, max(0.01, wait_10, wait_60))
        await asyncio.sleep(delay)
    return False

async def _get_ai_http_session():
    global _AI_HTTP_SESSION
    if _AI_HTTP_SESSION is not None and not _AI_HTTP_SESSION.closed:
        return _AI_HTTP_SESSION
    import aiohttp
    async with _AI_HTTP_SESSION_LOCK:
        if _AI_HTTP_SESSION is None or _AI_HTTP_SESSION.closed:
            timeout = aiohttp.ClientTimeout(
                total=max(4.5, float(os.getenv("AI_TIMEOUT_SECONDS", "5.0"))),
                sock_connect=3.0,
            )
            connector = aiohttp.TCPConnector(
                limit=max(20, _AI_CONCURRENCY + 4),
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            _AI_HTTP_SESSION = aiohttp.ClientSession(timeout=timeout, connector=connector)
    return _AI_HTTP_SESSION

async def close_ai_http_session():
    global _AI_HTTP_SESSION
    if _AI_HTTP_SESSION is not None and not _AI_HTTP_SESSION.closed:
        await _AI_HTTP_SESSION.close()
    _AI_HTTP_SESSION = None

def _parse_ts(ts):
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo:
            return ts.astimezone(timezone.utc).replace(tzinfo=None)
        return ts
    if isinstance(ts, str):
        try:
            v=datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if v.tzinfo:
                v=v.astimezone(timezone.utc).replace(tzinfo=None)
            return v
        except Exception:
            return None
    return None

def _memory_entry_text(entry):
    return str(entry.get("text", "")).strip() if isinstance(entry, dict) else str(entry).strip()

def _memory_entry_ts(entry):
    return entry.get("ts") if isinstance(entry, dict) else None

def _active_memories(u):
    memories=(u or {}).get("memory", []) if u else []
    cutoff=datetime.utcnow()-timedelta(days=MEMORY_DAYS)
    active=[]
    changed=False
    for entry in memories:
        value=_memory_entry_text(entry)
        if not value:
            changed=True; continue
        ts=_parse_ts(_memory_entry_ts(entry))
        if ts is not None and ts < cutoff:
            changed=True; continue
        if not isinstance(entry, dict) or ts is None:
            active.append({"text":value[:180],"ts":datetime.utcnow()}); changed=True
        else:
            active.append({"text":value[:180],"ts":ts})
    dedup={}
    for item in active:
        dedup[item["text"].casefold()]=item
    return list(dedup.values())[-MAX_MEMORY:], changed

def _history_text(u):
    hist=u.get("chat_history", []) if u else []
    cutoff=datetime.utcnow()-timedelta(days=MEMORY_DAYS)
    kept=[]
    for x in hist:
        if not isinstance(x, dict):
            continue
        ts=_parse_ts(x.get("ts"))
        if ts is None or ts >= cutoff:
            kept.append(x)
    return "\n".join(f"{x.get('role','user')}: {str(x.get('text',''))[:1200]}" for x in kept[-MAX_HISTORY:])

def _memory_text(u):
    active,_=_active_memories(u)
    return "\n".join(f"- {m['text']}" for m in active) or "- No saved facts yet."

async def _prune_and_get_memories(user_id):
    u=await get_user(user_id)
    active,changed=_active_memories(u)
    if changed:
        await users.update_one({"_id":user_id},{"$set":{"memory":active[-MAX_MEMORY:]}})
    return active

async def remember_facts(user_id, text_value):
    if not MEMORY_ENABLED or not text_value:
        return
    t=re.sub(r"\s+", " ", text_value.strip())
    patterns=[
        r"\b(?:my name is|call me) ([^.!?]{1,60})",
        r"\b(?:mera naam) ([^.!?]{1,60})\s*(?:hai|he)",
        r"\b(?:i am from|i'm from) ([^.!?]{1,60})",
        r"\b(?:main|mai) ([^.!?]{1,60})\s*(?:se hoon|se hu|se ho)",
        r"\b(?:i live in|i stay in) ([^.!?]{1,60})",
        r"\b(?:mujhe|mujhko) ([^.!?]{1,80}) (?:pasand hai|accha lagta hai|achha lagta hai)",
        r"\b(?:i like|i love|i enjoy) ([^.!?]{1,80})",
        r"\b(?:my favorite|my favourite|mera fav(?:orite|ourite)?) (?:thing|game|movie|song|food|color|colour) is ([^.!?]{1,80})",
        r"\bremember(?: this| that)?[:\-]?\s*(.{3,160})$",
    ]
    found=[]
    for pat in patterns:
        m=re.search(pat,t,re.I)
        if m:
            found.append(m.group(0).strip()[:180])
    if not found:
        return
    current=await _prune_and_get_memories(user_id)
    by_text={m["text"].casefold():m for m in current}
    now=datetime.utcnow()
    for fact in found:
        by_text[fact.casefold()]={"text":fact,"ts":now}
    await users.update_one({"_id":user_id},{"$set":{"memory":list(by_text.values())[-MAX_MEMORY:]}})

async def _append_history(user_id, user_text, assistant_text):
    now=datetime.utcnow()
    await users.update_one(
        {"_id":user_id},
        {"$push":{"chat_history":{"$each":[
            {"role":"user","text":str(user_text)[:3500],"ts":now},
            {"role":"assistant","text":str(assistant_text)[:3500],"ts":now}
        ],"$slice":-MAX_HISTORY}}},
        upsert=True)

async def _warm_ai_context_cache(user_id, force=False):
    """Warm one user's chat context without blocking the current reply."""
    if not user_id:
        return
    cached = _AI_CONTEXT_CACHE.get(user_id)
    now = time.monotonic()
    if (
        not force
        and cached
        and now - float(cached.get("at", 0.0)) < _AI_CONTEXT_CACHE_TTL
    ):
        return
    if user_id in _AI_CONTEXT_WARMING:
        return
    _AI_CONTEXT_WARMING.add(user_id)
    try:
        u = await get_user(user_id) or {}
        _AI_CONTEXT_CACHE[user_id] = {
            "history": _history_text(u),
            "memory": _memory_text(u),
            "at": time.monotonic(),
        }
    except Exception as exc:
        print(f"[AI][DB] context warm skipped: {type(exc).__name__}: {exc}")
    finally:
        _AI_CONTEXT_WARMING.discard(user_id)


def _get_cached_ai_context(user_id):
    cached = _AI_CONTEXT_CACHE.get(user_id) or {}
    return str(cached.get("history", "")), str(cached.get("memory", ""))


async def _save_ai_context_after_reply(user_id):
    # Let the persistent write finish first, then refresh the in-memory view
    # for the next message. This refresh is deliberately background-only.
    await _warm_ai_context_cache(user_id, force=True)


def _privacy_quick_reply(text_value):
    """Keep internal AI/provider implementation private from end users."""
    t = re.sub(r"\s+", " ", str(text_value or "")).strip().casefold()
    if not t:
        return None

    technical_patterns = (
        r"\bwhich\s+(?:ai\s+)?model\b",
        r"\bwhat\s+(?:ai\s+)?model\b",
        r"\bmodel\s*(?:name|version|used|use)\b",
        r"\bwhich\s+(?:api|provider|service)\b",
        r"\bwhat\s+(?:api|provider|service)\b",
        r"\b(?:api|provider|endpoint)\s+(?:name|url|link|used|use)\b",
        r"\b(?:api|provider)\s+(?:key|token)\b",
        r"\b(?:source|full|original)\s+code\b",
        r"\bgive\s+(?:me\s+)?(?:the\s+)?code\b",
        r"\bshow\s+(?:me\s+)?(?:the\s+)?code\b",
        r"\b(?:system|developer|hidden)\s+prompt\b",
        r"\b(?:internal|private)\s+(?:prompt|config|configuration|implementation)\b",
        r"\b(?:env|environment)\s+(?:variable|vars?)\b",
        r"\b(?:api|bot)\s+(?:url|endpoint|base\s*url)\b",
        r"\bhow\s+(?:does|do)\s+(?:you|u)\s+(?:work|work\s+internally)\b",
        r"\b(?:fallback|routing)\s+(?:api|model|provider|logic)\b",
    )
    if any(re.search(p, t, re.I) for p in technical_patterns):
        return random.choice([
            "Hehe itne technical sawaal kyun 😜 main Vanya hu, bas mujhse baat karo.",
            "Areee secret hai na 😌 main Vanya hu, technical details nahi batati.",
            "Ufff tum toh meri wiring tak pahunch gaye 😂 internal cheezein private hain.",
        ])
    return None

def _compact_vanya_reply(answer, max_words=25, max_lines=2):
    """Keep normal Vanya replies short and Telegram-chat-like."""
    text = re.sub(r"[ \t]+", " ", str(answer or "").strip())
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines[:max_lines])
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return text
    compact = " ".join(words[:max_words]).rstrip(" ,;:-")
    if compact and compact[-1] not in ".!?…":
        compact += "…"
    return compact


def _sanitize_vanya_reply(answer, max_words=25, max_lines=2):
    """Remove accidental internal implementation details before sending."""
    text = str(answer or "").strip()
    if not text:
        return ""
    private_patterns = (
        r"https?://[^\s<>]+",
        r"(?i)\b(?:elite\s*llm|chatgp|gpt[- ]?[0-9.]+|openai|gemini|anthropic|claude|cerebras)\b",
        r"(?i)\b(?:api[_ -]?key|api[_ -]?url|base[_ -]?url|endpoint|system prompt|developer prompt|environment variable|env variable)\b",
        r"(?i)(?:\b503\b|\b502\b|\b429\b|\b500\b|service\s+(?:unavailable|busy)|temporarily\s+(?:busy|unavailable)|system\s+notification|AI\s+interface|接口暂时繁忙|系统通知|暂无有效回答|暂无有效回复|没有有效回答|没有有效回复|无有效回答|无有效回复|有效回答)",
    )
    if any(re.search(p, text, re.I) for p in private_patterns):
        # Provider-generated error/status text is not a Vanya reply.
        # Return empty so _fast_ai_answer can fail over to the next provider.
        return ""
    return _compact_vanya_reply(text, max_words=max_words, max_lines=max_lines)

async def _fast_ai_answer(prompt, max_words=25, max_lines=2):
    """Use the configured AI providers privately with automatic failover."""
    providers = []

    if ELITE_LLM_API_KEY:
        providers.append(("elite", _call_elite_api))

    if CHATGP_API_KEY:
        providers.append(("chatgp", _call_chatgp_api))

    if not providers:
        return None

    # Keep the failover fast: a stuck Elite request must not block ChatGP
    # forever. The normal Elite HTTP session timeout still applies as well.
    elite_timeout = max(
        1.0,
        float(os.getenv("AI_ELITE_FAILOVER_TIMEOUT_SECONDS", "5.0")),
    )

    for provider_name, provider_call in providers:
        try:
            if provider_name == "elite":
                answer = await asyncio.wait_for(
                    provider_call(prompt),
                    timeout=elite_timeout,
                )
            else:
                answer = await provider_call(prompt)

            if answer:
                safe_answer = _sanitize_vanya_reply(answer, max_words=max_words, max_lines=max_lines)
                if safe_answer:
                    return safe_answer

            print(f"[AI][FAILOVER] {provider_name} returned no usable response; trying next provider.")
        except asyncio.TimeoutError:
            print(f"[AI][FAILOVER] {provider_name} timed out; trying next provider.")
        except Exception as exc:
            print(
                f"[AI][FAILOVER] {provider_name} failed: "
                f"{type(exc).__name__}: {exc}"
            )

    return None
def _instant_chat_reply(text_value: str):
    """Instant local replies for very short DM small-talk messages."""
    t = re.sub(r"\s+", " ", (text_value or "").strip().casefold())
    if not t:
        return None
    replies = {
        "hi": ["Hii 😄", "Hii yaar 💕", "Heyy 😌"],
        "hii": ["Hii 😄", "Hii yaar 💕", "Heyy 😌"],
        "hiii": ["Hiii 😄", "Heyy yaar 💕", "Hii 😌"],
        "hello": ["Helloo 😄", "Hii yaar 💕", "Heyy 😌"],
        "hey": ["Heyyy 😄", "Haan bolo 😌", "Hii yaar 💕"],
        "acha": ["Haan yaar 😌", "Hehe achaaa 😄", "Acha ji 😄"],
        "accha": ["Haan yaar 😌", "Hehe achaaa 😄", "Acha ji 😄"],
        "achha": ["Haan yaar 😌", "Hehe achaaa 😄", "Acha ji 😄"],
        "ohh": ["Hehe 😄", "Ohh haan 😌", "Samjhi 😄"],
        "hmm": ["Hmm 😌", "Hmmm, bol na 😄", "Haanji 👀"],
        "ok": ["Okayy 😌", "Theek hai yaar 😄", "Done 😌"],
        "okay": ["Okayy 😌", "Theek hai yaar 😄", "Done 😌"],
        "lol": ["😂", "Hahaha 😭", "Hehe 😄"],
        "haha": ["Hehe 😄", "Hahaha 😂", "Accha ji 😂"],
        "hehe": ["Hehe 😌", "😂", "Haan bolo 😄"],
    }
    choices = replies.get(t)
    return random.choice(choices) if choices else None


def _identity_quick_reply(text_value: str):
    t = re.sub(r"\s+", " ", (text_value or "").strip().casefold())
    # Keep common identity questions instant and consistent.
    who = [
        r"^who (?:are|r) (?:you|u)\??$",
        r"^who are u\??$",
        r"^tum (?:kon|kaun) ho\??$",
        r"^aap (?:kon|kaun) ho\??$",
        r"^(?:tumhara|aapka|tera|apka) naam kya hai\??$",
        r"^(?:name|naam) kya hai\??$",
        r"^what(?:s| is) your name\??$",
        r"^kya naam hai\??$",
    ]
    for pat in who:
        if re.search(pat, t):
            return random.choice([
                "Main Vanya hu 😊 Jaipur se, aur Pune mein design padh rahi hu.",
                "Main Vanya hu 😊 Bas Vanya hi samjho, yaar.",
                "Main Vanya hu 😊 Achha, introduction bhi dena padega kya? 😄",
            ])
    origin = [
        r"^kahan se ho\??$", r"^kaha se ho\??$", r"^where are you from\??$",
        r"^jaipur se ho\??$", r"^tum jaipur se ho\??$",
    ]
    for pat in origin:
        if re.search(pat, t):
            return random.choice([
                "Jaipur se hu 😊",
                "Jaipur meri hai yaar ✨",
                "Jaipur se hu, Pune mein design padh rahi hu 😌",
            ])
    return None

def _ai_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def _call_elite_api(text_value):
    """Call the documented OpenAI-compatible Elite endpoint."""
    import aiohttp
    if not ELITE_LLM_API_KEY:
        return None

    session = await _get_ai_http_session()
    base_model = ELITE_LLM_MODEL or AI_MODEL or "gpt-5-mini"
    # Use the configured model directly. Trying a second model first can
    # turn a healthy provider into an unnecessary 400/404 + latency.
    fallback_models = [str(base_model).strip()] if str(base_model).strip() else []
    max_attempts = max(1, int(os.getenv("AI_RETRY_ATTEMPTS", "1")))
    extra_models = [
        str(x).strip()
        for x in os.getenv("AI_FALLBACK_MODELS", "").split(",")
        if str(x).strip()
    ]
    for model_name in extra_models:
        if model_name not in fallback_models:
            fallback_models.append(model_name)
    last_error = None

    async with _AI_SEMAPHORE:
        for model_index, model_name in enumerate(fallback_models):
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": VANYA_SYSTEM_PROMPT},
                    {"role": "user", "content": text_value},
                ],
                "stream": False,
                "max_tokens": int(os.getenv("AI_MAX_TOKENS", "120")),
            }
            for attempt in range(max_attempts):
                if not await _try_get_ai_slot(float(os.getenv("AI_RATE_WAIT_SECONDS", "0.10"))):
                    return None
                try:
                    async with session.post(
                        f"{ELITE_LLM_BASE_URL}/chat/completions",
                        headers=_ai_headers(ELITE_LLM_API_KEY),
                        json=payload,
                    ) as resp:
                        raw = await resp.text()
                        if resp.status == 429:
                            last_error = RuntimeError(f"HTTP 429: {raw[:250]}")
                            if attempt < max_attempts - 1:
                                retry_after = resp.headers.get("Retry-After")
                                try:
                                    delay = float(retry_after) if retry_after else min(8.0, 1.5 ** attempt)
                                except Exception:
                                    delay = min(8.0, 1.5 ** attempt)
                                await asyncio.sleep(max(0.25, delay))
                                continue
                            break
                        if resp.status >= 500:
                            last_error = RuntimeError(f"HTTP {resp.status}: {raw[:250]}")
                            if attempt < max_attempts - 1:
                                await asyncio.sleep(min(8.0, 1.0 * (2 ** attempt)))
                                continue
                            break
                        if resp.status in (400, 404) and model_index < len(fallback_models) - 1:
                            last_error = RuntimeError(f"Model rejected ({resp.status}): {raw[:220]}")
                            break
                        if resp.status >= 400:
                            # Provider errors must not crash the Telegram handler.
                            # Try the next configured fallback model when possible.
                            last_error = RuntimeError(f"HTTP {resp.status}: {raw[:300]}")
                            if model_index < len(fallback_models) - 1:
                                break
                            break
                        data = await resp.json(content_type=None)
                        answer = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
                        answer = str(answer or "").strip()
                        if not answer:
                            raise RuntimeError("Empty response")
                        await _set_ai_provider_status("elite", True)
                        return answer
                except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                    last_error = exc
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(min(8.0, 1.0 * (2 ** attempt)))
                        continue
                    break

    detail = str(last_error or "request failed")
    await _set_ai_provider_status("elite", False, detail)
    return None


async def _call_elite_api_stream(text_value, on_chunk):
    """Stream Elite output so the user sees the reply as soon as tokens arrive."""
    import aiohttp
    if not ELITE_LLM_API_KEY:
        return None

    session = await _get_ai_http_session()
    model_name = str(ELITE_LLM_MODEL or AI_MODEL or "gpt-5.6-luna").strip()
    if not model_name:
        return None

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": VANYA_SYSTEM_PROMPT},
            {"role": "user", "content": text_value},
        ],
        "stream": True,
        "max_tokens": int(os.getenv("AI_MAX_TOKENS", "120")),
    }

    if not await _try_get_ai_slot(float(os.getenv("AI_RATE_WAIT_SECONDS", "0.10"))):
        return None

    # The shared session is configured for fast calls, but streaming needs a
    # longer socket-read budget so a slow second token does not kill the stream.
    timeout = aiohttp.ClientTimeout(
        total=max(8.0, float(os.getenv("AI_STREAM_TIMEOUT_SECONDS", "10"))),
        sock_connect=3.0,
        sock_read=max(6.0, float(os.getenv("AI_STREAM_READ_TIMEOUT_SECONDS", "8"))),
    )

    collected = []
    last_callback = 0.0
    try:
        async with session.post(
            f"{ELITE_LLM_BASE_URL}/chat/completions",
            headers=_ai_headers(ELITE_LLM_API_KEY),
            json=payload,
            timeout=timeout,
        ) as resp:
            if resp.status >= 400:
                raw = await resp.text()
                await _set_ai_provider_status(
                    "elite", False, f"HTTP {resp.status}: {raw[:300]}"
                )
                return None

            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", "ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_line = line[5:].strip()
                if data_line == "[DONE]":
                    break
                try:
                    data = __import__("json").loads(data_line)
                except Exception:
                    continue

                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content") or ""
                if not piece:
                    # Some compatible gateways may put the text directly in
                    # message.content even while streaming.
                    piece = ((choices[0].get("message") or {}).get("content") or "")
                if not piece:
                    continue

                collected.append(str(piece))
                current = "".join(collected)
                now = time.monotonic()

                # First chunk is pushed immediately; later edits are lightly
                # throttled so Telegram's edit-message limits are not hit.
                if now - last_callback >= 0.35 or len(collected) == 1:
                    await on_chunk(current)
                    last_callback = now

            answer = "".join(collected).strip()
            if answer:
                await _set_ai_provider_status("elite", True)
                await on_chunk(answer)
                return answer

    except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
        await _set_ai_provider_status("elite", False, f"{type(exc).__name__}: {exc}")
    except Exception as exc:
        await _set_ai_provider_status("elite", False, f"{type(exc).__name__}: {exc}")
    return None


async def _call_chatgp_api(text_value):
    """Fallback ChatGP API: POST /api/chat with {prompt} and read {response}."""
    import aiohttp
    if not CHATGP_API_KEY:
        await _set_ai_provider_status("chatgp", False, "CHATGP_API_KEY is not configured")
        return None
    # Reuse the same keep-alive session so fallback requests do not pay a new
    # DNS/TCP/TLS connection setup cost every time.
    session = await _get_ai_http_session()
    timeout = aiohttp.ClientTimeout(total=max(1.5, float(CHATGP_TIMEOUT_SECONDS)))
    try:
        request_url = CHATGP_API_URL
        async with session.post(
            request_url,
            headers=_ai_headers(CHATGP_API_KEY),
            json={"prompt": f"{VANYA_SYSTEM_PROMPT}\n\n{text_value}"},
            timeout=timeout,
        ) as resp:
            raw = await resp.text()
            if resp.status >= 400:
                detail = f"HTTP {resp.status}: {raw[:300]}"
                await _set_ai_provider_status("chatgp", False, detail)
                return None
            data = await resp.json(content_type=None)
            answer = str(
                data.get("response")
                or ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                or data.get("output")
                or ""
            ).strip()
            if not answer:
                await _set_ai_provider_status("chatgp", False, "Empty response")
                return None
            await _set_ai_provider_status("chatgp", True)
            return answer
    except Exception as exc:
        await _set_ai_provider_status("chatgp", False, f"{type(exc).__name__}: {exc}")
        return None


async def probe_ai_providers():
    """Probe providers at startup without allowing a bad model/config to crash the bot."""
    probe = "Reply with only: OK"
    results = {"elite": False, "chatgp": False}

    if ELITE_LLM_API_KEY:
        try:
            results["elite"] = bool(await _call_elite_api(probe))
        except Exception as exc:
            print(f"[AI][PROBE] Elite probe failed: {type(exc).__name__}: {exc}")

    if CHATGP_API_KEY:
        try:
            results["chatgp"] = bool(await _call_chatgp_api(probe))
        except Exception as exc:
            print(f"[AI][PROBE] ChatGP probe failed: {type(exc).__name__}: {exc}")

    return results


async def _save_chat_state_background(user_id, user_text, answer):
    """Persist memory/history after the user already received the fast reply."""
    try:
        await remember_facts(user_id, user_text)
    except Exception as exc:
        print(f"[AI][DB] remember skipped: {type(exc).__name__}: {exc}")
    try:
        await _append_history(user_id, user_text, answer)
    except Exception as exc:
        print(f"[AI][DB] history save skipped: {type(exc).__name__}: {exc}")
    try:
        await _save_ai_context_after_reply(user_id)
    except Exception as exc:
        print(f"[AI][DB] context refresh skipped: {type(exc).__name__}: {exc}")


async def ai_reply(user, text_value, chat_type="private", group_title="", stream_callback=None):
    """Latency-first AI path: no MongoDB round-trip blocks the LLM request."""
    quick = _privacy_quick_reply(text_value)
    if quick:
        asyncio.create_task(_save_chat_state_background(user.id, text_value, quick))
        return quick

    quick = _instant_chat_reply(text_value) if chat_type == "private" else None
    if quick:
        asyncio.create_task(_save_chat_state_background(user.id, text_value, quick))
        return quick

    quick = _identity_quick_reply(text_value)
    if quick and chat_type == "private":
        asyncio.create_task(_save_chat_state_background(user.id, text_value, quick))
        return quick

    # Never wait for MongoDB on the hot path. Use warm in-memory context;
    # for a cold user, the first reply intentionally goes out without history
    # and the cache is warmed in the background for the next message.
    history, memory = _get_cached_ai_context(user.id)
    if not history and not memory:
        asyncio.create_task(_warm_ai_context_cache(user.id))

    # Keep the LLM context compact for faster first-token/response latency.
    history_limit = int(os.getenv("AI_PROMPT_HISTORY_CHARS", "3600" if chat_type == "private" else "6000"))
    memory_limit = int(os.getenv("AI_PROMPT_MEMORY_CHARS", "1400" if chat_type == "private" else "2200"))
    history = history[-history_limit:]
    memory = memory[-memory_limit:]
    detail_request = bool(re.search(
        r"\b(?:detail|detailed|explain|explain\s+properly|full\s+explanation|"
        r"poora\s+(?:detail|samjha)|detail\s+mein|vistaar\s+se)\b",
        str(text_value or "").casefold(),
    ))
    max_words = 80 if detail_request else 25
    max_lines = 4 if detail_request else 2

    prompt = (
        f"Chat type: {chat_type}. Group: {group_title or 'DM'}\n"
        f"User display name: {user.first_name or 'User'}\n\n"
        f"Saved memory (last {MEMORY_DAYS} days):\n{memory}\n\n"
        f"Recent conversation:\n{history or '- None yet.'}\n\n"
        f"User's new message:\n{text_value}\n\n"
        "Reply only as Vanya. Be natural, concise, warm, and context-aware. "
        f"Normal reply: maximum {max_words} words and {max_lines} short lines. "
        "Do not write long paragraphs, lectures, or repeated explanations. "
        "Only use the longer limit when the user explicitly asks for detail."
    )

    answer = await _fast_ai_answer(
        prompt,
        max_words=max_words,
        max_lines=max_lines,
    )
    if answer:
        asyncio.create_task(_save_chat_state_background(user.id, text_value, answer))
        return answer

    # AI providers can occasionally be unavailable/rate-limited. Keep the
    # user-facing fallback natural and context-aware instead of exposing
    # network/API/latency details.
    fallback_text = re.sub(r"\s+", " ", str(text_value or "")).strip().casefold()
    if fallback_text:
        if fallback_text in {"acha", "accha", "achha", "oh", "ohh", "hmm", "hmmm"}:
            fallback_pool = [
                "Haanji 😌 bolo na.",
                "Hehe, sun rahi hu 😄",
                "Hmmm 👀 kya hua?",
                "Acha ji 😌 aur batao.",
            ]
        elif "?" in fallback_text:
            fallback_pool = [
                "Haan, bolo na 😌",
                "Hmm, sun rahi hu 👀",
                "Batao yaar, kya hua? 😄",
            ]
        elif any(word in fallback_text.split() for word in ("haha", "hehe", "lol")):
            fallback_pool = [
                "Hehe 😂",
                "Hahaha 😭",
                "Accha ji 😂",
            ]
        else:
            fallback_pool = [
                "Haan yaar 😌 bolo.",
                "Hmm, sun rahi hu 👀",
                "Achhaaa 😄 aur batao.",
                "Haanji, bolo na 💕",
            ]
        answer = random.choice(fallback_pool)
    else:
        answer = "Haanji 😌 bolo na."
    asyncio.create_task(_save_chat_state_background(user.id, text_value, answer))
    return answer

async def _load_custom_emoji_map():
    global _CUSTOM_EMOJI_CACHE, _CUSTOM_EMOJI_CACHE_AT
    now = time.monotonic()
    if _CUSTOM_EMOJI_CACHE and now - _CUSTOM_EMOJI_CACHE_AT < 300:
        return _CUSTOM_EMOJI_CACHE
    try:
        _CUSTOM_EMOJI_CACHE = await get_custom_emoji_map()
        _CUSTOM_EMOJI_CACHE_AT = now
    except Exception as exc:
        print(f"[CustomEmoji] {type(exc).__name__}: {exc}")
    return _CUSTOM_EMOJI_CACHE


def _is_emoji_codepoint(ch):
    cp = ord(ch)
    return (
        0x1F000 <= cp <= 0x1FAFF or
        0x2600 <= cp <= 0x27BF or
        0x2300 <= cp <= 0x23FF or
        cp in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299}
    )


def _strip_non_custom_emoji(text_value):
    """Remove plain Unicode emoji while leaving normal text untouched."""
    out = []
    i = 0
    value = str(text_value or "")
    while i < len(value):
        ch = value[i]
        if _is_emoji_codepoint(ch):
            i += 1
            while i < len(value):
                cp = ord(value[i])
                if cp in (0xFE0E, 0xFE0F, 0x200D) or 0x1F3FB <= cp <= 0x1F3FF or 0x20E3 <= cp <= 0x20FF:
                    i += 1
                    continue
                if _is_emoji_codepoint(value[i]):
                    i += 1
                    continue
                break
            continue
        if ord(ch) in (0xFE0E, 0xFE0F):
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


async def _premiumize_text(text_value):
    """Sanitize AI text before sending it to Telegram.

    AI/provider output must never expose Telegram custom-emoji markup or
    emoji-id values. Keep the visible text only; custom emoji rendering is
    intentionally disabled here so raw IDs can never leak to users.
    """
    text_value = str(text_value or "")

    # Remove complete custom-emoji tags and their attributes.
    text_value = re.sub(
        r"<tg-emoji\\b[^>]*>(.*?)</tg-emoji>",
        r"\\1",
        text_value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Also handle malformed/incomplete tags produced by an AI provider.
    text_value = re.sub(r"<tg-emoji\\b[^>]*>", "", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"</tg-emoji>", "", text_value, flags=re.IGNORECASE)
    # Never let an emoji-id attribute/value appear as visible chat text.
    text_value = re.sub(r"\\bemoji-id\\s*=\\s*[\\\"']?[^\\s>\\\"']+[\\\"']?", "", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\\bemoji[_ -]?id\\s*[:=]\\s*\\d+", "", text_value, flags=re.IGNORECASE)

    # Remove any other raw HTML tags that a provider may emit.
    text_value = re.sub(r"<[^>]+>", "", text_value)

    # Telegram parse_mode=HTML requires HTML escaping.
    return html.escape(text_value), False


async def send_vanya_reply(update, text_value):
    try:
        rendered, _ = await _premiumize_text(text_value)
    except Exception as exc:
        print(f"[CustomEmoji] sanitizing failed: {type(exc).__name__}: {exc}")
        rendered = html.escape(str(text_value or ""))

    if AI_DISCLOSURE and update.effective_chat.type=="private":
        u=await get_user(update.effective_user.id)
        if not u.get("ai_disclosure_sent"):
            disclosure, _ = await _premiumize_text(
                "Just so it's clear: I'm Vanya, an AI character — not a real person. I keep the chat natural and remember useful things for 30 days."
            )
            await update.effective_chat.send_message(disclosure, parse_mode="HTML")
            await users.update_one({"_id":update.effective_user.id},{"$set":{"ai_disclosure_sent":True}})

    await update.message.reply_text(rendered, parse_mode="HTML")

async def cleanup_expired_memory():
    cutoff=datetime.utcnow()-timedelta(days=MEMORY_DAYS)
    try:
        await users.update_many({}, {"$pull":{
            "chat_history":{"ts":{"$lt":cutoff}},
            "memory":{"ts":{"$lt":cutoff}},
            "memories":{"ts":{"$lt":cutoff}}
        }})
    except Exception as exc:
        print(f"[MemoryCleanup] {type(exc).__name__}: {exc}")

# ───────────────────── callbacks + chat ─────────────────────

async def callback(update,context):
    q=update.callback_query;data=q.data

    if data.startswith("kingdom:join:"):
        parts=data.split(":")
        if len(parts)!=3:
            await q.answer("Invalid Kingdom Wars room.", show_alert=True)
            return
        room_code=parts[2].strip().upper()
        if not re.fullmatch(r"[A-HJ-NP-Z2-9]{6}", room_code):
            await q.answer("Invalid room code.", show_alert=True)
            return
        try:
            from webserver import create_kingdom_join_token
            token=create_kingdom_join_token(room_code, q.from_user.id)
            base=(os.getenv("KINGDOM_WARS_WEBAPP_URL") or "").strip().strip('"').strip("'")
            if not base:
                domain=(os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().strip("/")
                if domain:
                    base="https://"+domain+"/kingdom-wars"
            if base and not base.startswith(("https://","http://")):
                base="https://"+base
            room_url=base.rstrip("/")+"?room="+room_code+"&token="+token
            try:
                await context.bot.send_message(
                    chat_id=q.from_user.id,
                    text=(
                        "🏰 <b>Kingdom Wars</b>\n\n"
                        "✅ Telegram account verified.\n"
                        "Your ruler seat is tied to your Telegram ID. "
                        "Use the button below to enter the battle."
                    ),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏰 Enter Verified Kingdom", web_app=WebAppInfo(url=room_url))
                    ]]),
                    disable_web_page_preview=True,
                )
                await q.answer("✅ Verified link sent to your DM.", show_alert=False)
            except Exception:
                bot_username=(getattr(context.bot,"username",None) or os.getenv("BOT_USERNAME","ItzVanyaBot")).lstrip("@")
                await q.answer(
                    f"Start @{bot_username} in DM first, then click Join again.",
                    show_alert=True,
                )
        except Exception as exc:
            print(f"[KingdomVerify] {type(exc).__name__}: {exc}")
            await q.answer("Could not create your verified join link. Try again.", show_alert=True)
        return

    if data.startswith("proposal:"):
        parts=data.split(":")
        if len(parts) == 4:
            action=parts[1]
            try:
                target_id=int(parts[2])
                proposer_id=int(parts[3])
            except (TypeError, ValueError):
                await q.answer("Invalid proposal.", show_alert=True)
                return
            await _complete_proposal_callback(
                q, context, action, target_id, proposer_id
            )
            return

    # Games that answer their own callback query must be routed before the
    # generic q.answer(), otherwise Telegram receives two callback answers.
    if data.startswith("tap:"):
        await tap_cb(q, data.split(":"))
        return
    if data.startswith("mine:"):
        await mines_cb(q, data.split(":"))
        return

    await q.answer()

    if data == "wordgrid:new":
        await send_wordgrid(q.message, context, getattr(q.from_user, "id", None))
        return
    if data.startswith("wordchain:"):
        if data == "wordchain:join":
            await wordchain_join(update, context)
            return

    if data.startswith("lb|"):
        parts = data.split("|")
        action = parts[1] if len(parts) > 1 else "v"
        period = parts[2] if len(parts) > 2 else "today"
        scope = parts[3] if len(parts) > 3 else "global"
        game = parts[4].upper() if len(parts) > 4 else "ALL"
        if action == "menu":
            await q.edit_message_text(
                "🎮 <b>Select game</b>\n\nChoose which game's points and wins you want to see:",
                parse_mode="HTML",
                reply_markup=leaderboard_kb(period, scope, game, picker=True)
            )
            return
        await _render_leaderboard(q, context, period, scope, game)
        return
    if data.startswith("world:"):
        tab=data.split(":",1)[1]
        url=get_world_webapp_url(tab if tab in ("city","room","pet") else "city")
        if update.effective_chat and update.effective_chat.type in ("group","supergroup"):
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Open Vanya World", url=url)]])
        else:
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Open Vanya World", web_app=WebAppInfo(url=url))]])
        await q.message.reply_html("🌌 <b>Vanya World</b>\n\nBuild your 3D city, decorate your room and raise your pet. ✨", reply_markup=markup)
        return
    if data.startswith("owner:"):
        if not await is_owner_or_sudo(update):
            await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
            return
        action = data.split(":", 1)[1]
        if action == "close":
            await q.edit_message_text("🔒 <b>Owner panel closed.</b>", parse_mode="HTML")
            return
        if action == "stats":
            try:
                total_users = await users.count_documents({})
                started_users = await users.count_documents({"started": True})
                total_groups = await groups.count_documents({})
                active_groups = await groups.count_documents({"active": {"$ne": False}})
                sudo_db = await users.count_documents({"is_sudo": True})
                sudo_total = max(sudo_db, len(SUDO_IDS))
                await q.edit_message_text(
                    "╭━━━〔 📊 <b>VANYA BOT STATS</b> 〕━━━╮\n"
                    "┃ 🔒 <i>Owner/Sudo only</i>\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    f"👥 <b>Groups where bot is recorded:</b> {active_groups:,}\n"
                    f"🗂️ <b>Total known groups:</b> {total_groups:,}\n"
                    f"👤 <b>Total known users:</b> {total_users:,}\n"
                    f"🚀 <b>Started users:</b> {started_users:,}\n"
                    f"👑 <b>Sudo users:</b> {sudo_total:,}",
                    parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
                )
            except Exception as e:
                await q.edit_message_text(f"⚠️ Stats error: {html.escape(str(e))}", parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]]))
            return
        if action == "commands":
            if not await is_owner_or_sudo(update):
                await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
                return

            lines = [
                "👑 <b>Owner/Sudo Commands</b>",
                "",
            ]
            for command, description in STAFF_COMMANDS.items():
                if command in {"owner", "ownerpanel", "panel", "devpanel"}:
                    continue
                if update.effective_user.id != OWNER_ID and command in OWNER_ONLY_COMMANDS:
                    continue
                lines.append(
                    f"• <code>/{command}</code> — {html.escape(description)}"
                )

            await q.edit_message_text(
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "revealgrid":
            if not await is_owner_or_sudo(update):
                await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
                return
            await q.edit_message_text(
                "🔐 <b>Wordgrid Answer Reveal</b>\n\n"
                "Use <code>/revealgrid</code> inside the group where an active Wordgrid game is running.\n\n"
                "The answer will be sent to your private chat and will not be shown to group members.\n"
                "🔒 <i>Owner/Sudo only.</i>",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "revealwordseek":
            if not await is_owner_or_sudo(update):
                await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
                return
            await q.edit_message_text(
                "🔎 <b>Wordseek Answer Reveal</b>\n\n"
                "Use <code>/revealwordseek</code> inside the group where an active Wordseek game is running.\n\n"
                "The answer will be sent to your private chat and will not be shown to group members.\n"
                "👑 <i>Owner/Sudo only.</i>",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "addsudo":
            await q.edit_message_text(
                "➕ <b>Add Sudo</b>\n\n"
                "Reply to a user's message and send <code>/addsudo</code>."
                "\nOnly the Owner can add sudo users.",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "delsudo":
            await q.edit_message_text(
                "➖ <b>Remove Sudo</b>\n\n"
                "Reply to a sudo user's message and send <code>/delsudo</code>."
                "\nOnly the Owner can remove sudo users.",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "addemoji":
            await q.edit_message_text(
                "🎨 <b>Premium Emoji</b>\n\n"
                "Send your Premium/custom emoji to Vanya, then reply to that emoji message with <code>/addemoji</code>."
                "\nOnly the Owner can save emoji IDs.",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "coins":
            await q.edit_message_text(
                "💰 <b>Coin Control</b>\n\n"
                "Only Owner/Sudo can use these commands:\n\n"
                "<code>/addcoins USER_ID AMOUNT</code>\n"
                "<code>/removecoins USER_ID AMOUNT</code>\n\n"
                "Example:\n"
                "<code>/addcoins 123456789 5000</code>\n"
                "<code>/removecoins 123456789 1000</code>\n\n"
                "These commands are hidden from normal users and public command menus.",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "broadcast":
            await q.edit_message_text(
                "📢 <b>Broadcast Center</b>\n\n"
                "Choose where the broadcast should go:\n\n"
                "👤 <b>Users Only</b> — private users who started Vanya\n"
                "💬 <b>Groups Only</b> — groups known to Vanya\n"
                "🌐 <b>Users + Groups</b> — send to both\n\n"
                "After choosing, send <code>/broadcast Your message</code> "
                "or reply to any message/media with <code>/broadcast</code>.\n\n"
                "🔒 <i>Owner/Sudo only.</i>",
                parse_mode="HTML", reply_markup=broadcast_target_kb()
            )
            return
        if action.startswith("broadcastmode:"):
            mode = action.split(":", 1)[1]
            if mode not in {"users", "groups", "both"}:
                await q.answer("Invalid broadcast mode.", show_alert=True)
                return
            modes = {
                "users": "👤 Users Only",
                "groups": "💬 Groups Only",
                "both": "🌐 Users + Groups",
            }
            broadcast_modes = context.application.bot_data.setdefault("broadcast_modes", {})
            broadcast_modes[q.from_user.id] = mode
            await q.edit_message_text(
                "📢 <b>Broadcast Target Selected</b>\n\n"
                f"🎯 <b>{modes[mode]}</b>\n\n"
                "Now send <code>/broadcast Your message</code>\n"
                "or reply to any message/media with <code>/broadcast</code>.\n\n"
                "The broadcast will use the selected target and show a completion report.",
                parse_mode="HTML",
                reply_markup=kb([
                    [InlineKeyboardButton("🔁 Change Target", callback_data="owner:broadcast")],
                    [InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")],
                ])
            )
            return
        if action == "sudo":
            rows=[]
            async for su in users.find({"is_sudo": True}, {"_id": 1, "name": 1, "username": 1}):
                label=html.escape(su.get("name", "User"))
                if su.get("username"):
                    label += f" (@{html.escape(su['username'])})"
                rows.append(f"• {label} — <code>{su['_id']}</code>")
            body="\n".join(rows) or "None"
            await q.edit_message_text(
                "👑 <b>Sudo Users</b>\n\n"+body+
                "\n\n<i>/addsudo and /delsudo are Owner-only.</i>",
                parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "auth":
            rows=[]
            async for g in groups.find({"authorized": True}, {"_id": 1, "title": 1}):
                rows.append(f"• {html.escape(g.get('title','Group'))} — <code>{g['_id']}</code>")
            body="\n".join(rows) or "None"
            await q.edit_message_text(
                "🔐 <b>Authorized Groups</b>\n\n"+body+
                "\n\nUse <code>/auth</code> or <code>/unauth</code> in the target group.",
                parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "home":
            await q.edit_message_text(
                "╭━━━〔 👑 <b>VANYA OWNER PANEL</b> 〕━━━╮\n"
                "┃ 🔒 <i>Owner/Sudo access only</i>\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                "Choose an owner control below.",
                parse_mode="HTML", reply_markup=owner_panel_kb(
                    owner_only=(q.from_user.id == OWNER_ID),
                    staff_access=await is_owner_or_sudo(update),
                )
            )
            return
    if data=="chat:start":
        await q.edit_message_text(
            "💬 <b>Chat With Vanya</b> 💜\n\n"
            "Send me a message in this chat, or use <code>/chat your message</code>.\n\n"
            "✨ I can remember recent conversation context when memory is enabled.",
            parse_mode="HTML",
            reply_markup=kb([
                [InlineKeyboardButton("⌨️ Use /chat", callback_data="chat:usage")],
                [InlineKeyboardButton("⬅️ Back", callback_data="cat:chat"), InlineKeyboardButton("⌂ Home", callback_data="home")]
            ])
        )
        return
    if data=="chat:usage":
        await q.edit_message_text(
            "💬 <b>Chat usage</b>\n\n<code>/chat hello Vanya</code>\n<code>/chat how are you?</code>\n\nOr simply DM me and send your message.",
            parse_mode="HTML",
            reply_markup=kb([[InlineKeyboardButton("⬅️ Back", callback_data="chat:start")]])
        )
        return
    if data=="profile:view":
        u=await get_user(update.effective_user.id)
        await q.edit_message_text(
            f"╭━━━〔 👤 <b>PROFILE</b> 〕━━━╮\n"
            f"┃ <b>{html.escape(u.get('name','User'))}</b>\n"
            f"┃ 💰 Coins: <b>{u.get('coins',0):,}</b>\n"
            f"┃ ⭐ XP: <b>{u.get('xp',0):,}</b>\n"
            f"┃ 🏆 Level: <b>{u.get('level',1)}</b>\n"
            f"╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode="HTML",
            reply_markup=kb([[InlineKeyboardButton("💬 Chat", callback_data="chat:start")], [InlineKeyboardButton("⬅️ Back", callback_data="cat:chat")]])
        )
        return

    if data=="home":
        await q.edit_message_text(
            "✨ <b>Vanya help menu</b> ✨\n\n<i>Pick a category below to see my commands.</i> 💜\n\n💬 <b>or just DM me — or say \"Vanya\" in a group — to chat anytime!</b>",
            parse_mode="HTML", reply_markup=help_menu_kb())
        return
    if data=="startmenu":
        await q.edit_message_text(
            "✨ <b>Hey, I'm Vanya 💜</b>\n\n"
            "<i>Not your average bot — I actually feel like a real one. 😏</i>\n\n"
            "🫧 <b>I remember you</b> — our chats, your vibe, where we left off.\n"
            "💬 <b>I talk like a person</b>, never a script — sweet when you're sweet, savage when you're not.\n"
            "🔔 <b>I check in too</b> — go quiet on me and I might text first. 😈\n\n"
            "Oh, and I run the fun around here:\n"
            "🎮 <b>20+ games</b> • 💰 <b>a living economy</b>\n"
            "💕 <b>ship, marry & drama</b>\n\n"
            "Tap <b>Help & Commands</b> to see it all, or add me to your group 👇",
            parse_mode="HTML", reply_markup=start_menu())
        return
    if data=="help":
        await q.edit_message_text(
            "✨ <b>Vanya help menu</b> ✨\n\n<i>Pick a category below to see my commands.</i> 💜\n\n💬 <b>or just DM me — or say \"Vanya\" in a group — to chat anytime!</b>",
            parse_mode="HTML", reply_markup=help_menu_kb())
        return
    if data.startswith("cat:"):
        name=data.split(":")[1]
        if name == "admin" and not await is_owner_or_sudo(update):
            await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Back", callback_data="help")]]))
            return
        if name=="games":
            await q.edit_message_text("🎮 <b>Game commands</b> 🎮\n\n<i>Choose a game below to see how to play and its commands!</i> 👇",parse_mode="HTML",reply_markup=game_menu_kb())
        else:
            title,lines=CATEGORIES[name]
            safe_lines = [safe_html(line) for line in lines]
            await q.edit_message_text(title+"\n\n"+"\n".join(safe_lines),parse_mode="HTML",reply_markup=back())
        return
    if data.startswith("game:"):
        key=data.split(":")[1]
        if key.upper() == "UNO":
            webapp_url = get_uno_webapp_url()
            if webapp_url and webapp_url.startswith("https://"):
                msg = (
                    "╭━━━〔 🃏 <b>VANYA UNO</b> 〕━━━╮\n"
                    "┃ <i>Live Multiplayer Arena</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🎯 Create or join a room and play with 2–4 real players.\n"
                    "🤖 Add a bot only if you want one."
                )
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    markup = kb([
                        [InlineKeyboardButton("🃏 Play UNO", url=webapp_url)],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                else:
                    markup = kb([
                        [InlineKeyboardButton("🃏 Play UNO", web_app=WebAppInfo(url=webapp_url))],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg, parse_mode="HTML", reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🃏 <b>UNO Web App is not configured.</b>\n\nSet <code>UNO_WEBAPP_URL</code> to your public HTTPS /uno URL in Railway Variables.",
                    parse_mode="HTML", reply_markup=back()
                )
            return
        if key.upper() == "LUDO":
            webapp_url = get_ludo_webapp_url()
            if webapp_url and webapp_url.startswith("https://"):
                msg = (
                    "╭━━━〔 🎲 <b>VANYA LUDO</b> 〕━━━╮\n"
                    "┃ <i>Live Multiplayer Arena</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🎯 Create or join a room and play with 2–4 real players.\n"
                    "🤖 Add a bot only if you want one."
                )
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    markup = kb([
                        [InlineKeyboardButton("🎲 Play Ludo", url=webapp_url)],
                        [InlineKeyboardButton("💬 Game Chat", callback_data="gchat:LUDO:telegram")],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                else:
                    markup = kb([
                        [InlineKeyboardButton("🎲 Play Ludo", web_app=WebAppInfo(url=webapp_url))],
                        [InlineKeyboardButton("💬 Game Chat", callback_data="gchat:LUDO:telegram")],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg, parse_mode="HTML", reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🎲 <b>Ludo Web App is not configured.</b>\n\nSet <code>LUDO_WEBAPP_URL</code> to your public HTTPS /ludo URL in Railway Variables.",
                    parse_mode="HTML",
                    reply_markup=back()
                )
            return
        if key.upper() == "SCRIBBLE":
            webapp_url = (os.getenv("SCRIBBLE_WEBAPP_URL") or "").strip()
            if not webapp_url:
                domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().strip("/")
                if domain:
                    webapp_url = "https://" + domain + "/scribble"
            if webapp_url and not webapp_url.startswith(("https://", "http://")):
                webapp_url = "https://" + webapp_url
            if webapp_url:
                msg = (
                    "╭━━━〔 🖌️ <b>VANYA SCRIBBLE</b> 〕━━━╮\n"
                    "┃ <i>Real-time drawing room</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🎨 Create or join a live drawing room.\n"
                    "💬 Draw and chat together in real time."
                )
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    markup = kb([
                        [InlineKeyboardButton("🖌️ Open Scribble", url=webapp_url)],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                else:
                    markup = kb([
                        [InlineKeyboardButton("🖌️ Open Scribble", web_app=WebAppInfo(url=webapp_url))],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg, parse_mode="HTML", reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🖌️ <b>Scribble Web App is not configured.</b>\n\nSet <code>SCRIBBLE_WEBAPP_URL</code> to your public HTTPS /scribble URL in Railway Variables.",
                    parse_mode="HTML",
                    reply_markup=back()
                )
            return
        if key.upper() == "SUBWAY":
            domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "personality-production-6405.up.railway.app").strip().strip("/")
            webapp_url = (os.getenv("STREET_RUSH_WEBAPP_URL") or "").strip().strip('"').strip("'")
            if not webapp_url and domain:
                webapp_url = "https://" + domain + "/street-rush"
            if webapp_url and not webapp_url.startswith(("https://", "http://")):
                webapp_url = "https://" + webapp_url
            if webapp_url:
                msg = (
                    "╭━━━〔 🏃 <b>VANYA STREET RUSH</b> 〕━━━╮\n"
                    "┃ <i>Neon Endless Runner</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🏙️ Run through the city, change lanes and dodge traffic.\n"
                    "🪙 Collect coins • 🦘 Jump barriers • 🧎 Slide under gates\n"
                    "⚡ Speed keeps increasing. How far can you run?"
                )
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    markup = kb([
                        [InlineKeyboardButton("🏃 Play Street Rush", url=webapp_url)],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                else:
                    markup = kb([
                        [InlineKeyboardButton("🏃 Play Street Rush", web_app=WebAppInfo(url=webapp_url))],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg, parse_mode="HTML", reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🏃 <b>Street Rush</b> is not configured.\n\nSet <code>STREET_RUSH_WEBAPP_URL</code> or your Railway public domain.",
                    parse_mode="HTML", reply_markup=back()
                )
            return
        if key.upper() == "KINGDOMWARS":
            webapp_url = (os.getenv("KINGDOM_WARS_WEBAPP_URL") or "").strip().strip('"').strip("'")
            if not webapp_url:
                domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().strip("/")
                if domain:
                    webapp_url = "https://" + domain + "/kingdom-wars"
            if webapp_url and not webapp_url.startswith(("https://", "http://")):
                webapp_url = "https://" + webapp_url
            if webapp_url:
                room_url = webapp_url.rstrip("/") + "?room=" + str(getattr(update, "_kingdom_room_code", "") or "")
                # Create a room for the callback chat so the button opens a ready lobby.
                try:
                    from webserver import create_kingdom_room_for_group
                    room_code = await create_kingdom_room_for_group(
                        update.effective_chat.id if update.effective_chat and update.effective_chat.type != "private" else None
                    )
                    room_url = webapp_url.rstrip("/") + "?room=" + room_code
                except Exception:
                    pass
                msg = (
                    "╭━━━〔 🏰 <b>KINGDOM WARS</b> 〕━━━╮\n"
                    "┃ <i>Live Grand Strategy Arena</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "👑 Build your kingdom, gather resources, recruit an army and conquer land.\n"
                    "⚔️ <b>2–6 rulers</b> • live turns • real-time war map\n"
                    "🏆 Reach <b>70 land</b> to claim the crown.\n\n"
                    "💰 Winner: <b>+500 coins +100 XP</b>\n"
                    "🎁 Participants: <b>+100 coins +25 XP</b>"
                )
                if update.effective_chat and update.effective_chat.type in ("group","supergroup"):
                    markup=kb([
                        [InlineKeyboardButton("🔐 Join as Telegram",callback_data=f"kingdom:join:{room_code}")],
                        [InlineKeyboardButton("⟵ Back to Games",callback_data="cat:games")]
                    ])
                else:
                    markup=kb([
                        [InlineKeyboardButton("🏰 Open Kingdom Wars",web_app=WebAppInfo(url=room_url))],
                        [InlineKeyboardButton("⟵ Back to Games",callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg,parse_mode="HTML",reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🏰 <b>Kingdom Wars Web App is not configured.</b>\n\n"
                    "Set <code>KINGDOM_WARS_WEBAPP_URL</code> or <code>MINIAPP_DOMAIN</code> in Railway Variables.",
                    parse_mode="HTML",reply_markup=back()
                )
            return
        if key.upper() == "CHESS":
            webapp_url=get_chess_webapp_url()
            if webapp_url and webapp_url.startswith("https://"):
                msg=("╭━━━〔 ♟️ <b>VANYA CHESS</b> 〕━━━╮\n"
                     "┃ <i>Live Multiplayer Arena</i> ✦\n"
                     "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                     "♟️ Create a room, invite one player, or add a bot.\n"
                     "⏱️ Live board, turns, moves and chat.")
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    markup=kb([[InlineKeyboardButton("♟️ Play Chess",url=webapp_url)],[InlineKeyboardButton("⟵ Back to Games",callback_data="cat:games")]])
                else:
                    markup=kb([[InlineKeyboardButton("♟️ Play Chess",web_app=WebAppInfo(url=webapp_url))],[InlineKeyboardButton("⟵ Back to Games",callback_data="cat:games")]])
                await q.edit_message_text(msg,parse_mode="HTML",reply_markup=markup)
            else:
                await q.edit_message_text("♟️ <b>Chess Web App is not configured.</b>\n\nSet <code>CHESS_WEBAPP_URL</code> to your public HTTPS /chess URL in Railway Variables.",parse_mode="HTML",reply_markup=back())
            return
        body=f"🎯 <b>How to play</b>\n{safe_html(GAME_INFO.get(key,'Coming soon.'))}\n\n💬 <b>Game Chat</b> — talk with players without leaving the arena."
        msg, markup=game_room_ui(key, body)
        await q.edit_message_text(msg,parse_mode="HTML",reply_markup=markup);return
    if data.startswith("gchat:"):
        parts=data.split(":",2)
        key=parts[1] if len(parts)>1 else "ARCADE"
        room=parts[2] if len(parts)>2 else "current chat"
        await q.answer("Game chat opened", show_alert=False)
        await q.edit_message_text(
            f"💬 <b>{html.escape(key)} GAME CHAT</b>\n\n"
            f"Room: <code>{html.escape(room)}</code>\n\n"
            "Send your message with:\n<code>/gchat your message</code>\n\n"
            "Messages are posted into the current game chat.",
            parse_mode="HTML",
            reply_markup=kb([[InlineKeyboardButton("🎮 Back to Arena",callback_data=f"game:{key}" if key!="ARCADE" else "cat:games")], [InlineKeyboardButton("⌂ Home",callback_data="home")]]))
        return
    if data.startswith("rps:"):
        await rps_cb(q, data.split(":"))
        return
    if data.startswith("card:"):
        await card_cb(q, data.split(":"))
        return
    if data.startswith("uno:"):
        await uno_cb(q,data.split(":"));return
    if data.startswith("ludo:"):
        await ludo_cb(q,data.split(":")[1]);return
    if data.startswith("chess:") or data.startswith("resign:"):
        await chess_cb(q,data.split(":"));return

async def capture_owner_custom_emojis(update, context):
    """Automatically save real custom-emoji IDs from the Owner's messages."""
    user = update.effective_user
    message = update.effective_message
    if not user or user.id != OWNER_ID or not message:
        return

    pairs = []
    try:
        for entity, value in (message.parse_entities() or {}).items():
            if getattr(entity, "type", "") == "custom_emoji" and getattr(entity, "custom_emoji_id", None):
                pairs.append((str(entity.custom_emoji_id), str(value)))
    except Exception as exc:
        print(f"[CustomEmojiCapture] {type(exc).__name__}: {exc}")

    try:
        for entity, value in (message.parse_caption_entities() or {}).items():
            if getattr(entity, "type", "") == "custom_emoji" and getattr(entity, "custom_emoji_id", None):
                pairs.append((str(entity.custom_emoji_id), str(value)))
    except Exception:
        pass

    if not pairs:
        return

    seen = set()
    for eid, alternative in pairs:
        if eid in seen:
            continue
        seen.add(eid)
        await save_custom_emoji(eid, alternative, user.id)

    try:
        from protected_bot import ProtectedBot
        ProtectedBot._emoji_cache = {}
        ProtectedBot._emoji_cache_at = 0.0
    except Exception:
        pass


async def _typing_heartbeat(bot, chat_id, stop_event, interval=2.0):
    """Keep Telegram's 'typing…' indicator visible while AI is generating."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


async def chat(update,context):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("💬 Tell me something: /chat hello Vanya")
        return
    # Do not block the typing indicator or LLM call on a MongoDB write.
    # ai_reply() persists the user state in the background.
    typing_stop = asyncio.Event()
    typing_started_at = time.monotonic()
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
    except Exception:
        pass
    typing_task = asyncio.create_task(
        _typing_heartbeat(context.bot, update.effective_chat.id, typing_stop)
    )
    try:
        answer = await ai_reply(update.effective_user, text, "private")
        # Telegram may not visibly render a typing action when the answer is
        # returned almost instantly (for quick replies). Keep it visible for
        # a tiny minimum so DM chat still feels natural.
        min_typing = max(0.0, float(os.getenv("AI_MIN_TYPING_SECONDS", "1.5")))
        remaining = min_typing - (time.monotonic() - typing_started_at)
        if remaining > 0:
            await asyncio.sleep(remaining)
        await send_vanya_reply(update, answer)
    finally:
        typing_stop.set()
        typing_task.cancel()

async def gchat(update,context):
    text=" ".join(context.args).strip()
    if not text:
        await update.message.reply_text("💬 Usage: /gchat <your message>")
        return
    await ensure_user(update.effective_user)
    name=html.escape(update.effective_user.first_name or "Player")
    await update.message.reply_html(f"💬 <b>{name}</b>  ›  {html.escape(text)}")

async def direct_game_answer(update, context):
    """Treat plain text as an answer while a word game is active in the chat."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return

    wordgrid_active = context.application.bot_data.get("wordgrid_active", {})
    if chat_id in wordgrid_active:
        await wordgrid_answer(update, context)
        return

    if chat_id in WORDSEEK_GAMES:
        await wordseek_answer(update, context)
        return

    if chat_id in WORDCHAIN_GAMES:
        handled = await wordchain_answer(update, context)
        if handled:
            return

    if chat_id in WORDSCRAMBLE_GAMES:
        handled = await wordscramble_answer(update, context)
        if handled:
            return


async def mention_chat(update,context):
    if not update.message:
        return

    # Quest tracking must never delay chat handling.
    chat = update.effective_chat
    if not chat:
        return

    text = (update.message.text or "").strip()
    if not text or len(text) > 1200:
        return

    if chat.type == "private":
        # Natural DM replies without requiring /chat.
        if not AI_DM_MODE:
            return
        if text.startswith("/"):
            return
        typing_stop = asyncio.Event()
        typing_started_at = time.monotonic()
        try:
            await context.bot.send_chat_action(chat_id=chat.id, action="typing")
        except Exception:
            pass
        typing_task = asyncio.create_task(
            _typing_heartbeat(context.bot, chat.id, typing_stop)
        )

        stream_state = {"message": None, "last_text": "", "last_edit": 0.0}

        async def stream_to_telegram(current_text):
            clean = re.sub(r"<[^>]+>", "", str(current_text or "")).strip()
            if not clean:
                return
            rendered = html.escape(clean)
            now = time.monotonic()
            message = stream_state.get("message")

            try:
                if message is None:
                    message = await update.message.reply_text(
                        rendered,
                        parse_mode="HTML",
                    )
                    stream_state["message"] = message
                    stream_state["last_text"] = clean
                    stream_state["last_edit"] = now
                    return

                if clean == stream_state.get("last_text"):
                    return
                if now - float(stream_state.get("last_edit", 0.0)) < 0.30:
                    return

                await context.bot.edit_message_text(
                    chat_id=chat.id,
                    message_id=message.message_id,
                    text=rendered,
                    parse_mode="HTML",
                )
                stream_state["last_text"] = clean
                stream_state["last_edit"] = now
            except Exception as exc:
                print(f"[AI][STREAM] Telegram update skipped: {type(exc).__name__}: {exc}")

        try:
            answer = await ai_reply(
                update.effective_user,
                text,
                "private",
                stream_callback=stream_to_telegram,
            )

            min_typing = max(0.0, float(os.getenv("AI_MIN_TYPING_SECONDS", "0.7")))
            remaining = min_typing - (time.monotonic() - typing_started_at)
            if remaining > 0:
                await asyncio.sleep(remaining)

            # If streaming already created the message, only make sure the
            # final text is present. Otherwise use the normal reply path.
            if stream_state.get("message") is None:
                await send_vanya_reply(update, answer)
            elif answer:
                final_clean = re.sub(r"<[^>]+>", "", str(answer)).strip()
                final_rendered = html.escape(final_clean)
                if final_clean and final_clean != stream_state.get("last_text"):
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat.id,
                            message_id=stream_state["message"].message_id,
                            text=final_rendered,
                            parse_mode="HTML",
                        )
                    except Exception as exc:
                        print(f"[AI][STREAM] final edit skipped: {type(exc).__name__}: {exc}")
        finally:
            typing_stop.set()
            typing_task.cancel()
        return

    if not AI_GROUP_MODE:
        return

    # Never let the normal AI chat handler consume active word-game answers.
    wordgrid_active = context.application.bot_data.get("wordgrid_active", {})
    if (
        chat.id in wordgrid_active
        or chat.id in WORDSEEK_GAMES
        or chat.id in WORDCHAIN_GAMES
        or chat.id in WORDSCRAMBLE_GAMES
    ):
        return

    if text.startswith("/"):
        return

    # Telegram can deliver an @mention as an entity rather than as plain text.
    # Only Vanya's own mentions should wake the AI. If someone is talking to
    # another tagged user, do not interrupt that conversation.
    bot_username = getattr(context.bot, "username", None)
    vanya_aliases = {"vanya", "itzvanya"}
    if bot_username:
        vanya_aliases.add(bot_username.lower().lstrip("@"))

    mentioned = bool(re.search(r"(?<!\w)(?:@?(?:vanya|itzvanya))(?!\w)", text, re.I))
    other_user_mentioned = False

    for entity in (update.message.entities or []):
        if getattr(entity, "type", "") == "mention":
            mention_text = text[entity.offset:entity.offset + entity.length].lstrip("@").lower()
            if mention_text in vanya_aliases:
                mentioned = True
            else:
                other_user_mentioned = True

    # Fallback for usernames when Telegram does not provide a usable entity.
    for username in re.findall(r"(?<!\w)@([A-Za-z0-9_]{3,32})", text):
        if username.lower() not in vanya_aliases:
            other_user_mentioned = True

    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    greeting = bool(re.fullmatch(
        r"(?:"
        r"(?:hi+|hello+|hey+)(?:\s+@?(?:vanya|itzvanya))?(?:\s+.*)?"
        r"|@?(?:vanya|itzvanya)\s+(?:hi+|hello+|hey+)(?:\s+.*)?"
        r"|(?:good\s+morning|good\s+night|goodnight)\s+@?(?:vanya|itzvanya)(?:\s+.*)?"
        r"|@?(?:vanya|itzvanya)\s+(?:good\s+morning|good\s+night|goodnight)(?:\s+.*)?"
        r")[\s!.?~]*",
        normalized,
        re.I,
    ))

    replied_to_bot = (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.id == context.bot.id
    )

    # If another user is explicitly tagged, keep Vanya out of that
    # direct conversation.
    if other_user_mentioned and not mentioned:
        return

    # A reply to another person's message is also a private conversation
    # between those users. Only replies to Vanya should trigger her.
    reply_to = update.message.reply_to_message
    if (
        reply_to is not None
        and reply_to.from_user is not None
        and reply_to.from_user.id != context.bot.id
        and not mentioned
    ):
        return

    # Group AI mode: reply to ordinary messages too, even without a mention,
    # greeting, or reply-to-Vanya. Commands and active game answers are
    # excluded above.
    should_reply = True

    # Do non-critical progression work in the background so it cannot add
    # MongoDB latency to the visible chat reply.
    asyncio.create_task(progress_quest(update.effective_user.id))
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass
    group_title = getattr(update.effective_chat, "title", "") or ""
    answer = await ai_reply(update.effective_user, text, "group", group_title)
    await send_vanya_reply(update, answer)


async def persona(update, context):
    await update.message.reply_html(
        "💜 <b>Meet Vanya</b>\n\n"
        "I'm <b>ItzVanya</b>, a fictional AI character with an 18-year-old "
        "Delhi-style personality. I chat in casual English/Hinglish, remember "
        "recent messages, and can join conversations in DMs and groups.\n\n"
        "✨ Natural DM chat\n"
        "💬 Mention/reply-to chat in groups\n"
        "🧠 Short conversation memory\n"
        "⌨️ Typing-style delays\n"
        "😂 Casual reactions + light Delhi slang\n"
        "🎮 Games + economy + social features\n\n"
        "<i>I'm an AI character, not a real human.</i>"
    )


# ───────────────────── complete advertised features ─────────────────────

async def rank(update, context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)
    xp = int(u.get("xp", 0))
    level = int(u.get("level", 1))
    await update.message.reply_html(
        f"⭐ <b>{html.escape(u.get('name','User'))}'s Rank</b>\n"
        f"XP: <b>{xp:,}</b>\nLevel: <b>{level}</b>\n"
        f"Next level: <b>{max(0, level*1000-xp):,} XP</b>"
    )

async def kill(update, context):
    target = await target_user(update)
    if not target or target.id == update.effective_user.id:
        await update.message.reply_text("Reply to another player: /kill &lt;amount&gt;")
        return
    try:
        amount = max(1, int(context.args[0]))
    except Exception:
        amount = 100
    me = await get_user(update.effective_user.id)
    victim = await get_user(target.id)
    if not victim:
        await ensure_user(target)
        victim = await get_user(target.id)
    amount = min(amount, int(victim.get("coins", 0)))
    if amount <= 0:
        await update.message.reply_text("That player has no coins to bounty. 😭")
        return
    if random.random() < 0.5:
        await add_coins(target.id, -amount)
        await add_coins(update.effective_user.id, amount)
        await users.update_one({"_id": update.effective_user.id}, {"$inc": {"kills": 1}})
        await update.message.reply_text(f"🎯 Fictional bounty won! +{amount:,} coins.")
    else:
        fine = min(100, int(me.get("coins", 0)))
        await add_coins(update.effective_user.id, -fine)
        await update.message.reply_text(f"💥 Bounty failed. You lost {fine:,} coins.")

async def revive(update, context):
    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to a player: /revive")
        return
    await ensure_user(target)
    await users.update_one({"_id": target.id}, {"$set": {"revived": True}})
    await update.message.reply_text(f"✨ {target.first_name or 'Player'} has been revived!")

async def topkill(update, context):
    cur = users.find().sort("kills", -1).limit(10)
    rows = []
    i = 1
    async for u in cur:
        rows.append(f"{i}. {html.escape(u.get('name','User'))} — {u.get('kills',0)}")
        i += 1
    await update.message.reply_html("🎯 <b>Top Assassins</b>\n\n" + ("\n".join(rows) or "No scores yet."))

async def marriage(update, context):
    target = await target_user(update) or update.effective_user
    await ensure_user(target)
    u = await get_user(target.id)
    partner = u.get("partner")
    if partner:
        p = await get_user(partner)
        pname = p.get("name", str(partner)) if p else str(partner)
        await update.message.reply_html(f"💕 <b>{html.escape(u.get('name','User'))}</b> is married to <b>{html.escape(pname)}</b>.")
    else:
        await update.message.reply_text("💔 Single for now.")

async def reject(update, context):
    u = await get_user(update.effective_user.id)
    if not u or not u.get("pending_proposal"):
        await update.message.reply_text("No pending proposal.")
        return
    await users.update_one({"_id": update.effective_user.id}, {"$unset": {"pending_proposal": ""}})
    await update.message.reply_text("💔 Proposal declined. No hard feelings.")

STAFF_COMMANDS = {
    "owner": "Open Owner/Sudo panel",
    "ownerpanel": "Open Owner/Sudo panel",
    "panel": "Open Owner/Sudo panel",
    "devpanel": "Open Owner/Sudo panel",
    "broadcast": "Broadcast to users, groups, or both",
    "addcoins": "Add coins by user ID",
    "removecoins": "Remove coins by user ID",
    "sudolist": "List sudo users",
    "auth": "Authorize current group",
    "unauth": "Unauthorize current group",
    "authlist": "List authorized groups",
    "stats": "View bot statistics",
    "revealgrid": "Reveal Wordgrid answer",
    "revealwordseek": "Reveal Wordseek answer",
    "addemoji": "Save premium custom emoji",
    "addsudo": "Add sudo user",
    "delsudo": "Remove sudo user",
    "blacklist": "Blacklist a user (Owner only)",
    "unblacklist": "Remove a user from blacklist (Owner only)",
}
OWNER_ONLY_COMMANDS = {"addsudo", "delsudo", "addemoji", "blacklist", "unblacklist"}


async def track_incoming_chat(update, context):
    try:
        chat = update.effective_chat
        user = update.effective_user
        if chat and chat.type != "private":
            await track_group(chat)
            if user and not getattr(user, "is_bot", False):
                await ensure_user(user)
                # Record that this user has spoken in this group. This powers
                # /couple without relying on the administrator list.
                await users.update_one(
                    {"_id": user.id},
                    {"$addToSet": {"group_ids": chat.id}},
                    upsert=True,
                )
    except Exception:
        pass

async def stats(update, context):
    """Owner/Sudo-only bot usage statistics."""
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return

    try:
        total_users = await users.count_documents({})
        started_users = await users.count_documents({"started": True})
        total_groups = await groups.count_documents({})
        # Missing `active` is treated as active for legacy group records;
        # explicitly removed groups have active=False.
        active_groups = await groups.count_documents({"active": {"$ne": False}})
        sudo_db = await users.count_documents({"is_sudo": True})
        configured_sudo = len(SUDO_IDS)
        sudo_total = max(sudo_db, configured_sudo)

        await update.message.reply_html(
            "╭━━━〔 📊 <b>VANYA BOT STATS</b> 〕━━━╮\n"
            "┃ 🔒 <i>Owner/Sudo only</i>\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"👥 <b>Groups where bot is recorded:</b> {active_groups:,}\n"
            f"🗂️ <b>Total known groups:</b> {total_groups:,}\n"
            f"👤 <b>Total known users:</b> {total_users:,}\n"
            f"🚀 <b>Started users:</b> {started_users:,}\n"
            f"👑 <b>Sudo users:</b> {sudo_total:,}\n\n"
            "ℹ️ Group count is based on groups the bot has seen/recorded;\n"
            "removed groups are excluded after Telegram reports removal.",
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Stats error: {e}")


async def answer(update, context):
    """Route /answer to the active Wordgrid game first, otherwise Wordseek."""
    active = context.application.bot_data.get("wordgrid_active", {}) if context.application else {}
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is not None and chat_id in active:
        await wordgrid_answer(update, context)
        return
    await wordseek_answer(update, context)


async def end_game(update, context):
    """End all active games associated with the current Telegram group."""
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("🎮 /end sirf group games ko end karta hai. Is command ko group mein use karo.")
        return

    chat_id = chat.id
    ended = []

    # Native bot-side games.
    for gid, game in list(RPS_GAMES.items()):
        if game.get("chat_id") == chat_id:
            RPS_GAMES.pop(gid, None)
            ended.append("RPS")

    for room_id, room in list(CARD_ROOMS.items()):
        if room.get("group_id") == chat_id:
            CARD_ROOMS.pop(room_id, None)
            ended.append("Card")

    if chat_id in WORDSEEK_GAMES:
        WORDSEEK_GAMES.pop(chat_id, None)
        ended.append("Wordseek")

    wordgrid_active = context.application.bot_data.get("wordgrid_active", {}) if context.application else {}
    if chat_id in wordgrid_active:
        wordgrid_active.pop(chat_id, None)
        ended.append("Wordgrid")

    if chat_id in WORDCHAIN_GAMES:
        WORDCHAIN_GAMES.pop(chat_id, None)
        ended.append("Wordchain")

    # Legacy in-bot game dictionaries are still cleaned up for older rooms.
    for store, label in (
        (uno_games, "UNO"),
        (ludo_games, "Ludo"),
        (chess_games, "Chess"),
    ):
        for gid in list(store.keys()):
            if str(gid).startswith(str(chat_id) + "-"):
                store.pop(gid, None)
                ended.append(label)

    # Mines is stored per user; clear active rounds for users known in this group.
    try:
        mine_result = await users.update_many(
            {"group_ids": chat_id, "mines_active": True},
            {"$set": {"mines_active": False, "mines_set": [], "mines_safe": [], "mines_bet": 0}},
        )
        if mine_result.modified_count:
            ended.append(f"Mines ({mine_result.modified_count} player)")
    except Exception:
        pass

    # Browser Mini Apps are independent web rooms.
    # /end intentionally does NOT stop UNO/Ludo/Chess/Scribble browser rooms.
    if not ended:
        await update.message.reply_text(
            "ℹ️ Is group mein abhi koi active game nahi mila."
        )
        return

    counts = {}
    for item in ended:
        key = item.split(" (", 1)[0]
        counts[key] = counts.get(key, 0) + 1
    lines = [f"{name}: {count}" if count > 1 else name for name, count in counts.items()]

    await update.message.reply_html(
        "🛑 <b>GAME SESSION ENDED</b>\n\n"
        "✅ Current group ke active game sessions close kar diye gaye.\n"
        "• " + "\n• ".join(html.escape(x) for x in lines) + "\n\n"
        "🎮 Ab koi bhi player naya game start kar sakta hai."
    )


async def chatstatus(update, context):
    """Diagnose Telegram group-message access without requiring bot admin rights."""
    if not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("ℹ️ /chatstatus group mein use karo.")
        return

    try:
        me = await context.bot.get_me()
        privacy_ok = bool(getattr(me, "can_read_all_group_messages", False))
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Telegram status check failed: {exc}")
        return

    try:
        member = await context.bot.get_chat_member(
            update.effective_chat.id,
            context.bot.id,
        )
        bot_admin = getattr(member, "status", "") in ("administrator", "creator")
    except Exception:
        bot_admin = False

    access = "✅ ALL GROUP MESSAGES" if privacy_ok or bot_admin else "❌ NORMAL MESSAGES NOT DELIVERED"
    privacy = "🟢 Privacy disabled" if privacy_ok else "🔴 Privacy enabled"
    admin = "🟢 Bot is admin" if bot_admin else "⚪ Bot is not admin"

    await update.message.reply_html(
        "🧪 <b>Vanya Group Chat Status</b>\n\n"
        f"{access}\n"
        f"{privacy}\n"
        f"{admin}\n\n"
        "<i>For non-admin groups, Telegram requires Group Privacy to be disabled. "
        "After disabling it in @BotFather, remove Vanya from the group and add her again.</i>"
    )

async def ping(update, context):
    """Show bot response latency and a simple service status."""
    started = time.perf_counter()
    msg = await update.message.reply_text("🏓 Checking ping…")
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    try:
        await msg.edit_text(
            f"🏓 <b>Pong!</b>\n\n⚡ Response: <code>{elapsed_ms} ms</code>\n🟢 Status: <b>Online</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass


# Modular handler imports. These are loaded after bot globals are defined,
# avoiding circular-import initialization races while keeping one runtime namespace.
from handlers.webapp import get_uno_webapp_url, uno, get_chess_webapp_url, chess, get_ludo_webapp_url, get_world_webapp_url, world_cmd, city, room, pet, ludo
from handlers.ui import kb, developer_button, home, start_menu, back, game_chat_kb, game_room_ui, log_event, _get_group_log_link, log_bot_membership, start, profile, safe_html
from handlers.economy import toprich, balance, daily, work, _leaderboard_since, _leaderboard_label, leaderboard_kb, _render_leaderboard, leaderboard, give, target_user, _protection_until, _is_dead, rob, protect, shield, propose, _complete_proposal_callback, accept, divorce, couple, topcouples
from handlers.moderation import is_admin, _moderation_ready, ban, unban, warn, mute, unmute, purge
from handlers.owner import staff_command_objects, is_owner_or_sudo, broadcast_target_kb, owner_panel_kb, owner_panel, owner_panel_command, _coin_admin_target, addcoins_admin, removecoins_admin, broadcast, addemoji, addsudo, delsudo, sudolist, auth, unauth, authlist, memory, remember_cmd, forgetme

async def main():
    await cleanup_expired_memory()
    web_runner = await start_web_server()
    # Configure the HTTP connection pool on the custom ProtectedBot itself.
    # ApplicationBuilder cannot change request pool settings after .bot(...).
    telegram_request = HTTPXRequest(connection_pool_size=32, pool_timeout=5)
    bot = ProtectedBot(TOKEN, request=telegram_request)
    app=(Application.builder().bot(bot)
         .concurrent_updates(16)
         .build())
    commands={
        "start":start,"help":help_cmd,"profile":profile,"bal":balance,
        "daily":daily,"work":work,"give":give,"toprich":toprich,"leaderboard":leaderboard,
        "rank":rank,"rob":rob,"protect":protect,"shield":shield,
        "kill":kill,"revive":revive,"topkill":topkill,
        "propose":propose,"accept":accept,"reject":reject,"divorce":divorce,"marriage":marriage,"couple":couple,"topcouples":topcouples,
        "rps":rps,"dice":dice,"coinflip":coinflip,"slots":slots,"jumble":jumble,
        "tap":tap,"bet":bet,"card":card,"cardjoin":cardjoin,"cardstart":cardstart,"cardcancel":cardcancel,"uno":uno,"unojoin":unojoin,"ludo":ludo,"ludojoin":ludojoin,
        "chess":chess,"chessjoin":chessjoin,"chat":chat,"gchat":gchat,"persona":persona,"memory":memory,"remember":remember_cmd,"forgetme":forgetme,"games":games_cmd,"spin":spin,"achievements":achievements,"quest":quest,
        "mines":mines,"wordseek":wordseek,"wordgrid":wordgrid,"crash":crash,"charades":charades,
        "wordchain":wordchain,"wordchainjoin":wordchain_join,"wordscramble":wordscramble,"hack":hack,
        "scribble":scribble,"kingdomwars":kingdomwars,"subway":street_rush_cmd,"city":city,"room":room,"pet":pet,"vanyacity":city,"myroom":room,"mypet":pet,
        "owner":owner_panel_command,"ownerpanel":owner_panel_command,"panel":owner_panel_command,"devpanel":owner_panel_command,"broadcast":broadcast,"addcoins":addcoins_admin,"removecoins":removecoins_admin,"addemoji":addemoji,"addsudo":addsudo,"delsudo":delsudo,"sudolist":sudolist,"auth":auth,"unauth":unauth,"authlist":authlist,"stats":stats,"ping":ping,
        "ban":ban,"unban":unban,"warn":warn,"mute":mute,"unmute":unmute,"purge":purge,"chatstatus":chatstatus,"end":end_game,
        "blacklist":blacklist,"unblacklist":unblacklist,
    }
    for name,fn in commands.items():
        app.add_handler(CommandHandler(name,fn))

    # /revealgrid is intentionally registered outside the public command map:
    # the handler exists, but Telegram must never advertise it to normal users.
    app.add_handler(CommandHandler("revealgrid", reveal_wordgrid))
    app.add_handler(CommandHandler("revealwordseek", reveal_wordseek))

    # Register the full command list with Telegram so typing "/" in ANY
    # group/private chat shows Vanya's available commands (like the
    # command suggestions shown by established bots).
    command_descriptions = {
        "start": "Start Vanya", "help": "Open help and command categories",
        "profile": "View your profile", "bal": "Check your balance",
        "daily": "Claim daily coins and XP", "work": "Work for coins", "give": "Give coins to another user",
        "toprich": "Show richest users", "leaderboard": "Show the leaderboard", "rank": "Show your rank",
        "rob": "Rob up to the target balance", "protect": "Buy 1d/2d protection", "shield": "Check protection time",
        "kill": "Kill a player for 50-100 coins", "revive": "Revive yourself for 500 coins", "topkill": "Show kill leaderboard",
        "propose": "Propose to another user", "accept": "Accept a proposal", "reject": "Reject a proposal",
        "divorce": "End a marriage", "marriage": "View marriage status", "couple": "Pair group players", "topcouples": "View group couples",
        "rps": "Play rock paper scissors", "dice": "Roll a dice", "coinflip": "Flip a coin",
        "slots": "Spin the slot machine", "card": "Create a 2-4 player Card Match", "cardjoin": "Join the Card Match", "cardstart": "Start the Card Match", "cardcancel": "Cancel the Card Match", "jumble": "Unscramble a word",
        "tap": "Play the tap challenge", "bet": "Place a virtual coin bet", "card": "Create a 2-4 player Card Match", "cardjoin": "Join the Card Match", "cardstart": "Start the Card Match", "cardcancel": "Cancel the Card Match", "uno": "Create an UNO room",
        "unojoin": "Join an UNO room", "ludo": "Open Ludo", "ludojoin": "Join a Ludo room",
        "chess": "Open Chess Mini App", "chessjoin": "Join a chess room", "chat": "Chat with Vanya",
        "gchat": "Send a game chat message", "persona": "Change chat persona", "memory": "View saved memory",
        "remember": "Save something to memory", "forgetme": "Clear your saved memory", "games": "Open Games",
        "spin": "Spin for a reward", "achievements": "View achievements", "quest": "View quests",
        "mines": "Play Mines", "wordseek": "Play Wordseek", "wordgrid": "Play Wordgrid",
        "crash": "Play Crash", "charades": "Play Charades", "wordchain": "Start multiplayer Wordchain", "wordchainjoin": "Join active Wordchain lobby",
        "wordscramble": "Play Wordscramble", "hack": "Play Hack puzzle",
        "scribble": "Open Scribble", "kingdomwars": "Open Kingdom Wars strategy arena", "subway": "Play Subway endless runner", "city": "Open Vanya City", "room": "Open your 3D room", "pet": "Open your 3D pet", "vanyacity": "Open Vanya City", "myroom": "Open your room", "mypet": "Open your pet", "owner": "Open owner panel",
        "stats": "View bot group and user statistics (Owner/Sudo only)",
        "panel": "Open owner panel", "ownerpanel": "Open owner panel", "devpanel": "Open owner panel", "broadcast": "Broadcast to users, groups, or both (Owner/Sudo)", "addcoins": "Add coins by user ID (Owner/Sudo)", "removecoins": "Remove coins by user ID (Owner/Sudo)", "addemoji": "Save premium custom emoji (Owner only)", "addsudo": "Add a sudo user",
        "delsudo": "Remove a sudo user", "sudolist": "List sudo users", "auth": "Authorize this group",
        "unauth": "Unauthorize this group", "authlist": "List authorized groups", "ping": "Check bot latency",
        "ban": "Ban a user", "unban": "Unban a user", "warn": "Warn a user", "mute": "Mute a user",
        "unmute": "Unmute a user", "purge": "Delete recent messages", "chatstatus": "Check group chat access", "end": "End all active games in this group",
        "blacklist": "Blacklist a user (Owner only)", "unblacklist": "Remove a user from blacklist (Owner only)",
    }
    command_list = [BotCommand(name, command_descriptions.get(name, "Vanya command")) for name in commands]
    # /revealgrid is not part of command_list at all, so it cannot leak
    # into any public command scope.
    # /end is a GROUP-ONLY command. Keep it out of private/default
    # command menus so it never appears as a web-app/private-chat command.
    public_command_list = [
        c for c in command_list
        if c.command not in STAFF_COMMANDS and c.command not in {"addemoji", "end"}
    ]
    group_command_list = public_command_list + [
        BotCommand("end", "End all active games in this group")
    ]

    # Clear previously registered public command menus first. This prevents
    # Telegram from retaining a stale /revealgrid or /end entry.
    await app.bot.delete_my_commands(scope=BotCommandScopeDefault())
    await app.bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
    await app.bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())

    await app.bot.set_my_commands(public_command_list, scope=BotCommandScopeDefault())
    await app.bot.set_my_commands(group_command_list, scope=BotCommandScopeAllGroupChats())
    await app.bot.set_my_commands(public_command_list, scope=BotCommandScopeAllPrivateChats())
    if OWNER_ID:
        await app.bot.set_my_commands(
            public_command_list + staff_command_objects(owner=True),
            scope=BotCommandScopeChat(chat_id=OWNER_ID),
        )
        for sudo_id in SUDO_IDS:
            await app.bot.set_my_commands(
                public_command_list + staff_command_objects(owner=False),
                scope=BotCommandScopeChat(chat_id=sudo_id),
            )

    # Blacklist guard runs before every normal message/command handler.
    # Owner is always exempt so /unblacklist can be used safely.
    app.add_handler(MessageHandler(filters.ALL, blacklist_message_guard, block=True), group=-3)
    app.add_handler(MessageHandler(filters.ALL, capture_owner_custom_emojis, block=False), group=-2)
    app.add_handler(MessageHandler(filters.ALL, track_incoming_chat, block=False), group=-1)
    app.add_handler(ChatMemberHandler(log_bot_membership, ChatMemberHandler.MY_CHAT_MEMBER), group=-1)
    app.add_handler(CallbackQueryHandler(blacklist_callback_guard, block=True), group=-3)
    app.add_handler(CallbackQueryHandler(callback))

    # Word games accept a plain typed word. This handler runs before Vanya's
    # normal chat handler and only does anything when a word game is active.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, direct_game_answer), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mention_chat), group=1)
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("✦ ItzVanyaBot Ultimate started ✦")
    global _AI_LOGGER_BOT
    _AI_LOGGER_BOT = app.bot
    provider_status = await probe_ai_providers()
    # Startup log is sent only after Telegram initialization/polling succeeds.
    await log_event(
        type("StartupContext", (), {"bot": app.bot})(),
        "🚀 <b>VANYA BOT STARTED</b>\n\n"
        "🟢 Status: <b>Online</b>\n"
        "⚡ Telegram polling: <b>Active</b>\n"
        "🎮 Games: <b>Ready</b>\n\n"
        f"🤖 <b>Elite LLM:</b> {'🟢 ACTIVE' if provider_status.get('elite') else '🔴 DOWN'}\n"
        f"   Model: <code>{html.escape(ELITE_LLM_MODEL or AI_MODEL or 'unset')}</code>\n"
        f"   Key configured: <b>{'YES' if ELITE_LLM_API_KEY else 'NO'}</b>\n"
        f"🔁 <b>ChatGP Fallback:</b> {'🟢 ACTIVE' if provider_status.get('chatgp') else '🔴 DOWN'}\n"
        f"   Key configured: <b>{'YES' if CHATGP_API_KEY else 'NO'}</b>"
    )
    await asyncio.Event().wait()

if __name__=="__main__":
    import asyncio
    asyncio.run(main())
