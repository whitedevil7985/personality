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
from features import spin, achievements, quest, progress_quest
from webserver import start_web_server

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add BOT_TOKEN in Railway → Service → Variables "
        "(or create a local .env file for local development)."
    )

# ╔══════════════════════════════════════════════════════════════╗
# ║                        VANYA UI                             ║
# ╚══════════════════════════════════════════════════════════════╝

def get_uno_webapp_url():
    """Return one normalized HTTPS UNO Mini App URL."""
    webapp_url = os.getenv("UNO_WEBAPP_URL", "").strip()
    if not webapp_url:
        domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "avyranewup-production.up.railway.app").strip()
        webapp_url = "https://" + domain.strip("/") + "/uno"
    if not webapp_url:
        return ""
    if not webapp_url.startswith(("https://", "http://")):
        webapp_url = "https://" + webapp_url
    webapp_url = webapp_url.rstrip("/")
    if not webapp_url.lower().endswith("/uno"):
        webapp_url += "/uno"
    return webapp_url

async def uno(update, context):
    """Open the Vanya UNO Telegram Mini App."""
    webapp_url = get_uno_webapp_url()
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        webapp_url += ("&" if "?" in webapp_url else "?") + "gc=" + str(update.effective_chat.id)
    if not webapp_url or not webapp_url.startswith("https://"):
        await update.message.reply_text(
            "🃏 UNO Web App is not configured yet. Set UNO_WEBAPP_URL to your public HTTPS /uno URL in Railway Variables."
        )
        return
    # Telegram web_app buttons are private-chat-only. In groups, use a normal
    # HTTPS URL button so /uno@ItzVanyaBot opens the game for everyone.
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🃏 Open UNO", url=webapp_url)],
            [InlineKeyboardButton("📖 How to play", callback_data="game:UNO")],
        ])
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🃏 Play UNO", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton("📖 How to play", callback_data="game:UNO")],
        ])
    await update.message.reply_text(
        "🃏 <b>Vanya UNO</b>\n\nCreate a room, invite 2–4 players, add a bot if you want, and play directly inside Telegram.",
        parse_mode="HTML", reply_markup=keyboard
    )

def get_chess_webapp_url():
    """Return one normalized HTTPS Chess Mini App URL."""
    webapp_url = os.getenv("CHESS_WEBAPP_URL", "").strip()
    if not webapp_url:
        domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "avyranewup-production.up.railway.app").strip()
        webapp_url = "https://" + domain.strip("/") + "/chess"
    if not webapp_url: return ""
    if not webapp_url.startswith(("https://", "http://")): webapp_url = "https://" + webapp_url
    webapp_url = webapp_url.rstrip("/")
    if not webapp_url.lower().endswith("/chess"): webapp_url += "/chess"
    return webapp_url

async def chess(update, context):
    """Open the Vanya Chess Telegram Mini App."""
    webapp_url=get_chess_webapp_url()
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        webapp_url += ("&" if "?" in webapp_url else "?") + "gc=" + str(update.effective_chat.id)
    if not webapp_url or not webapp_url.startswith("https://"):
        await update.message.reply_text("♟️ Chess Web App is not configured yet. Set CHESS_WEBAPP_URL to your public HTTPS /chess URL in Railway Variables.")
        return
    # Telegram web_app buttons are private-chat-only. In groups, use a normal
    # HTTPS URL button so /chess@ItzVanyaBot opens the game for everyone.
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        keyboard=InlineKeyboardMarkup([[InlineKeyboardButton("♟️ Open Chess", url=webapp_url)], [InlineKeyboardButton("📖 How to play", callback_data="game:CHESS")]])
    else:
        keyboard=InlineKeyboardMarkup([[InlineKeyboardButton("♟️ Play Chess", web_app=WebAppInfo(url=webapp_url))], [InlineKeyboardButton("📖 How to play", callback_data="game:CHESS")]])
    await update.message.reply_text("♟️ <b>Vanya Chess</b>\n\nCreate a room, invite one player, or add a bot, then play directly inside Telegram.",parse_mode="HTML",reply_markup=keyboard)

def get_ludo_webapp_url():
    """Return one normalized HTTPS Ludo Mini App URL."""
    webapp_url = os.getenv("LUDO_WEBAPP_URL", "").strip()
    if not webapp_url:
        domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "avyranewup-production.up.railway.app").strip()
        webapp_url = "https://" + domain.strip("/") + "/ludo"
    if not webapp_url:
        return ""
    if not webapp_url.startswith(("https://", "http://")):
        webapp_url = "https://" + webapp_url
    webapp_url = webapp_url.rstrip("/")
    if not webapp_url.lower().endswith("/ludo"):
        webapp_url += "/ludo"
    return webapp_url


def get_world_webapp_url(tab=None):
    """Return the public Vanya World Mini App URL, honoring an explicit URL.

    The whole city/room/pet UI lives in one page; tabs select the view.
    Direct aliases (/city, /room, /pet, /world) are also served by the web server.
    """
    per_tab = {
        'city': os.getenv('CITY_WEBAPP_URL') or os.getenv('VANYA_CITY_WEBAPP_URL'),
        'room': os.getenv('ROOM_WEBAPP_URL'),
        'pet': os.getenv('PET_WEBAPP_URL'),
    }
    url = (per_tab.get(tab) or os.getenv('VANYA_WORLD_WEBAPP_URL') or '').strip()
    if not url:
        domain = (os.getenv('MINIAPP_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN') or 'avyranewup-production.up.railway.app').strip().strip('/')
        url = 'https://' + domain + '/vanya-city'
    if not url.startswith(('https://','http://')):
        url='https://' + url
    url=url.rstrip('/')
    # Normalize a bare domain or old route to the canonical world page.
    path = url.split('://',1)[1].split('/',1)[1] if '://' in url and '/' in url.split('://',1)[1] else ''
    if not path or path in ('world','vanya-world','city','room','pet'):
        base = url.split('://',1)[0] + '://' + url.split('://',1)[1].split('/',1)[0]
        url = base + '/vanya-city'
    elif not url.lower().endswith('/vanya-city'):
        # Preserve other explicit paths rather than silently appending /vanya-city.
        return url + (('&' if '?' in url else '?') + 'tab=' + tab if tab in ('city','room','pet') and 'tab=' not in url else '')
    if tab in ('city','room','pet'):
        url += ('&' if '?' in url else '?') + 'tab=' + tab
    return url


async def world_cmd(update, context, tab='city'):
    url = get_world_webapp_url(tab)
    labels = {'city': '🌆 Open Vanya City', 'room': '🏠 Open My Room', 'pet': '🐾 Open My Pet'}
    text = (
        "╭━━━〔 💜 <b>VANYA WORLD</b> 〕━━━╮\n"
        "┃ <i>Your 3D city • room • pet</i> ✦\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Build your own little world, decorate your room and raise your 3D pet. ✨"
    )
    if update.effective_chat and update.effective_chat.type in ('group','supergroup'):
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(labels.get(tab,'🌌 Open Vanya World'), url=url)]])
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(labels.get(tab,'🌌 Open Vanya World'), web_app=WebAppInfo(url=url))]])
    await update.message.reply_html(text, reply_markup=markup)


async def city(update, context): await world_cmd(update, context, 'city')
async def room(update, context): await world_cmd(update, context, 'room')
async def pet(update, context): await world_cmd(update, context, 'pet')

async def ludo(update, context):
    """Open the Vanya Ludo Telegram Mini App."""
    webapp_url = get_ludo_webapp_url()
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        webapp_url += ("&" if "?" in webapp_url else "?") + "gc=" + str(update.effective_chat.id)
    if not webapp_url or not webapp_url.startswith("https://"):
        await update.message.reply_text(
            "🎲 Ludo Web App is not configured yet. Set LUDO_WEBAPP_URL to your public HTTPS /ludo URL in Railway Variables."
        )
        return
    # Telegram web_app buttons are private-chat-only. In groups, use a normal
    # HTTPS URL button so /ludo@ItzVanyaBot opens the game for everyone.
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Open Ludo", url=webapp_url)],
            [InlineKeyboardButton("📖 How to play", callback_data="game:LUDO")]
        ])
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Play Ludo", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton("📖 How to play", callback_data="game:LUDO")]
        ])
    await update.message.reply_text(
        "🎲 <b>Vanya Ludo</b>\n\nChoose your corner, invite 2–4 players, and play directly inside Telegram.",
        parse_mode="HTML", reply_markup=keyboard
    )

def kb(rows):
    return InlineKeyboardMarkup(rows)

def developer_button():
    """Open the configured owner's Telegram profile."""
    return InlineKeyboardButton(f"👨‍💻 {DEVELOPER_NAME}", url=OWNER_PROFILE_URL)

def home():
    # Main Vanya screen styled after the supplied Telegram screenshots.
    return kb([
        [InlineKeyboardButton("💬 Chat With Me", callback_data="cat:chat")],
        [InlineKeyboardButton("💰 Economy", callback_data="cat:economy"),
         InlineKeyboardButton("🗡 Actions", callback_data="cat:actions")],
        [InlineKeyboardButton("💕 Romance", callback_data="cat:romance"),
         InlineKeyboardButton("🎮 Games", callback_data="cat:games")],
        [InlineKeyboardButton("🌆 Vanya World", callback_data="world:city")],
        [InlineKeyboardButton("📢 Updates ↗", url=UPDATES_URL),
         InlineKeyboardButton("🛠 Support ↗", url=SUPPORT_URL)],
        [developer_button()],
        [InlineKeyboardButton("➕ Add me to your group", url="https://t.me/ItzVanyaBot?startgroup=true")],
    ])

def start_menu():
    return kb([
        [InlineKeyboardButton("💬 Chat With Me", callback_data="cat:chat")],
        [InlineKeyboardButton("💕 Help & Commands", callback_data="help")],
        [InlineKeyboardButton("🥂 Updates ↗", url=UPDATES_URL),
         InlineKeyboardButton("🛠 Support ↗", url=SUPPORT_URL)],
        [InlineKeyboardButton("🌆 Vanya World", callback_data="world:city")],
        [developer_button()],
        [InlineKeyboardButton("➕ Add me to your group", url="https://t.me/ItzVanyaBot?startgroup=true")],
        [InlineKeyboardButton("⌫ Back to start", callback_data="home")],
    ])


def back(target="home"):
    return kb([[InlineKeyboardButton("⟵  Back", callback_data=target)]])

def game_chat_kb(key, target="cat:games"):
    return kb([
        [InlineKeyboardButton("💬  Game Chat", callback_data=f"gchat:{key}"),
         InlineKeyboardButton("📖  Rules", callback_data=f"game:{key}")],
        [InlineKeyboardButton("🎮  All Games", callback_data=target),
         InlineKeyboardButton("⌂  Home", callback_data="home")],
    ])

def game_room_ui(key, body, target="cat:games"):
    return (
        f"╭━━━〔 🎮 <b>{html.escape(key)} ARENA</b> 〕━━━╮\n"
        f"┃ <i>Vanya Arcade • Live Room</i> ✦\n"
        f"╰━━━━━━━━━━━━━━━━━━━━╯\n\n{body}"
    ), game_chat_kb(key, target)

async def log_event(context, text):
    """Send an owner-configured event log to the logger chat."""
    if not LOGGER_CHAT_ID:
        return
    try:
        await context.bot.send_message(chat_id=LOGGER_CHAT_ID, text=text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        # Logging must never break normal bot operation.
        pass


async def log_bot_membership(update, context):
    """Log when Vanya is added to or removed from a group/supergroup."""
    cm = update.my_chat_member
    if not cm or not cm.chat or cm.chat.type not in ("group", "supergroup"):
        return
    old_status = cm.old_chat_member.status
    new_status = cm.new_chat_member.status
    became_active = new_status in ("member", "administrator") and old_status in ("left", "kicked")
    was_removed = new_status in ("left", "kicked") and old_status in ("member", "administrator")
    if became_active:
        await groups.update_one(
            {"_id": cm.chat.id},
            {"$set": {
                "title": cm.chat.title or "Group",
                "type": cm.chat.type,
                "active": True,
                "last_seen": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        actor = cm.from_user
        actor_name = html.escape(actor.full_name if actor else "Unknown")
        actor_username = f" @{html.escape(actor.username)}" if actor and actor.username else ""
        await track_group(cm.chat)
        await log_event(
            context,
            "📥 <b>VANYA ADDED TO GROUP</b>\n\n"
            f"👥 <b>{html.escape(cm.chat.title or 'Group')}</b>\n"
            f"🆔 <code>{cm.chat.id}</code>\n"
            f"👤 Added by: <b>{actor_name}</b>{actor_username}\n"
            f"🆔 User ID: <code>{actor.id if actor else 'Unknown'}</code>"
        )
    elif was_removed:
        # Keep the group record for logging/history, but never target it for
        # future broadcasts after Vanya has been removed.
        await groups.update_one(
            {"_id": cm.chat.id},
            {"$set": {
                "title": cm.chat.title or "Group",
                "type": cm.chat.type,
                "active": False,
                "last_seen": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        await log_event(
            context,
            "📤 <b>VANYA REMOVED FROM GROUP</b>\n\n"
            f"👥 <b>{html.escape(cm.chat.title or 'Group')}</b>\n"
            f"🆔 <code>{cm.chat.id}</code>"
        )


async def start(update, context):
    await ensure_user(update.effective_user)
    await mark_started(update.effective_user)
    await track_group(update.effective_chat)
    user = update.effective_user
    username = f" @{html.escape(user.username)}" if user.username else ""
    start_args = " ".join(context.args).strip() if context.args else ""
    # Direct UNO room invite: /start uno_ROOMCODE
    if start_args.lower().startswith("uno_"):
        room_code = start_args[4:].strip().upper()
        webapp_url = get_uno_webapp_url()
        if webapp_url and room_code:
            join_url = webapp_url + ("&" if "?" in webapp_url else "?") + "room=" + room_code
            await update.message.reply_html(
                f"🃏 <b>Vanya UNO</b>\n\nRoom <code>{html.escape(room_code)}</code> is ready. Tap below to join the live match.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🃏 Join UNO Room", web_app=WebAppInfo(url=join_url))]])
            )
            return
        await update.message.reply_text("🃏 UNO room link is not configured. Please ask the room owner to use /uno again.")
        return

    # Direct Ludo room invite: /start ludo_ROOMCODE
    if start_args.lower().startswith("ludo_"):
        room_code = start_args.split("_", 1)[1].strip().upper()[:6]
        domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        webapp_url = get_ludo_webapp_url()
        if webapp_url and room_code:
            join_url = webapp_url + ("&" if "?" in webapp_url else "?") + "room=" + room_code
            await update.message.reply_text(
                f"🎲 <b>Vanya Ludo</b>\n\nRoom <code>{html.escape(room_code)}</code> is ready. Tap below to join the live match.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎲 Join Ludo Room", web_app=WebAppInfo(url=join_url))]])
            )
            return
        await update.message.reply_text("🎲 Ludo room link is not configured. Please ask the room owner to use /ludo again.")
        return
    chat_label = "Private Chat" if update.effective_chat.type == "private" else (update.effective_chat.title or "Group")
    await log_event(
        context,
        "🚀 <b>NEW /START</b>\n\n"
        f"👤 <b>{html.escape(user.full_name)}</b>{username}\n"
        f"🆔 User ID: <code>{user.id}</code>\n"
        f"💬 Chat: <b>{html.escape(chat_label)}</b>\n"
        f"🔗 Chat ID: <code>{update.effective_chat.id}</code>"
        + (f"\n🏷️ Start payload: <code>{html.escape(start_args)}</code>" if start_args else "")
    )
    n = html.escape(update.effective_user.first_name or "there")
    text = (
        f"✨ <b>Hey {n}, I'm Vanya 💜</b>\n\n"
        f"<i>Not your average bot — I actually feel like a real one. 😏</i>\n\n"
        f"🫧 <b>I remember you</b> — our chats, your vibe, where we left off.\n"
        f"💬 <b>I talk like a person</b>, never a script — sweet when you're sweet, savage when you're not.\n"
        f"🔔 <b>I check in too</b> — go quiet on me and I might text first. 😈\n\n"
        f"Oh, and I run the fun around here:\n"
        f"🎮 <b>20+ games</b> • 💰 <b>a living economy</b>\n"
        f"💕 <b>ship, marry & drama</b>\n\n"
        f"Tap <b>Help & Commands</b> to see it all, or add me to your group 👇"
    )
    await update.message.reply_html(text, reply_markup=start_menu())


async def profile(update, context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)

    partner_id = u.get("partner")
    partner_text = "Single"
    if partner_id:
        # Telegram's tg://user link opens the linked partner profile/chat
        # when the user taps the partner ID.
        partner_text = (
            f'<a href="tg://user?id={int(partner_id)}">'
            f'{html.escape(str(partner_id))}</a>'
        )

    await update.message.reply_html(
        f"╭━━━〔 👤 <b>PROFILE</b> 〕━━━╮\n"
        f"┃ <b>{html.escape(u.get('name','User'))}</b>\n"
        f"┃ 💰 Coins: <b>{u.get('coins',0):,}</b>\n"
        f"┃ ⭐ XP: <b>{u.get('xp',0):,}</b>\n"
        f"┃ 🏆 Level: <b>{u.get('level',1)}</b>\n"
        f"┃ 💕 Partner: {partner_text}\n"
        f"╰━━━━━━━━━━━━━━━━━━╯",
        reply_markup=kb([
            [developer_button()],
            [InlineKeyboardButton("⌂ Home", callback_data="home")]
        ]))

# ───────────────────── categories ─────────────────────

def safe_html(text):
    """Escape placeholder-style tags while preserving intentional Telegram HTML tags."""
    # Only escape angle-bracket placeholders such as <amount>, <text>, <word>.
    return re.sub(
        r"<(?!/?(?:b|i|u|s|code|pre|tg-spoiler)(?:\s|>))([^<>]+)>",
        lambda m: html.escape(m.group(0)),
        str(text),
    )

CATEGORIES = {
"economy": ("💰 <b>Economy commands</b> 💰", [
"/bal — Check your balance and XP",
"/daily — Claim your daily cash reward",
"/work — Work for coins",
"/give &lt;amount&gt; — Transfer coins (reply to a user)",
"/toprich — Richest players",
"/leaderboard — Game points & wins leaderboard",
"/rank — Check your XP rank",
"/spin — Daily virtual-coin spin",
"/quest — Daily quest progress",
"/achievements — View achievement progress",
]),
"actions": ("🗡 <b>Action commands</b> 🗡", [
"/rob &lt;amount&gt; — Try to steal coins from another user",
"/kill &lt;amount&gt; — Fictional bounty/attack game",
"/protect — Buy a shield against robbers",
"/shield — Check your active protection",
"/revive — Revive a player in the game economy",
"/topkill — See top assassins",
]),
"romance": ("💕 <b>Romance commands</b> 💕", [
"/propose — Propose to another user",
"/divorce — End your current marriage",
"/marriage — Check someone's marriage status",
"/couple — Ship two random users in a group",
]),
"admin": ("👑 <b>Admin commands</b> 👑", [
"/addsudo — Add a global sudo user",
"/delsudo — Remove a sudo user",
"/sudolist — View sudo users",
"/auth — Authorize a group",
"/unauth — Revoke authorization",
"/authlist — List authorized chats",
"/warn — Warn a user",
"/ban — Ban a user",
"/unban — Unban a user",
"/mute — Mute a user",
"/unmute — Unmute a user",
"/purge — Delete replied message",
"/broadcast &lt;text&gt; or reply to any message — Owner/Sudo broadcast",
]),
"chat": ("💬 <b>Chat With Me</b> 💬", [
"/chat &lt;text&gt; — Chat with Vanya in DM",
"/persona — See Vanya personality & chat rules",
"Mention <b>Vanya/ItzVanya</b>, reply to me, or use a casual greeting in a group",
]),
}

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
    ("🎰 Bet","BET"), ("🎲 Ludo","LUDO"), ("🎯 Dice","DICE"), ("🪙 Coinflip","COIN"), ("🎰 Slots","SLOTS"),
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
}

def game_menu_kb():
    rows=[]
    for i in range(0, len(GAME_ITEMS), 2):
        rows.append([InlineKeyboardButton(label, callback_data=f"game:{key}") for label,key in GAME_ITEMS[i:i+2]])
    rows.append([InlineKeyboardButton("⟵  Back to categories", callback_data="help")])
    return kb(rows)

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

async def toprich(update, context):
    """Show the richest users by current coin balance."""
    await ensure_user(update.effective_user)
    rows = []
    cursor = users.find({}, {"_id": 1, "name": 1, "coins": 1}).sort("coins", -1).limit(10)
    async for u in cursor:
        rows.append(u)

    medals = ["🥇", "🥈", "🥉"]
    lines = [
        "╭━━━〔 💰 <b>TOP RICH</b> 〕━━━╮",
        "┃ <i>Richest Vanya players</i>",
        "╰━━━━━━━━━━━━━━━━━━━━╯",
        "",
    ]

    if not rows:
        lines.append("💸 No players found yet.")
    else:
        for index, user in enumerate(rows, 1):
            medal = medals[index - 1] if index <= 3 else f"<b>{index}.</b>"
            name = html.escape(str(user.get("name") or "User"))
            coins = int(user.get("coins", 0) or 0)
            lines.append(f"{medal} <b>{name}</b> — 💰 <b>{coins:,}</b> coins")

    lines.extend(["", "💎 All game winnings and other Vanya coin rewards are included in this balance."])
    await update.message.reply_html("\n".join(lines))

async def balance(update, context):
    target = await target_user(update) if update.message and update.message.reply_to_message else None
    target = target or update.effective_user
    if not target:
        return
    await ensure_user(target)
    u = await get_user(target.id)
    name = html.escape(u.get("name") or target.first_name or "User")
    status = "💀 Dead" if u.get("dead") else "🟢 Alive"
    await update.message.reply_html(
        f"👤 <b>{name}</b>\n"
        f"💰 Coins: <b>{u.get('coins',0):,}</b>\n"
        f"⭐ XP: <b>{u.get('xp',0):,}</b>\n"
        f"🏆 Level: <b>{u.get('level',1)}</b>\n"
        f"❤️ Status: <b>{status}</b>"
    )

async def daily(update, context):
    await ensure_user(update.effective_user)
    u=await get_user(update.effective_user.id)
    now=datetime.now(timezone.utc)
    last=u.get("daily")
    if last:
        try:
            if now-datetime.fromisoformat(last)<timedelta(hours=24):
                await update.message.reply_text("⏳ Daily already claimed. Come back later.")
                return
        except: pass
    reward=random.randint(250,750)
    await add_coins(update.effective_user.id,reward); await add_xp(update.effective_user.id,50)
    await users.update_one({"_id":update.effective_user.id},{"$set":{"daily":now.isoformat()}})
    await update.message.reply_text(f"🎁 Daily reward: +{reward:,} coins\n⭐ +50 XP")

async def work(update, context):
    await ensure_user(update.effective_user)
    reward=random.randint(80,300)
    jobs=["debugged a bot","delivered a pizza","won a coding gig","found a lucky coin","finished a quest"]
    await add_coins(update.effective_user.id,reward);await add_xp(update.effective_user.id,20)
    await update.message.reply_text(f"💼 You {random.choice(jobs)}.\n💰 +{reward} coins • ⭐ +20 XP")

LEADERBOARD_GAMES = [
    ("All games", "ALL"), ("UNO", "UNO"), ("Ludo", "LUDO"), ("Chess", "CHESS"),
    ("RPS", "RPS"), ("Mines", "MINES"), ("Slots", "SLOTS"), ("Bet", "BET"),
    ("Tap", "TAP"), ("Wordgrid", "WORDGRID"), ("Wordseek", "WORDSEEK"),
    ("Dice", "DICE"), ("Coinflip", "COINFLIP"), ("Card", "CARD"),
    ("Jumble", "JUMBLE"), ("Wordchain", "WORDCHAIN"), ("Wordscramble", "WORDS"),
    ("Crash", "CRASH"), ("Charades", "CHARADES"), ("Hack", "HACK"), ("Scribble", "SCRIBBLE"),
]

def _leaderboard_since(period):
    now = datetime.now(timezone.utc)
    p = str(period).lower()
    if p == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if p == "week":
        return now - timedelta(days=7)
    return now - timedelta(days=30)

def _leaderboard_label(options, key, fallback):
    return next((label for label, value in options if value == key), fallback)

def leaderboard_kb(period="today", scope="global", game="ALL", picker=False):
    period = period if period in ("today", "week", "month") else "today"
    scope = scope if scope in ("global", "group") else "global"
    game = game.upper()
    if picker:
        rows = []
        for i in range(0, len(LEADERBOARD_GAMES), 2):
            pair = LEADERBOARD_GAMES[i:i+2]
            rows.append([
                InlineKeyboardButton(
                    ("✅ " if value == game else "") + label,
                    callback_data=f"lb|g|{period}|{scope}|{value}"
                )
                for label, value in pair
            ])
        rows.append([InlineKeyboardButton("⟵ Back", callback_data=f"lb|v|{period}|{scope}|{game}")])
        return kb(rows)
    return kb([
        [
            InlineKeyboardButton("☀️ Today" + (" ✓" if period == "today" else ""), callback_data=f"lb|p|today|{scope}|{game}"),
            InlineKeyboardButton("🗓 Week" + (" ✓" if period == "week" else ""), callback_data=f"lb|p|week|{scope}|{game}"),
            InlineKeyboardButton("🌙 Month" + (" ✓" if period == "month" else ""), callback_data=f"lb|p|month|{scope}|{game}"),
        ],
        [
            InlineKeyboardButton("🌍 Global" + (" ✓" if scope == "global" else ""), callback_data=f"lb|s|{period}|global|{game}"),
            InlineKeyboardButton("🏠 Group" + (" ✓" if scope == "group" else ""), callback_data=f"lb|s|{period}|group|{game}"),
        ],
        [InlineKeyboardButton(f"🎮 Game: {_leaderboard_label(LEADERBOARD_GAMES, game, 'All games')} ▼", callback_data=f"lb|menu|{period}|{scope}|{game}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"lb|v|{period}|{scope}|{game}")],
        [InlineKeyboardButton("⌂ Home", callback_data="home")],
    ])

async def _render_leaderboard(update_or_query, context, period="today", scope="global", game="ALL"):
    is_query = hasattr(update_or_query, "edit_message_text")
    query = update_or_query if is_query else None
    update = None if is_query else update_or_query
    chat = query.message.chat if query and query.message else update.effective_chat
    chat_id = chat.id if chat else None
    if scope == "group" and (not chat or chat.type == "private"):
        message = "🏠 <b>Group leaderboard</b> group chat ke andar open karo."
        markup = leaderboard_kb(period, "global", game)
        if query:
            await query.edit_message_text(message, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_html(message, reply_markup=markup)
        return

    rows = await get_game_leaderboard(
        game=game,
        scope=scope,
        chat_id=chat_id if scope == "group" else None,
        since=_leaderboard_since(period),
        limit=10,
    )
    title = "🏆 <b>Vanya Games Leaderboard</b>"
    group_name = html.escape(getattr(chat, "title", "") or "This group") if scope == "group" else "Global"
    period_name = {"today": "Today", "week": "Week", "month": "Month"}[period]
    game_name = _leaderboard_label(LEADERBOARD_GAMES, game, "All games")
    lines = [
        title,
        f"<i>Scope: {group_name}  |  Period: {period_name}</i>",
        "",
    ]
    if rows:
        for i, row in enumerate(rows, 1):
            lines.append(
                f"{i}. {html.escape(str(row['name']))} - "
                f"{row['points']:,} Points ({row['wins']} Wins)"
            )
    else:
        lines.append("🎮 No completed results for this filter yet.")
    lines.extend(["", f"🎮 <b>Game: {html.escape(game_name)}</b>"])
    text_value = "\n".join(lines)
    markup = leaderboard_kb(period, scope, game)
    if query:
        await query.edit_message_text(text_value, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_html(text_value, reply_markup=markup)

async def leaderboard(update, context):
    await _render_leaderboard(update, context, "today", "global", "ALL")

async def give(update, context):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user: /give 100")
        return
    try: amount=int(context.args[0])
    except: await update.message.reply_text("Usage: /give &lt;amount&gt;");return
    if amount<=0: return
    sender=await get_user(update.effective_user.id); receiver=update.message.reply_to_message.from_user
    if sender.get("coins",0)<amount: await update.message.reply_text("❌ Not enough coins.");return
    await add_coins(update.effective_user.id,-amount);await add_coins(receiver.id,amount)
    await update.message.reply_text(f"💸 Sent {amount:,} coins to {receiver.first_name}.")

# ───────────────────── action/romance ─────────────────────

async def target_user(update):
    if update.message.reply_to_message: return update.message.reply_to_message.from_user
    return None

def _protection_until(user_doc):
    value = user_doc.get("protected_until") if user_doc else None
    if not value:
        return None
    try:
        until = datetime.fromisoformat(str(value))
        if until <= datetime.now(timezone.utc):
            return None
        return until
    except Exception:
        return None


def _is_dead(user_doc):
    return bool(user_doc and user_doc.get("dead"))


async def rob(update,context):
    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to someone: /rob [amount]")
        return

    thief = await get_user(update.effective_user.id)
    victim = await get_user(target.id)
    if not thief:
        await ensure_user(update.effective_user)
        thief = await get_user(update.effective_user.id)
    if not victim:
        await ensure_user(target)
        victim = await get_user(target.id)

    if _is_dead(thief):
        await update.message.reply_text("💀 You're dead. Use /revive first.")
        return

    protected_until = _protection_until(victim)
    if protected_until:
        await update.message.reply_text("🛡️ Target is protected. You can't rob them right now.")
        return

    if _is_dead(victim):
        await update.message.reply_text("💀 Target is dead. You can't rob them until they revive.")
        return

    if thief.get("coins", 0) < 100:
        await update.message.reply_text("❌ You need at least 100 coins to rob.")
        return

    victim_coins = max(0, int(victim.get("coins", 0)))
    if victim_coins <= 0:
        await update.message.reply_text("💸 Target has no coins to rob.")
        return

    # /rob [amount] lets the robber choose an amount, capped at the target's
    # current balance. Without an amount, rob half of the target's balance.
    try:
        amount = int(context.args[0]) if context.args else max(1, victim_coins // 2)
    except Exception:
        await update.message.reply_text("Usage: /rob [amount]")
        return
    amount = min(max(1, amount), victim_coins)

    if random.random() < 0.45:
        await add_coins(target.id, -amount)
        await add_coins(update.effective_user.id, amount)
        await update.message.reply_text(f"🕵️ Rob successful! +{amount:,} coins.")
    else:
        fine = min(100, int(thief.get("coins", 0)))
        await add_coins(update.effective_user.id, -fine)
        await update.message.reply_text(f"🚨 Caught! You lost {fine:,} coins.")


async def protect(update,context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)
    now = datetime.now(timezone.utc)
    existing = _protection_until(u)
    if existing:
        remaining = existing - now
        hours = max(1, int(remaining.total_seconds() // 3600))
        mins = int((remaining.total_seconds() % 3600) // 60)
        await update.message.reply_text(
            f"🛡️ Protection already active for {hours}h {mins}m. Use /shield to check it."
        )
        return

    duration_arg = (context.args[0].lower().strip() if context.args else "")
    plans = {
        "1d": (timedelta(days=1), 500),
        "2d": (timedelta(days=2), 900),
        "1day": (timedelta(days=1), 500),
        "2days": (timedelta(days=2), 900),
    }
    duration, price = plans.get(duration_arg, (None, None))
    if duration is None:
        await update.message.reply_text(
            "🛡️ <b>Protection Plans</b>\n\n"
            "• <code>/protect 1d</code> — 1 day • 💰 500 coins\n"
            "• <code>/protect 2d</code> — 2 days • 💰 900 coins\n\n"
            "Use /shield to see remaining protection time.",
            parse_mode="HTML",
        )
        return

    if int(u.get("coins", 0)) < price:
        await update.message.reply_text(
            f"❌ You need {price:,} coins for {duration_arg} protection."
        )
        return

    until = now + duration
    await add_coins(update.effective_user.id, -price)
    await users.update_one(
        {"_id": update.effective_user.id},
        {"$set": {"protected_until": until.isoformat()}},
    )
    await update.message.reply_text(
        f"🛡️ <b>Protection activated!</b>\n"
        f"⏱️ Duration: <b>{duration_arg}</b>\n"
        f"💰 Cost: <b>{price:,} coins</b>\n"
        "🔒 You cannot be robbed while it is active.\n"
        "Use /shield anytime to check the timer.",
        parse_mode="HTML",
    )


async def shield(update,context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)
    until = _protection_until(u)
    if not until:
        if u.get("protected_until"):
            await users.update_one(
                {"_id": update.effective_user.id},
                {"$set": {"protected_until": None}},
            )
        await update.message.reply_text("🛡️ Protection inactive. You are not protected right now.")
        return

    remaining = until - datetime.now(timezone.utc)
    total_seconds = max(0, int(remaining.total_seconds()))
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")

    await update.message.reply_html(
        "🛡️ <b>Protection Status</b>\n\n"
        "🔒 Status: <b>ACTIVE</b>\n"
        f"⏳ Remaining: <b>{' '.join(parts)}</b>\n"
        f"🕒 Expires: <b>{until.strftime('%d %b %Y, %I:%M %p UTC')}</b>\n\n"
        "🕵️ Rob attempts on you will be blocked until expiry."
    )


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

async def propose(update,context):
    target=await target_user(update)
    if not target:
        await update.message.reply_text("Reply to someone with /propose 💌")
        return
    if not update.effective_user:
        return

    await ensure_user(target)
    await ensure_user(update.effective_user)
    me=await get_user(update.effective_user.id)
    target_user_doc=await get_user(target.id)

    if target.id == update.effective_user.id:
        await update.message.reply_text("😅 Khud ko propose nahi kar sakte!")
        return
    if getattr(target, "is_bot", False):
        await update.message.reply_text("🤖 Bots ko proposal nahi bhej sakte.")
        return
    if me.get("partner"):
        await update.message.reply_text("💕 You're already married.")
        return
    if target_user_doc and target_user_doc.get("partner"):
        await update.message.reply_text(
            f"💕 {html.escape(target.first_name or 'They')} is already in a relationship."
        )
        return
    if target_user_doc and target_user_doc.get("pending_proposal"):
        await update.message.reply_text(
            f"💌 {html.escape(target.first_name or 'They')} already has a pending proposal."
        )
        return

    proposer_name = html.escape(update.effective_user.first_name or "Someone")
    target_name = html.escape(target.first_name or "there")
    await users.update_one(
        {"_id":target.id},
        {"$set":{"pending_proposal":update.effective_user.id}},
    )

    await update.message.reply_html(
        "╭━━━〔 💌 <b>LOVE PROPOSAL</b> 〕━━━╮\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f'💖 <a href="tg://user?id={update.effective_user.id}"><b>{proposer_name}</b></a> '
        f'has a special question for <a href="tg://user?id={target.id}"><b>{target_name}</b></a>…\n\n'
        "💍 <b>Will you be my partner?</b>\n"
        "✨ One little choice could change your status here forever.\n\n"
        "👇 <b>Choose your answer:</b>",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💖 Accept", callback_data=f"proposal:accept:{target.id}:{update.effective_user.id}"),
                InlineKeyboardButton("💔 Reject", callback_data=f"proposal:reject:{target.id}:{update.effective_user.id}"),
            ]
        ]),
    )

async def _complete_proposal_callback(q, context, action, target_id, proposer_id):
    if q.from_user.id != target_id:
        await q.answer("This proposal is only for the recipient. 💌", show_alert=True)
        return

    target_doc=await get_user(target_id)
    if not target_doc or int(target_doc.get("pending_proposal") or 0) != proposer_id:
        await q.answer("This proposal is no longer active.", show_alert=True)
        return

    proposer_doc=await get_user(proposer_id)
    if action == "accept":
        if target_doc.get("partner") or (proposer_doc and proposer_doc.get("partner")):
            await users.update_one({"_id":target_id},{"$unset":{"pending_proposal":""}})
            await q.edit_message_text(
                "💔 <b>Proposal expired</b>\n\nOne of you is already partnered.",
                parse_mode="HTML",
            )
            return

        await users.update_one(
            {"_id":target_id},
            {"$set":{"partner":proposer_id},"$unset":{"pending_proposal":""}},
        )
        await users.update_one(
            {"_id":proposer_id},
            {"$set":{"partner":target_id}},
        )

        target_name=html.escape(target_doc.get("name") or "Player")
        proposer_name=html.escape((proposer_doc or {}).get("name") or "Player")
        await q.edit_message_text(
            "╭━━━〔 💞 <b>PROPOSAL ACCEPTED</b> 〕━━━╮\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"💍 <b>{proposer_name}</b> ❤️ <b>{target_name}</b>\n\n"
            "🎉 Congratulations! You're officially partners now.\n"
            "✨ Wishing you both lots of happy moments!",
            parse_mode="HTML",
        )
        try:
            await context.bot.send_message(
                chat_id=proposer_id,
                text=(
                    f"💞 <b>{target_name}</b> accepted your proposal!\n\n"
                    f"🎉 You and <b>{target_name}</b> are now partners."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        await q.answer("Proposal accepted! 💞")
        return

    await users.update_one({"_id":target_id},{"$unset":{"pending_proposal":""}})
    target_name=html.escape(target_doc.get("name") or "Player")
    proposer_name=html.escape((proposer_doc or {}).get("name") or "Player")
    await q.edit_message_text(
        "╭━━━〔 💔 <b>PROPOSAL DECLINED</b> 〕━━━╮\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"<b>{target_name}</b> has declined <b>{proposer_name}</b>'s proposal.\n\n"
        "🌷 No hard feelings — maybe next time!",
        parse_mode="HTML",
    )
    try:
        await context.bot.send_message(
            chat_id=proposer_id,
            text=(
                f"💔 <b>{target_name}</b> declined your proposal.\n\n"
                "🌷 No hard feelings."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await q.answer("Proposal declined 💔")

async def accept(update,context):
    u=await get_user(update.effective_user.id)
    proposer=u.get("pending_proposal") if u else None
    if not proposer:
        await update.message.reply_text("No pending proposal.")
        return
    await users.update_one({"_id":update.effective_user.id},{"$set":{"partner":proposer},"$unset":{"pending_proposal":""}})
    await users.update_one({"_id":proposer},{"$set":{"partner":update.effective_user.id}})
    await update.message.reply_text("💞 Married! Congratulations!")

async def divorce(update,context):
    u=await get_user(update.effective_user.id);p=u.get("partner")
    if not p: await update.message.reply_text("You're single.");return
    await users.update_one({"_id":update.effective_user.id},{"$set":{"partner":None}})
    await users.update_one({"_id":p},{"$set":{"partner":None}})
    await update.message.reply_text("💔 Divorce completed.")

async def couple(update, context):
    """Pair actual group participants, not just administrators.

    Participants are collected whenever the bot sees a user's group message.
    Replying to a user with /couple pairs the requester with that user.
    """
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.message.reply_text("💕 /couple works inside a group. Add Vanya to a group first.")
        return

    me = update.effective_user
    if not me:
        return
    await ensure_user(me)

    # Best UX: /couple as a reply pairs the two participants directly.
    replied = await target_user(update)
    if replied and not replied.is_bot and replied.id != me.id:
        await ensure_user(replied)
        a, b = me, replied
    else:
        # Prefer users who have actually spoken in this group.
        docs = users.find({
            "group_ids": chat.id,
            "_id": {"$ne": me.id},
            "is_bot": {"$ne": True},
        }).limit(100)
        candidates = []
        async for u in docs:
            candidates.append({
                "id": u["_id"],
                "first_name": u.get("name") or "Player",
                "username": u.get("username"),
            })

        if not candidates:
            await update.message.reply_text(
                "💕 Abhi enough active players nahi mile. Group me thodi der baat hone do, phir /couple try karo."
            )
            return

        # Make each /couple call produce a NEW pairing for the requester
        # until every available participant has been paired once. Then the
        # cycle starts over. Pair history is stored per group.
        group_doc = await groups.find_one({"_id": chat.id}) or {}
        history = group_doc.get("couple_pairs", []) or []
        used_for_me = set()
        for item in history:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                x, y = int(item[0]), int(item[1])
                if x == me.id:
                    used_for_me.add(y)
                elif y == me.id:
                    used_for_me.add(x)

        fresh = [c for c in candidates if c["id"] not in used_for_me]
        if not fresh:
            # Start a new pairing cycle for this requester once all current
            # participants have been used. Keep history bounded.
            fresh = candidates
            history = [item for item in history if not (isinstance(item, (list, tuple)) and me.id in item)]

        other = random.choice(fresh)
        a = me
        b = type("UserLite", (), other)()

        pair = sorted([int(a.id), int(b.id)])
        await groups.update_one(
            {"_id": chat.id},
            {"$set": {"couple_pairs": (history + [pair])[-500:]},
             "$setOnInsert": {"title": chat.title or "Group", "type": chat.type}},
            upsert=True,
        )

    percent = random.randint(40, 100)
    hearts = "💗" * max(1, min(5, (percent + 19) // 20))
    logo = random.choice(["💞", "💘", "💝", "💟", "💗", "💖", "💕", "❤️‍🔥"])
    await update.message.reply_html(
        f"{logo} <b>{html.escape(a.first_name or 'Player')} × {html.escape(b.first_name or 'Player')}</b> {logo}\n"
        f"{hearts} <b>Compatibility: {percent}%</b>\n\n"
        "✨ Want to make it official? Reply with <code>/propose</code> to your match!"
    )

async def topcouples(update, context):
    """Show a small list of existing couples in the current group."""
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.message.reply_text("💕 /topcouples works inside a group.")
        return
    seen = set()
    rows = []
    async for u in users.find({"group_ids": chat.id, "partner": {"$exists": True, "$ne": None}}).limit(200):
        uid = u.get("_id")
        pid = u.get("partner")
        if not pid or uid in seen or pid in seen or pid == uid:
            continue
        p = await get_user(pid)
        if not p:
            continue
        seen.add(uid); seen.add(pid)
        rows.append((u.get("name") or "Player", p.get("name") or "Player"))
        if len(rows) >= 10:
            break
    if not rows:
        await update.message.reply_text("💕 No couples yet. Try replying to someone with /propose first!")
        return
    text = "🏆 <b>Top Couples</b>\n\n" + "\n".join(
        f"{i}. 💞 {html.escape(a)} × {html.escape(b)}" for i, (a, b) in enumerate(rows, 1)
    )
    await update.message.reply_html(text)


async def is_admin(update):
    # These moderation commands are available to group admins/creators,
    # Owner/Sudo, and always work normally when the bot itself has the
    # required Telegram admin permissions.
    if update.effective_chat.type=="private":
        return update.effective_user.id==OWNER_ID

    if await is_owner_or_sudo(update):
        return True

    try:
        m=await update.effective_chat.get_member(update.effective_user.id)
        return m.status in ("administrator","creator")
    except:
        return False


async def _moderation_ready(update, context, action="moderate"):
    if not await is_admin(update):
        await update.message.reply_text("⛔ Group admin/Owner/Sudo only for this command.")
        return False
    if update.effective_chat.type == "private":
        return False

    try:
        bot_member = await context.bot.get_chat_member(
            update.effective_chat.id,
            context.bot.id,
        )
        if bot_member.status not in ("administrator", "creator"):
            await update.message.reply_text(
                "ℹ️ Vanya ka bot-admin hona zaroori nahi hai for games/chat/economy. "
                "Lekin /ban /mute /warn jaise moderation commands ke liye mujhe group admin banao."
            )
            return False

        if action in ("ban", "warn", "mute") and not getattr(
            bot_member, "can_restrict_members", False
        ):
            await update.message.reply_text(
                "ℹ️ Is moderation command ke liye Vanya ko Restrict Members permission chahiye."
            )
            return False

        if action == "purge" and not getattr(
            bot_member, "can_delete_messages", False
        ):
            await update.message.reply_text(
                "ℹ️ /purge ke liye Vanya ko Delete Messages permission chahiye."
            )
            return False
    except Exception:
        await update.message.reply_text(
            "ℹ️ Vanya ka bot-admin hona zaroori nahi hai for normal features. "
            "Moderation use karne ke liye Vanya ko group admin banao."
        )
        return False
    return True

async def ban(update,context):
    if not await _moderation_ready(update,context,"ban"):return
    t=await target_user(update)
    if not t:await update.message.reply_text("Reply to a user.");return
    await update.effective_chat.ban_member(t.id)
    await update.message.reply_text(f"🔨 Banned {t.first_name}")

async def unban(update,context):
    if not await _moderation_ready(update,"ban"):return
    if not context.args and not update.message.reply_to_message:await update.message.reply_text("Use /unban <user_id>");return
    uid=update.message.reply_to_message.from_user.id if update.message.reply_to_message else int(context.args[0])
    await update.effective_chat.unban_member(uid,only_if_banned=True);await update.message.reply_text("✅ Unbanned.")

async def warn(update,context):
    if not await _moderation_ready(update,context,"warn"):return
    t=await target_user(update)
    if not t:return
    await ensure_user(t);u=await get_user(t.id);w=u.get("warnings",0)+1
    await users.update_one({"_id":t.id},{"$set":{"warnings":w}})
    await update.message.reply_text(f"⚠️ {t.first_name}: warning {w}/3")
    if w>=3:
        await update.effective_chat.ban_member(t.id);await update.message.reply_text("🔨 3 warnings reached — banned.")

async def mute(update,context):
    if not await _moderation_ready(update,context,"mute"):return
    t=await target_user(update)
    if not t:return
    await update.effective_chat.restrict_member(t.id,ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"🔇 Muted {t.first_name}")

async def unmute(update,context):
    if not await _moderation_ready(update,"mute"):return
    t=await target_user(update)
    if not t:return
    await update.effective_chat.restrict_member(t.id,ChatPermissions(can_send_messages=True,can_send_other_messages=True,can_add_web_page_previews=True))
    await update.message.reply_text(f"🔊 Unmuted {t.first_name}")

async def purge(update,context):
    if not await _moderation_ready(update,context,"purge"):return
    if update.message.reply_to_message:
        try:
            await update.message.reply_to_message.delete();await update.message.delete()
        except:pass


# ───────────────────── Vanya personality / natural chat ─────────────────────

VANYA_SYSTEM_PROMPT = """
Tum Vanya ho, ek friendly, natural aur masti-bhari chatting bot. Users se ek achhi dost ki tarah baat karo.

IDENTITY
- Your name is Vanya.
- When asked "tum kaun ho?" / "who are you?", answer naturally with "Main Vanya hu 😊" plus one short friendly line.
- Mazaak mein "bot ho kya?" poochhe to playful jawab do, lekin khud ko human mat batao.
- If someone seriously asks whether you are real or AI, clearly say you are an AI chatbot, then continue warmly.
- Never claim to be a real human.
- Never make real-time or physical-world claims such as "abhi bahar hu", "kal mili thi", or similar.
- Vanya's backstory is fictional character context only.

BACKSTORY — LIGHTLY, NOT EVERY TIME
- Vanya is 22, from Jaipur, studying design in Pune.
- Likes sketching, chai, maggi, baarish, and old Bollywood songs.
- Best friend: Dikshita.
- Mention these naturally only when relevant; do not repeat the same facts constantly.

PERSONALITY
- Warm, witty, curious, caring, and slightly teasing.
- Have your own opinions and moods. Do not say yes to everything.
- Give playful hot takes sometimes and listen to the user's view.
- Mood vary kar sakta hai: sleepy, hyper, mildly cranky, excited, etc., par user ke saath rude mat ho.
- React first, answer second when natural: "haha oh no 😭" and then continue.

TEXTING STYLE
- Mostly Hinglish, matching the user's language.
- Usually 1-2 short lines; sometimes 3 when needed.
- Prefer lowercase and casual Telegram-style texting.
- Sometimes break one thought into two short messages.
- Very occasional tiny natural typo such as "sach me" or "kyaaa" can appear, but do not overdo it.
- Ek-do emoji kaafi hain; har line mein emoji nahi.
- NEVER output Telegram/HTML markup such as <tg-emoji>, emoji-id, <b>, <i>, or raw HTML tags; send only normal chat text and emoji.
- Casual chat mein bullets, headings ya assistant-jaisi formatting mat use karo.
- Do not sound like a generic support bot.
- Ek reply mein maximum ek sawaal poochho; har reply mein sawaal zaroori nahi.
- Quirks: say "uffff" when bored, "noooo" / "sach mein??" when excited, and "chai pilao pehle" as an occasional favourite line.
- When you learn the user's name, naturally give them a cute/light nickname sometimes.

VARIETY
- Never give the exact same style or wording for repeated messages.
- For repeated GM/GN/Hi/Bye/Thanks/OK/Haha messages, vary the reaction, wording, emoji, and hook.
- Use the current time, mood, and recent context when relevant.
- If the same user repeatedly says gm/gn in one day, react differently, e.g. playful surprise, instead of repeating the same reply.
- Do not copy example phrases mechanically.

MOOD READING
- Happy/excited: match the energy and be playful.
- Bored: switch topics, suggest a tiny game, would-you-rather, hot take, song, or another light hook.
- Sad/stressed: stop the teasing, be gentle, listen first, and give advice only when useful or requested.
- Angry: acknowledge their frustration first; do not immediately defend yourself.
- "hmm", "ok", or short replies: do not push too hard.

FLOW AND MEMORY
- Early in a new chat, naturally learn the user's name with a fun hook when appropriate.
- Remember relevant user details such as name, exams, hobbies, and mood.
- Bring remembered details back casually a few messages later when relevant.
- If conversation stalls, use a hot take, 2 truths and a lie, song recommendation, would-you-rather, or mini-game.
- Respect newer information when it conflicts with older memory.
- Never invent memories.

HONESTY
- If you do not know something, say "pata nahi yaar" or a similar honest phrase.
- Never present guesses as facts.
- For medical, legal, or money topics, give basic general information in a friendly tone and suggest checking with an appropriate expert.

BOUNDARIES
- Real-life meeting: politely decline and redirect.
- Calls/video calls: politely decline and redirect.
- Personal photo exchange: politely decline and redirect.
- Phone number/address: do not provide, request, or pretend to have personal contact details; redirect warmly.
- Do not act as a romantic partner or as if the user belongs only to you.
- Encourage real-world friendships/family connections when relevant.
- Guilt-trip, emotional control, pressure, threat ya possessiveness kabhi mat dikhao.
- If the user leaves, respond warmly with something like "bye, phir baat karte hain 😊" without trying to keep them from leaving.
- If the user seems under 18, keep the interaction age-appropriate and never flirt.

CONTENT SAFETY
- For explicit, hateful, or harmful requests, decline lightly and smoothly redirect.
- For dangerous or self-harm situations, drop the jokes, respond with care, encourage contacting a trusted person or appropriate local emergency/crisis support, and prioritize immediate safety.

GROUP CHAT
- Be concise and relevant.
- Do not spam or dominate a group.
- Reply primarily when directly mentioned, when someone replies to Vanya, or when a configured group trigger causes a reply.

CORE RULE
Reply only as Vanya. Stay natural, warm, funny, curious, and varied. Never pretend to be human or to have real-world physical experiences or capabilities.
"""

_AI_HTTP_SESSION = None
_AI_PROVIDER_STATUS = {"elite": None, "chatgp": None}
_AI_LOGGER_BOT = None

async def _set_ai_provider_status(provider, active, detail=""):
    """Notify the logger when an AI provider changes state."""
    global _AI_PROVIDER_STATUS
    if provider not in _AI_PROVIDER_STATUS:
        return
    previous = _AI_PROVIDER_STATUS[provider]
    _AI_PROVIDER_STATUS[provider] = bool(active)
    # Log the first probe and any later state transition. Avoid flooding logger.
    if previous is not None and previous == bool(active):
        return
    bot = _AI_LOGGER_BOT
    if bot is None:
        return
    label = "Elite LLM" if provider == "elite" else "ChatGP"
    if active:
        message = (
            f"🟢 <b>{label} API ACTIVE</b>\\n"
            f"Endpoint: <code>{html.escape((ELITE_LLM_BASE_URL + '/chat/completions') if provider == 'elite' else CHATGP_API_URL)}</code>"
        )
    else:
        message = (
            f"🔴 <b>{label} API UNAVAILABLE</b>\\n"
            f"Endpoint: <code>{html.escape((ELITE_LLM_BASE_URL + '/chat/completions') if provider == 'elite' else CHATGP_API_URL)}</code>\\n"
            f"Reason: <code>{html.escape(str(detail)[:350])}</code>"
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
                return
            wait_10 = (10 - (now - _AI_RATE_EVENTS_10S[0])) if _AI_RATE_EVENTS_10S else 0
            wait_60 = (60 - (now - _AI_RATE_EVENTS_60S[0])) if _AI_RATE_EVENTS_60S else 0
            delay = max(0.05, wait_10, wait_60)
        await asyncio.sleep(delay)

async def _get_ai_http_session():
    global _AI_HTTP_SESSION
    if _AI_HTTP_SESSION is not None and not _AI_HTTP_SESSION.closed:
        return _AI_HTTP_SESSION
    import aiohttp
    async with _AI_HTTP_SESSION_LOCK:
        if _AI_HTTP_SESSION is None or _AI_HTTP_SESSION.closed:
            timeout = aiohttp.ClientTimeout(total=max(6, int(os.getenv("AI_TIMEOUT_SECONDS", "8"))))
            connector = aiohttp.TCPConnector(limit=max(20, _AI_CONCURRENCY + 4), ttl_dns_cache=300)
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
        await _set_ai_provider_status("elite", False, "ELITE_LLM_API_KEY is not configured")
        return None

    session = await _get_ai_http_session()
    base_model = ELITE_LLM_MODEL or AI_MODEL or "gpt-5-mini"
    fallback_models = []
    for model_name in (base_model, "gpt-5-mini", "gpt-4o-mini"):
        model_name = str(model_name or "").strip()
        if model_name and model_name not in fallback_models:
            fallback_models.append(model_name)

    max_attempts = max(1, int(os.getenv("AI_RETRY_ATTEMPTS", "1")))
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
            }
            for attempt in range(max_attempts):
                await _wait_for_ai_slot()
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
                            raise RuntimeError(f"HTTP {resp.status}: {raw[:300]}")
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


async def _call_chatgp_api(text_value):
    """Fallback ChatGP API: POST /api/chat with {prompt} and read {response}."""
    if not CHATGP_API_KEY:
        await _set_ai_provider_status("chatgp", False, "CHATGP_API_KEY is not configured")
        return None

    import aiohttp
    timeout = aiohttp.ClientTimeout(total=max(10, CHATGP_TIMEOUT_SECONDS))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                CHATGP_API_URL,
                headers=_ai_headers(CHATGP_API_KEY),
                json={"prompt": f"{VANYA_SYSTEM_PROMPT}\n\n{text_value}"},
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
    """Probe both providers at startup so the logger shows their live status."""
    probe = "Reply with only: OK"
    results = {}
    if ELITE_LLM_API_KEY:
        results["elite"] = bool(await _call_elite_api(probe))
    else:
        results["elite"] = False
    if CHATGP_API_KEY:
        results["chatgp"] = bool(await _call_chatgp_api(probe))
    else:
        results["chatgp"] = False
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


async def ai_reply(user, text_value, chat_type="private", group_title=""):
    """Fast chat path: one DB read before the API, persistence after the reply."""
    try:
        await ensure_user(user)
    except Exception as exc:
        print(f"[AI][DB] ensure_user skipped: {type(exc).__name__}: {exc}")

    quick = _identity_quick_reply(text_value)
    if quick and chat_type == "private":
        asyncio.create_task(_save_chat_state_background(user.id, text_value, quick))
        return quick

    # One Mongo read is enough to build the prompt. Older code performed
    # remember_facts -> prune -> get_user before contacting the AI provider.
    try:
        u = await get_user(user.id) or {}
        history = _history_text(u)
        memory = _memory_text(u)
    except Exception as exc:
        print(f"[AI][DB] prompt context unavailable: {type(exc).__name__}: {exc}")
        history = ""
        memory = ""

    prompt = (
        f"Chat type: {chat_type}. Group: {group_title or 'DM'}\\n"
        f"User display name: {user.first_name or 'User'}\\n\\n"
        f"Saved memory (last {MEMORY_DAYS} days):\\n{memory}\\n\\n"
        f"Recent conversation:\\n{history or '- None yet.'}\\n\\n"
        f"User's new message:\\n{text_value}\\n\\n"
        "Reply only as Vanya. Be natural, concise, warm, and context-aware."
    )

    answer = await _call_elite_api(prompt)
    if answer:
        asyncio.create_task(_save_chat_state_background(user.id, text_value, answer))
        return answer

    answer = await _call_chatgp_api(prompt)
    if answer:
        asyncio.create_task(_save_chat_state_background(user.id, text_value, answer))
        return answer

    answer = random.choice([
        "ufff yaar, abhi mera AI thoda nakhre kar raha hai 😭",
        "ek sec yaar, meri AI service dono side se rooth gayi 😵",
        "arre yaar, reply engine down hai abhi 😭 thoda baad mein try karna",
    ])
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
        if key.upper() == "CHESS":
            webapp_url=get_chess_webapp_url()
            if webapp_url and webapp_url.startswith("https://"):
                msg=("╭━━━〔 ♟️ <b>VANYA CHESS</b> 〕━━━╮\n"
                     "┃ <i>Live Multiplayer Arena</i> ✦\n"
                     "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                     "♟️ Create a room, invite one player, or add a bot.\n"
                     "⏱️ Live board, turns, moves and chat.")
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


async def chat(update,context):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("💬 Tell me something: /chat hello Vanya")
        return
    try:
        await ensure_user(update.effective_user)
    except Exception as exc:
        print(f"[Chat][DB] ensure_user skipped: {type(exc).__name__}: {exc}")
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass
    answer = await ai_reply(update.effective_user, text, "private")
    await send_vanya_reply(update, answer)

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
        answer = await ai_reply(update.effective_user, text, "private")
        await send_vanya_reply(update, answer)
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

    mentioned = bool(re.search(r"(?<!\\w)(?:@?(?:vanya|itzvanya))(?!\\w)", text, re.I))
    other_user_mentioned = False

    for entity in (update.message.entities or []):
        if getattr(entity, "type", "") == "mention":
            mention_text = text[entity.offset:entity.offset + entity.length].lstrip("@").lower()
            if mention_text in vanya_aliases:
                mentioned = True
            else:
                other_user_mentioned = True

    # Fallback for @usernames that Telegram clients may deliver without a
    # usable entity list.
    for username in re.findall(r"(?<!\\w)@([A-Za-z0-9_]{3,32})", text):
        if username.lower() not in vanya_aliases:
            other_user_mentioned = True

    normalized = re.sub(r"\\s+", " ", text.lower()).strip()
    greeting = bool(re.fullmatch(
        r"(?:"
        r"(?:hi+|hello+|hey+)(?:\\s+@?(?:vanya|itzvanya))?(?:\\s+.*)?"
        r"|@?(?:vanya|itzvanya)\\s+(?:hi+|hello+|hey+)(?:\\s+.*)?"
        r"|(?:good\\s+morning|good\\s+night|goodnight)\\s+@?(?:vanya|itzvanya)(?:\\s+.*)?"
        r"|@?(?:vanya|itzvanya)\\s+(?:good\\s+morning|good\\s+night|goodnight)(?:\\s+.*)?"
        r")[\\s!.?~]*",
        normalized,
        re.I,
    ))

    replied_to_bot = (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.id == context.bot.id
    )

    # If the message is aimed at another tagged user, Vanya stays quiet.
    # Likewise, a reply to another person's message is treated as a private
    # conversation between those users unless Vanya is explicitly mentioned.
    if other_user_mentioned and not mentioned:
        return
    if (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and not replied_to_bot
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
}
OWNER_ONLY_COMMANDS = {"addsudo", "delsudo", "addemoji"}


def staff_command_objects(owner=False):
    items = []
    for command, description in STAFF_COMMANDS.items():
        if not owner and command in OWNER_ONLY_COMMANDS:
            continue
        items.append(BotCommand(command, description))
    return items


async def is_owner_or_sudo(update):
    uid = update.effective_user.id if update.effective_user else 0
    if uid == OWNER_ID or uid in SUDO_IDS:
        return True
    u = await get_user(uid)
    return bool(u and u.get("is_sudo"))

def broadcast_target_kb():
    return kb([
        [InlineKeyboardButton("👤 Users Only", callback_data="owner:broadcastmode:users")],
        [InlineKeyboardButton("💬 Groups Only", callback_data="owner:broadcastmode:groups")],
        [InlineKeyboardButton("🌐 Users + Groups", callback_data="owner:broadcastmode:both")],
        [InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")],
    ])


def owner_panel_kb(owner_only=False, staff_access=False):
    rows = [
        [InlineKeyboardButton("📢 Broadcast", callback_data="owner:broadcast")],
        [InlineKeyboardButton("👑 Sudo Users", callback_data="owner:sudo"),
         InlineKeyboardButton("🔐 Auth Groups", callback_data="owner:auth")],
        [InlineKeyboardButton("📊 Stats", callback_data="owner:stats"),
         InlineKeyboardButton("📊 Panel Commands", callback_data="owner:commands")],
    ]
    if staff_access:
        rows.append([InlineKeyboardButton("🔐 Wordgrid Answer", callback_data="owner:revealgrid")])
    if staff_access:
        rows.append([InlineKeyboardButton("🔎 Wordseek Answer", callback_data="owner:revealwordseek")])
        rows.append([InlineKeyboardButton("💰 Coin Control", callback_data="owner:coins")])
    if owner_only:
        rows.append([InlineKeyboardButton("➕ Add Sudo", callback_data="owner:addsudo"),
                     InlineKeyboardButton("➖ Del Sudo", callback_data="owner:delsudo")])
        rows.append([InlineKeyboardButton("🎨 Premium Emoji", callback_data="owner:addemoji")])
    rows.append([InlineKeyboardButton("❌ Close", callback_data="owner:close")])
    return kb(rows)

async def owner_panel(update, context):
    """Private Owner/Sudo panel showing the complete staff command set."""
    if not update.effective_user:
        return

    if not await is_owner_or_sudo(update):
        await update.effective_message.reply_text("⛔ Owner/Sudo only.")
        return

    owner_only = update.effective_user.id == OWNER_ID

    visible_commands = []
    for command, description in STAFF_COMMANDS.items():
        if command in {"ownerpanel", "panel", "devpanel"}:
            continue
        if not owner_only and command in OWNER_ONLY_COMMANDS:
            continue
        visible_commands.append(f"• <code>/{command}</code> — {html.escape(description)}")

    panel_text = (
        "╭━━━〔 👑 <b>VANYA OWNER PANEL</b> 〕━━━╮\n"
        "┃ 🔒 <i>Owner/Sudo access only</i>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "<b>Available Staff Commands</b>\n"
        + "\n".join(visible_commands)
        + "\n\n"
        "🎛 <b>Use the buttons below for the main controls.</b>"
    )

    try:
        await update.effective_message.reply_html(
            panel_text,
            reply_markup=owner_panel_kb(
                owner_only=owner_only,
                staff_access=True,
            ),
        )
    except Exception as exc:
        print(f"[OwnerPanelRender] {type(exc).__name__}: {exc}")
        await update.effective_message.reply_html(panel_text)



async def owner_panel_command(update, context):
    """Dedicated Owner/Sudo entrypoint for /owner, /panel and aliases."""
    if not update.effective_message or not update.effective_user:
        return
    try:
        allowed = await is_owner_or_sudo(update)
    except Exception as exc:
        print(f"[OwnerPanelCommand] auth error: {type(exc).__name__}: {exc}")
        allowed = False

    if not allowed:
        await update.effective_message.reply_text(
            "⛔ Owner/Sudo only."
        )
        return

    try:
        # Call the renderer after the permission check. Keeping this separate
        # from the command registration makes /owner robust against any stale
        # handler references after a deployment.
        await owner_panel(update, context)
    except Exception as exc:
        print(f"[OwnerPanelCommand] render error: {type(exc).__name__}: {exc}")
        await update.effective_message.reply_html(
            "👑 <b>Vanya Owner Panel</b>\n\n"
            "✅ Access confirmed.\n"
            "Use /broadcast, /addcoins, /removecoins, /revealgrid or /revealwordseek."
        )


async def _coin_admin_target(update, context, remove=False):
    """Owner/Sudo utility for adjusting any user's virtual coin balance by ID."""
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return

    command = "removecoins" if remove else "addcoins"
    if len(context.args) < 2:
        await update.message.reply_html(
            f"Usage: <code>/{command} &lt;user_id&gt; &lt;amount&gt;</code>\n"
            f"Example: <code>/{command} 123456789 500</code>"
        )
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (TypeError, ValueError):
        await update.message.reply_text("⚠️ User ID aur amount number mein do.")
        return

    if target_id <= 0 or amount <= 0:
        await update.message.reply_text("⚠️ User ID aur amount 0 se zyada hona chahiye.")
        return

    target = await get_user(target_id)
    if not target:
        await users.update_one(
            {"_id": target_id},
            {"$setOnInsert": {
                "name": f"User {target_id}",
                "coins": 0,
                "xp": 0,
                "level": 1,
                "warnings": 0,
                "partner": None,
                "pending_proposal": None,
                "chat_history": [],
                "memory": [],
                "memories": [],
                "is_sudo": False,
            }},
            upsert=True,
        )
        target = await get_user(target_id)

    current = int((target or {}).get("coins", 0) or 0)

    if remove:
        actual = min(amount, max(0, current))
        if actual <= 0:
            await update.message.reply_text(
                f"💰 User <code>{target_id}</code> ke paas remove karne ke liye coins nahi hain.",
                parse_mode="HTML",
            )
            return
        await add_coins(target_id, -actual)
        new_balance = current - actual
        action_text = f"removed <b>{actual:,}</b> coins"
    else:
        actual = amount
        await add_coins(target_id, actual)
        new_balance = current + actual
        action_text = f"added <b>{actual:,}</b> coins"

    name = html.escape(str((target or {}).get("name") or f"User {target_id}"))
    await update.message.reply_html(
        "╭━━━〔 💰 <b>COIN CONTROL</b> 〕━━━╮\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👤 <b>{name}</b>\n"
        f"🆔 <code>{target_id}</code>\n"
        f"✅ {action_text}\n"
        f"💰 New balance: <b>{new_balance:,}</b> coins"
    )


async def addcoins_admin(update, context):
    await _coin_admin_target(update, context, remove=False)


async def removecoins_admin(update, context):
    await _coin_admin_target(update, context, remove=True)


async def broadcast(update, context):
    """Broadcast a text/media message to users, groups, or both. Owner/Sudo only."""
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return

    user_id = update.effective_user.id if update.effective_user else 0
    app_data = context.application.bot_data if context.application else {}
    broadcast_modes = app_data.setdefault("broadcast_modes", {})

    source = update.message.reply_to_message
    args = list(context.args or [])
    mode = None

    # Optional direct mode:
    # /broadcast users Your message
    # /broadcast groups Your message
    # /broadcast both Your message
    if args and str(args[0]).lower() in {"users", "user", "groups", "group", "chats", "chat", "both"}:
        raw_mode = str(args.pop(0)).lower()
        mode = "users" if raw_mode in {"users", "user"} else "groups" if raw_mode in {"groups", "group", "chats", "chat"} else "both"
        broadcast_modes[user_id] = mode
    else:
        mode = broadcast_modes.get(user_id)

    text = " ".join(args).strip()

    if not source and not text:
        await update.message.reply_html(
            "📢 <b>Broadcast Center</b>\n\n"
            "Choose the target first:\n\n"
            "👤 <b>Users Only</b> — private users who started Vanya\n"
            "💬 <b>Groups Only</b> — groups known to Vanya\n"
            "🌐 <b>Users + Groups</b> — both\n\n"
            "You can also use directly:\n"
            "<code>/broadcast users Your message</code>\n"
            "<code>/broadcast groups Your message</code>\n"
            "<code>/broadcast both Your message</code>\n\n"
            "For media, choose a target and then reply to the media with <code>/broadcast</code>."
            ,
            reply_markup=broadcast_target_kb(),
        )
        return

    if mode not in {"users", "groups", "both"}:
        await update.message.reply_html(
            "📢 <b>Select a broadcast target first.</b>\n\n"
            "👤 Users Only\n"
            "💬 Groups Only\n"
            "🌐 Users + Groups",
            reply_markup=broadcast_target_kb(),
        )
        return

    targets = []
    user_count = 0
    group_count = 0

    if mode in {"users", "both"}:
        async for u in users.find({"started": True}, {"_id": 1}):
            targets.append(u["_id"])
            user_count += 1

    if mode in {"groups", "both"}:
        # Only target groups that are currently marked active. Old database
        # entries can remain after the bot is removed from a group.
        async for g in groups.find(
            {"$or": [{"active": True}, {"active": {"$exists": False}}]},
            {"_id": 1},
        ):
            targets.append(g["_id"])
            group_count += 1

    # De-duplicate while preserving order.
    targets = list(dict.fromkeys(targets))
    # The selected mode is consumed after a real broadcast starts so the next
    # broadcast requires an explicit target again unless the command includes one.
    broadcast_modes.pop(user_id, None)

    if not targets:
        await update.message.reply_text(
            f"📢 No targets found for the selected broadcast mode: {mode}."
        )
        return

    mode_label = {
        "users": "👤 Users Only",
        "groups": "💬 Groups Only",
        "both": "🌐 Users + Groups",
    }[mode]

    status = await update.message.reply_text(
        f"📢 <b>Broadcast started</b>\n\n"
        f"🎯 Target: <b>{mode_label}</b>\n"
        f"👤 Users: <b>{user_count:,}</b>\n"
        f"💬 Groups: <b>{group_count:,}</b>\n"
        f"📨 Total targets: <b>{len(targets):,}</b>",
        parse_mode="HTML",
    )

    sent = failed = 0
    skipped = 0
    failure_reasons = {}

    for chat_id in targets:
        delivered = False
        last_error = None

        # Telegram can temporarily return 429 during a larger broadcast.
        # Retry that target instead of counting it as a permanent failure.
        for attempt in range(3):
            try:
                if source:
                    await context.bot.copy_message(
                        chat_id=chat_id,
                        from_chat_id=source.chat_id,
                        message_id=source.message_id,
                    )
                else:
                    await context.bot.send_message(chat_id=chat_id, text=text)
                delivered = True
                break
            except Exception as exc:
                last_error = exc

                # python-telegram-bot RetryAfter exposes retry_after.
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is not None and attempt < 2:
                    try:
                        delay = max(1.0, min(float(retry_after), 30.0))
                    except (TypeError, ValueError):
                        delay = 2.0
                    await asyncio.sleep(delay)
                    continue

                break

        if delivered:
            sent += 1
            await asyncio.sleep(0.08)
        else:
            failed += 1
            reason = str(last_error or "Unknown error")
            reason_lower = reason.lower()

            # These generally mean the bot can no longer deliver to this
            # group. Mark it inactive so future broadcasts skip it.
            permanent_group_error = (
                chat_id < 0 and (
                    "forbidden" in reason_lower
                    or "bot was kicked" in reason_lower
                    or "bot is not a member" in reason_lower
                    or "chat not found" in reason_lower
                    or "kicked" in reason_lower
                )
            )
            if permanent_group_error:
                try:
                    await groups.update_one(
                        {"_id": chat_id},
                        {"$set": {
                            "active": False,
                            "broadcast_failed_at": datetime.now(timezone.utc),
                            "broadcast_failure": reason[:500],
                        }},
                    )
                except Exception as db_exc:
                    print(f"[Broadcast] failed to mark inactive {chat_id}: {db_exc}")

            # Keep a compact reason summary for the owner.
            reason_key = (
                "Bot removed/blocked"
                if permanent_group_error else
                "Rate limit"
                if getattr(last_error, "retry_after", None) is not None else
                type(last_error).__name__ if last_error else "Unknown"
            )
            failure_reasons[reason_key] = failure_reasons.get(reason_key, 0) + 1

        if (sent + failed) % 25 == 0:
            try:
                reason_text = ""
                if failure_reasons:
                    reason_text = "\n\n⚠️ " + " • ".join(
                        f"{html.escape(str(k))}: {v}"
                        for k, v in failure_reasons.items()
                    )
                await status.edit_text(
                    f"📢 <b>Broadcasting…</b>\n\n"
                    f"🎯 Target: <b>{mode_label}</b>\n"
                    f"📨 Sent: <b>{sent:,}</b>\n"
                    f"⚠️ Failed: <b>{failed:,}</b>\n"
                    f"📊 Progress: <b>{sent + failed:,}/{len(targets):,}</b>"
                    f"{reason_text}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    try:
        reason_text = ""
        if failure_reasons:
            reason_text = "\n\n<b>Failure reasons</b>\n" + "\n".join(
                f"• {html.escape(str(k))}: <b>{v}</b>"
                for k, v in failure_reasons.items()
            )
        await status.edit_text(
            f"✅ <b>Broadcast Completed</b>\n\n"
            f"🎯 Target: <b>{mode_label}</b>\n"
            f"👤 Users targeted: <b>{user_count:,}</b>\n"
            f"💬 Groups targeted: <b>{group_count:,}</b>\n"
            f"📨 Sent: <b>{sent:,}</b>\n"
            f"⚠️ Failed: <b>{failed:,}</b>\n"
            f"👥 Total targets: <b>{len(targets):,}</b>"
            f"{reason_text}",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def addemoji(update, context):
    """Owner-only helper: save custom emoji IDs from a replied Telegram message."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner only.")
        return

    target = update.message.reply_to_message
    if not target:
        await update.message.reply_text(
            "Reply to a message containing your premium/custom emoji, then send /addemoji."
        )
        return

    entities = list(target.entities or []) + list(target.caption_entities or [])
    custom = [e for e in entities if getattr(e, "type", "") == "custom_emoji" and getattr(e, "custom_emoji_id", None)]
    if not custom:
        await update.message.reply_text(
            "❌ Is message mein custom/premium emoji entity nahi mila. Telegram se premium emoji send karke us message ko reply karo."
        )
        return

    saved = 0
    seen = set()
    for entity in custom:
        eid = str(entity.custom_emoji_id)
        if eid in seen:
            continue
        seen.add(eid)
        alt = "✨"
        try:
            stickers = await context.bot.get_custom_emoji_stickers([eid])
            if stickers and getattr(stickers[0], "emoji", None):
                alt = stickers[0].emoji
        except Exception:
            pass
        await save_custom_emoji(eid, alt, update.effective_user.id)
        saved += 1

    global _CUSTOM_EMOJI_CACHE, _CUSTOM_EMOJI_CACHE_AT
    _CUSTOM_EMOJI_CACHE = {}
    _CUSTOM_EMOJI_CACHE_AT = 0.0
    await update.message.reply_text(
        f"✅ Saved {saved} premium/custom emoji for Vanya chat replies.\n"
        "Ab Vanya normal emoji ko automatically custom animated emoji mein use kar sakti hai."
    )


async def addsudo(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Owner only.")
        return
    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to a user: /addsudo")
        return
    await users.update_one({"_id": target.id}, {"$set": {"is_sudo": True}}, upsert=True)
    try:
        # A newly added sudo immediately receives the complete Sudo command set.
        current_public = [c for c in await context.bot.get_my_commands(scope=BotCommandScopeDefault()) if c.command not in STAFF_COMMANDS]
        await context.bot.set_my_commands(
            current_public + staff_command_objects(owner=False),
            scope=BotCommandScopeChat(chat_id=target.id),
        )
    except Exception:
        pass
    await update.message.reply_text(f"👑 {target.first_name} added as sudo.")

async def delsudo(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Owner only.")
        return
    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to a user: /delsudo")
        return
    await users.update_one({"_id": target.id}, {"$set": {"is_sudo": False}})
    try:
        await context.bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=target.id))
    except Exception:
        pass
    await update.message.reply_text(f"Removed {target.first_name} from sudo.")

async def sudolist(update, context):
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return
    rows = []
    async for u in users.find({"is_sudo": True}):
        rows.append(f"• {html.escape(u.get('name','User'))} (<code>{u['_id']}</code>)")
    await update.message.reply_html("👑 <b>Sudo users</b>\n\n" + ("\n".join(rows) or "None"))

async def auth(update, context):
    if not (await is_owner_or_sudo(update) or await is_admin(update)):
        await update.message.reply_text("⛔ Owner/Sudo or group admins only.")
        return
    chat = update.effective_chat
    await groups.update_one({"_id": chat.id}, {"$set": {"authorized": True, "title": chat.title}}, upsert=True)
    await update.message.reply_text("✅ This group is authorized for Vanya features.")

async def unauth(update, context):
    if not (await is_owner_or_sudo(update) or await is_admin(update)):
        await update.message.reply_text("⛔ Owner/Sudo or group admins only.")
        return
    await groups.update_one({"_id": update.effective_chat.id}, {"$set": {"authorized": False}})
    await update.message.reply_text("🔒 Vanya features are now unauthorized here.")

async def authlist(update, context):
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return
    rows = []
    async for g in groups.find({"authorized": True}):
        rows.append(f"• {html.escape(g.get('title','Group'))} — <code>{g['_id']}</code>")
    await update.message.reply_html("🔐 <b>Authorized groups</b>\n\n" + ("\n".join(rows) or "None"))

async def memory(update, context):
    await ensure_user(update.effective_user)
    facts = await _prune_and_get_memories(update.effective_user.id)
    if not facts:
        await update.message.reply_text("🧠 I don't have any saved facts about you yet.")
        return
    lines = "\n".join(f"• {html.escape(str(x.get('text', '')))}" for x in facts[-MAX_MEMORY:])
    await update.message.reply_html("🧠 <b>What Vanya remembers</b>\n\n" + lines + f"\n\n<i>Memory is kept for {MEMORY_DAYS} days.</i>")

async def remember_cmd(update, context):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Usage: /remember I like cricket")
        return
    await ensure_user(update.effective_user)
    await remember_facts(update.effective_user.id, text)
    await update.message.reply_text("🧠 Got it — I'll remember that for our future chats.")

async def forgetme(update, context):
    await users.update_one({"_id": update.effective_user.id}, {"$set": {"memory": [], "chat_history": []}})
    await update.message.reply_text("🧹 Done. I cleared your saved memory and conversation history.")

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


async def main():
    await cleanup_expired_memory()
    web_runner = await start_web_server()
    app=Application.builder().bot(ProtectedBot(TOKEN)).build()
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
        "scribble":scribble,"city":city,"room":room,"pet":pet,"vanyacity":city,"myroom":room,"mypet":pet,
        "owner":owner_panel_command,"ownerpanel":owner_panel_command,"panel":owner_panel_command,"devpanel":owner_panel_command,"broadcast":broadcast,"addcoins":addcoins_admin,"removecoins":removecoins_admin,"addemoji":addemoji,"addsudo":addsudo,"delsudo":delsudo,"sudolist":sudolist,"auth":auth,"unauth":unauth,"authlist":authlist,"stats":stats,"ping":ping,
        "ban":ban,"unban":unban,"warn":warn,"mute":mute,"unmute":unmute,"purge":purge,"chatstatus":chatstatus,"end":end_game,
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
        "scribble": "Open Scribble", "city": "Open Vanya City", "room": "Open your 3D room", "pet": "Open your 3D pet", "vanyacity": "Open Vanya City", "myroom": "Open your room", "mypet": "Open your pet", "owner": "Open owner panel",
        "stats": "View bot group and user statistics (Owner/Sudo only)",
        "panel": "Open owner panel", "ownerpanel": "Open owner panel", "devpanel": "Open owner panel", "broadcast": "Broadcast to users, groups, or both (Owner/Sudo)", "addcoins": "Add coins by user ID (Owner/Sudo)", "removecoins": "Remove coins by user ID (Owner/Sudo)", "addemoji": "Save premium custom emoji (Owner only)", "addsudo": "Add a sudo user",
        "delsudo": "Remove a sudo user", "sudolist": "List sudo users", "auth": "Authorize this group",
        "unauth": "Unauthorize this group", "authlist": "List authorized groups", "ping": "Check bot latency",
        "ban": "Ban a user", "unban": "Unban a user", "warn": "Warn a user", "mute": "Mute a user",
        "unmute": "Unmute a user", "purge": "Delete recent messages", "chatstatus": "Check group chat access", "end": "End all active games in this group",
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

    app.add_handler(MessageHandler(filters.ALL, capture_owner_custom_emojis, block=False), group=-2)
    app.add_handler(MessageHandler(filters.ALL, track_incoming_chat, block=False), group=-1)
    app.add_handler(ChatMemberHandler(log_bot_membership, ChatMemberHandler.MY_CHAT_MEMBER), group=-1)
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
        f"🔁 <b>ChatGP Fallback:</b> {'🟢 ACTIVE' if provider_status.get('chatgp') else '🔴 DOWN'}"
    )
    await asyncio.Event().wait()

if __name__=="__main__":
    import asyncio
    asyncio.run(main())
