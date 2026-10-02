"""Modular handler module for ItzVanyaBot Ultimate.

The entrypoint owns shared runtime state; this module only owns the handlers
listed below. The bridge keeps the current runtime namespace shared during the
migration so existing behavior is preserved.
"""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

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


async def _get_group_log_link(context, chat):
    """Return the most useful direct group link for the owner logger."""
    try:
        # Public groups have a stable t.me username link.
        if chat.username:
            return f"https://t.me/{chat.username}"

        # For private groups, an admin bot can export a direct invite link.
        # This is intentionally attempted only when Vanya is an administrator.
        me = await context.bot.get_me()
        member = await context.bot.get_chat_member(chat.id, me.id)
        if member.status == "administrator":
            # Create a direct-join invite link. This link is configured
            # without join-request approval, so users can enter immediately.
            invite = await context.bot.create_chat_invite_link(
                chat_id=chat.id,
                creates_join_request=False,
            )
            return invite.invite_link
    except Exception:
        pass
    return None


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
        group_link = await _get_group_log_link(context, cm.chat)
        link_line = (f'\n🔗 <b>Group Link:</b> <a href="{html.escape(group_link, quote=True)}">Open Group</a>' if group_link else "")
        await log_event(
            context,
            "📥 <b>VANYA ADDED TO GROUP</b>\n\n"
            f"👥 <b>{html.escape(cm.chat.title or 'Group')}</b>\n"
            f"🆔 <code>{cm.chat.id}</code>\n"
            f"👤 Added by: <b>{actor_name}</b>{actor_username}\n"
            f"🆔 User ID: <code>{actor.id if actor else 'Unknown'}</code>"
            f"{link_line}"
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
