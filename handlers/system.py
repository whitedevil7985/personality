"""Modular handler module for ItzVanyaBot Ultimate."""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

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

    if chat_id in WORDSCRAMBLE_GAMES:
        WORDSCRAMBLE_GAMES.pop(chat_id, None)
        ended.append("Wordscramble")

    if chat_id in JUMBLE_GAMES:
        JUMBLE_GAMES.pop(chat_id, None)
        ended.append("Jumble")

    if chat_id in CHARADES_GAMES:
        CHARADES_GAMES.pop(chat_id, None)
        ended.append("Charades")

    if chat_id in HACK_GAMES:
        HACK_GAMES.pop(chat_id, None)
        ended.append("Hack")

    # Crash rounds are stored per player; each round keeps its group chat ID.
    for uid, crash_game in list(CRASH_GAMES.items()):
        if crash_game.get("chat_id") == chat_id:
            CRASH_GAMES.pop(uid, None)
            task = crash_game.get("task")
            if task:
                try:
                    task.cancel()
                except Exception:
                    pass
            ended.append("Crash")

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
    """Show bot response latency, uptime, and start time."""
    started = time.perf_counter()
    msg = await update.message.reply_text("🏓 Checking ping…")
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    try:
        uptime_seconds = max(0, int(time.monotonic() - BOT_START_TIME))
        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)

        uptime_parts = []
        if days:
            uptime_parts.append(f"{days}d")
        if hours or days:
            uptime_parts.append(f"{hours}h")
        if minutes or hours or days:
            uptime_parts.append(f"{minutes}m")
        uptime_parts.append(f"{seconds}s")

        started_at = BOT_STARTED_AT.strftime("%d %b %Y, %I:%M:%S %p UTC")

        await msg.edit_text(
            "🏓 <b>Pong!</b>\n\n"
            f"⚡ Response: <code>{elapsed_ms} ms</code>\n"
            "🟢 Status: <b>Online</b>\n"
            f"⏱️ Uptime: <code>{' '.join(uptime_parts)}</code>\n"
            f"🚀 Started: <code>{started_at}</code>",
            parse_mode="HTML",
        )
    except Exception as exc:
        print(f"[Ping] {type(exc).__name__}: {exc}")


# Modular handler imports. These are loaded after bot globals are defined,
# avoiding circular-import initialization races while keeping one runtime namespace.
from handlers.webapp import get_uno_webapp_url, uno, get_chess_webapp_url, chess, get_ludo_webapp_url, get_world_webapp_url, world_cmd, city, room, pet, ludo
from handlers.ui import kb, developer_button, home, start_menu, back, game_chat_kb, game_room_ui, log_event, _get_group_log_link, log_bot_membership, start, profile, safe_html
from handlers.economy import toprich, balance, daily, work, _leaderboard_since, _leaderboard_label, leaderboard_kb, _render_leaderboard, leaderboard, give, target_user, _protection_until, _is_dead, rob, protect, shield, propose, _complete_proposal_callback, accept, divorce, couple, topcouples
from handlers.moderation import is_admin, _moderation_ready, ban, unban, warn, mute, unmute, purge
from handlers.owner import staff_command_objects, is_owner_or_sudo, broadcast_target_kb, owner_panel_kb, owner_panel, owner_panel_command, _coin_admin_target, addcoins_admin, removecoins_admin, broadcast, addemoji, addsudo, delsudo, sudolist, auth, unauth, authlist, memory, remember_cmd, forgetme

# Remaining feature handlers are imported after the core namespace is ready.
