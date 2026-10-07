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
    AI_DISCLOSURE, AI_MODEL, DEDICATED_API_KEY, DEDICATED_API_URL, DEDICATED_AI_MODEL, DEDICATED_TIMEOUT_SECONDS, ELITE_LLM_API_KEY, ELITE_LLM_BASE_URL, ELITE_LLM_MODEL, CHATGP_API_KEY, CHATGP_API_URL, CHATGP_TIMEOUT_SECONDS, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_AI_MODEL, CLOUDFLARE_TIMEOUT_SECONDS, OLLAMA_API_KEY, OLLAMA_API_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS, MAX_HISTORY, MEMORY_ENABLED, MAX_MEMORY,
    MEMORY_DAYS, SUDO_IDS, LOGGER_CHAT_ID
)
from db import db, ensure_user, mark_started, track_group, get_user, add_coins, add_xp, top_users, users, groups, games, logs, ai_usage, get_game_leaderboard, save_custom_emoji, get_custom_emoji_map, record_ai_usage

# ───────────────────── modular games ─────────────────────
from games.rps import rps, rps_cb, RPS_GAMES
from games.dice import dice
from games.coinflip import coinflip
from games.slots import slots
from games.card import card, cardjoin, cardstart, cardcancel, card_cb, CARD_ROOMS
from games.jumble import jumble, JUMBLE_GAMES, jumble_answer, reveal_jumble
from games.tap import tap, tap_cb
from games.bet import bet
from games.uno import uno as uno_legacy, uno_cb, uno_games
from games.ludo import ludo as ludo_legacy, ludo_cb, ludo_games
from games.chess import chess_cmd, chess_cb, chess_games
from games.mines import mines, mines_cb
from games.wordseek import wordseek, answer as wordseek_answer, reveal_wordseek, WORDSEEK_GAMES
from games.wordgrid import wordgrid, wordgrid_answer, send_wordgrid, reveal_wordgrid
from games.crash import crash, crash_cb
from games.charades import charades, CHARADES_GAMES, charades_answer
from games.wordchain import wordchain, wordchain_join, wordchain_answer, WORDCHAIN_GAMES
from games.wordscramble import wordscramble, wordscramble_answer, WORDSCRAMBLE_GAMES
from games.hack import hack, HACK_GAMES, hack_answer
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

from handlers.webapp import get_uno_webapp_url, uno, unojoin, get_chess_webapp_url, chess, chessjoin, get_ludo_webapp_url, ludojoin, get_world_webapp_url, world_cmd, city, room, pet, ludo
from handlers.ui import kb, developer_button, home, start_menu, back, game_chat_kb, game_room_ui, log_event, _get_group_log_link, log_bot_membership, start, profile, safe_html
from handlers.economy import toprich, balance, daily, work, _leaderboard_since, _leaderboard_label, leaderboard_kb, _render_leaderboard, leaderboard, give, target_user, _protection_until, _is_dead, rob, protect, shield, propose, _complete_proposal_callback, accept, divorce, couple, topcouples
from handlers.moderation import is_admin, _moderation_ready, ban, unban, warn, mute, unmute, purge
from handlers.owner import STAFF_COMMANDS, OWNER_ONLY_COMMANDS, staff_command_objects, is_owner_or_sudo, broadcast_target_kb, owner_panel_kb, owner_panel, owner_panel_command, _coin_admin_target, addcoins_admin, removecoins_admin, broadcast, addemoji, addsudo, delsudo, sudolist, auth, unauth, authlist, memory, remember_cmd, forgetme, log, aistats, api_health, owner_monitor_kb, owner_manage_kb, owner_economy_kb, owner_games_kb, owner_users_kb
from handlers.menus import category, category_kb, help_cmd, help_menu_kb, game_menu_kb, games_cmd, game_info, GAME_ITEMS, GAME_INFO, CATEGORIES

# AI service must load before chat handlers so their module globals can see ai_reply/send_vanya_reply.
from services.ai_service import _set_ai_provider_status, _ai_rate_cleanup, _wait_for_ai_slot, _try_get_ai_slot, _get_ai_http_session, close_ai_http_session, _parse_ts, _memory_entry_text, _memory_entry_ts, _active_memories, _history_text, _memory_text, _prune_and_get_memories, remember_facts, _append_history, _warm_ai_context_cache, _get_cached_ai_context, _save_ai_context_after_reply, _privacy_quick_reply, _compact_vanya_reply, _sanitize_vanya_reply, _fast_ai_answer, _instant_chat_reply, _identity_quick_reply, _ai_headers, _call_elite_api, _call_elite_api_stream, _call_chatgp_api, _call_cloudflare_api, _call_ollama_api, probe_ai_providers, _ai_health_monitor, _save_chat_state_background, ai_reply, _load_custom_emoji_map, _is_emoji_codepoint, _strip_non_custom_emoji, _premiumize_text, send_vanya_reply, cleanup_expired_memory, set_ai_logger_bot

from handlers.callback import callback
from handlers.chat import capture_owner_custom_emojis, _typing_heartbeat, chat, gchat, direct_game_answer, mention_chat
# Process uptime starts when the bot module is loaded. These values must
# exist before the modular system handler imports the shared runtime namespace.
BOT_START_TIME = time.monotonic()
BOT_STARTED_AT = datetime.now(timezone.utc)

from handlers.social import persona, rank, kill, revive, topkill, marriage, reject
from handlers.system import stats, answer, end_game, chatstatus, ping
from handlers.middleware import track_incoming_chat


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
        "scribble":scribble,"kingdomwars":kingdomwars,"city":city,"room":room,"pet":pet,"vanyacity":city,"myroom":room,"mypet":pet,
        "owner":owner_panel_command,"ownerpanel":owner_panel_command,"panel":owner_panel_command,"devpanel":owner_panel_command,"broadcast":broadcast,"addcoins":addcoins_admin,"removecoins":removecoins_admin,"addemoji":addemoji,"addsudo":addsudo,"delsudo":delsudo,"sudolist":sudolist,"auth":auth,"unauth":unauth,"authlist":authlist,"stats":stats,"ping":ping,
        "ban":ban,"unban":unban,"warn":warn,"mute":mute,"unmute":unmute,"purge":purge,"chatstatus":chatstatus,"end":end_game,
        "blacklist":blacklist,"unblacklist":unblacklist,"log":log,"aistats":aistats,"apihealth":api_health,
    }
    for name,fn in commands.items():
        app.add_handler(CommandHandler(name,fn))

    # Private answer-reveal commands are registered outside the public command map:
    # Telegram must never advertise them to normal users.
    app.add_handler(CommandHandler("revealgrid", reveal_wordgrid))
    app.add_handler(CommandHandler("revealwordseek", reveal_wordseek))
    app.add_handler(CommandHandler("revealjumble", reveal_jumble))

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
        "scribble": "Open Scribble", "kingdomwars": "Open Kingdom Wars strategy arena", "city": "Open Vanya City", "room": "Open your 3D room", "pet": "Open your 3D pet", "vanyacity": "Open Vanya City", "myroom": "Open your room", "mypet": "Open your pet", "owner": "Open owner panel",
        "stats": "View bot group and user statistics (Owner/Sudo only)",
        "panel": "Open owner panel", "ownerpanel": "Open owner panel", "devpanel": "Open owner panel", "broadcast": "Broadcast to users, groups, or both (Owner/Sudo)", "addcoins": "Add coins by user ID (Owner/Sudo)", "removecoins": "Remove coins by user ID (Owner/Sudo)", "addemoji": "Save premium custom emoji (Owner only)", "addsudo": "Add a sudo user",
        "delsudo": "Remove a sudo user", "sudolist": "List sudo users", "auth": "Authorize this group",
        "unauth": "Unauthorize this group", "authlist": "List authorized groups", "ping": "Check bot latency",
        "ban": "Ban a user", "unban": "Unban a user", "warn": "Warn a user", "mute": "Mute a user",
        "unmute": "Unmute a user", "purge": "Delete recent messages", "chatstatus": "Check group chat access", "end": "End all active games in this group",
        "blacklist": "Blacklist a user (Owner only)", "unblacklist": "Remove a user from blacklist (Owner only)", "log": "View recent logger events (Owner only)", "aistats": "Today's AI API usage by provider (Owner only)", "apihealth": "Live-check every configured AI API (Owner/Sudo)",
    }
    command_list = [BotCommand(name, command_descriptions.get(name, "Vanya command")) for name in commands]
    # Private reveal commands are not part of command_list at all, so they cannot leak
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
    # Route AI chat explicitly: ordinary text in groups/supergroups must reach
    # Vanya without requiring /chat or an @mention.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
            mention_chat,
        ),
        group=1,
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            mention_chat,
        ),
        group=1,
    )
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("✦ ItzVanyaBot Ultimate started ✦")
    set_ai_logger_bot(app.bot)
    provider_status = await probe_ai_providers()
    # Continue checking all configured AI providers in the background every
    # 30 minutes; each cycle is written to the same logger chat and /log store.
    ai_health_task = asyncio.create_task(_ai_health_monitor(app.bot))
    # Startup log is sent only after Telegram initialization/polling succeeds.
    await log_event(
        type("StartupContext", (), {"bot": app.bot})(),
        "🚀 <b>VANYA BOT STARTED</b>\n\n"
        "🟢 Status: <b>Online</b>\n"
        "⚡ Telegram polling: <b>Active</b>\n"
        "🎮 Games: <b>Ready</b>\n\n"
        f"🎯 <b>Dedicated LLMs:</b> {'🟢 ACTIVE' if provider_status.get('dedicated') else '🔴 DOWN'}\n"
        f"   Model: <code>{html.escape(DEDICATED_AI_MODEL or 'unset')}</code>\n"
        f"   Key configured: <b>{'YES' if DEDICATED_API_KEY else 'NO'}</b>\n"
        f"🤖 <b>Elite LLM:</b> {'🟢 ACTIVE' if provider_status.get('elite') else '🔴 DOWN'}\n"
        f"   Model: <code>{html.escape(ELITE_LLM_MODEL or AI_MODEL or 'unset')}</code>\n"
        f"   Key configured: <b>{'YES' if ELITE_LLM_API_KEY else 'NO'}</b>\n"
        f"🔁 <b>ChatGP Fallback:</b> {'🟢 ACTIVE' if provider_status.get('chatgp') else '🔴 DOWN'}\n"
        f"   Key configured: <b>{'YES' if CHATGP_API_KEY else 'NO'}</b>\n"
        f"☁️ <b>Cloudflare Fallback:</b> {'🟢 ACTIVE' if provider_status.get('cloudflare') else '🔴 DOWN'}\n"
        f"   Key configured: <b>{'YES' if CLOUDFLARE_API_TOKEN else 'NO'}</b>\n"
        f"   Model: <code>{html.escape(CLOUDFLARE_AI_MODEL or 'unset')}</code>\n"
        f"🦙 <b>Ollama Cloud:</b> {'🟢 ACTIVE' if provider_status.get('ollama') else '🔴 DOWN'}\n"
        f"   Key configured: <b>{'YES' if OLLAMA_API_KEY else 'NO'}</b>\n"
        f"   Model: <code>{html.escape(OLLAMA_MODEL or 'unset')}</code>"
    )
    await asyncio.Event().wait()

if __name__=="__main__":
    import asyncio
    asyncio.run(main())
