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

from handlers.callback import callback
from handlers.chat import capture_owner_custom_emojis, _typing_heartbeat, chat, gchat, direct_game_answer, mention_chat
from handlers.social import persona, rank, kill, revive, topkill, marriage, reject

from services.ai_service import _set_ai_provider_status, _ai_rate_cleanup, _wait_for_ai_slot, _try_get_ai_slot, _get_ai_http_session, close_ai_http_session, _parse_ts, _memory_entry_text, _memory_entry_ts, _active_memories, _history_text, _memory_text, _prune_and_get_memories, remember_facts, _append_history, _warm_ai_context_cache, _get_cached_ai_context, _save_ai_context_after_reply, _privacy_quick_reply, _compact_vanya_reply, _sanitize_vanya_reply, _fast_ai_answer, _instant_chat_reply, _identity_quick_reply, _ai_headers, _call_elite_api, _call_elite_api_stream, _call_chatgp_api, probe_ai_providers, _save_chat_state_background, ai_reply, _load_custom_emoji_map, _is_emoji_codepoint, _strip_non_custom_emoji, _premiumize_text, send_vanya_reply, cleanup_expired_memory, track_incoming_chat, stats, answer, end_game, chatstatus, ping, set_ai_logger_bot

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
    set_ai_logger_bot(app.bot)
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
