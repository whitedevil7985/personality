"""Owner-only blacklist handlers and access guards for ItzVanyaBot Ultimate.

This module is intentionally independent from bot.py so blacklist logic can be
changed/tested without touching unrelated AI, games, broadcast, or UI code.
"""

import html
from datetime import datetime, timezone

from telegram.ext import ApplicationHandlerStop

from config import OWNER_ID
from db import get_user, users


def _resolve_user_id(update, context):
    """Resolve a moderation target from a replied message or a numeric user ID."""
    if update.message and update.message.reply_to_message and update.message.reply_to_message.from_user:
        return update.message.reply_to_message.from_user.id, update.message.reply_to_message.from_user
    if context.args:
        try:
            uid = int(context.args[0])
            if uid > 0:
                return uid, None
        except (TypeError, ValueError):
            pass
    return None, None


async def blacklist(update, context):
    """Owner-only permanent bot blacklist. Supports reply or /blacklist <user_id>."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        await update.effective_message.reply_text("⛔ Owner only.")
        return

    target_id, target_user_obj = await _resolve_user_id(update, context)
    if not target_id:
        await update.effective_message.reply_html(
            "🚫 <b>Blacklist User</b>\n\n"
            "Reply to the user's message with <code>/blacklist</code>\n"
            "or use <code>/blacklist &lt;user_id&gt;</code>."
        )
        return

    if target_id == OWNER_ID:
        await update.effective_message.reply_text("⚠️ Owner ko blacklist nahi kiya ja sakta.")
        return

    target_name = (
        target_user_obj.full_name
        if target_user_obj
        else f"User {target_id}"
    )
    now = datetime.now(timezone.utc)
    await users.update_one(
        {"_id": target_id},
        {"$set": {
            "blacklisted": True,
            "blacklisted_at": now,
            "blacklisted_by": update.effective_user.id,
            "name": target_name,
            "username": getattr(target_user_obj, "username", None) if target_user_obj else None,
        }},
        upsert=True,
    )

    await update.effective_message.reply_html(
        "🚫 <b>USER BLACKLISTED</b>\n\n"
        f"👤 <b>{html.escape(target_name)}</b>\n"
        f"🆔 <code>{target_id}</code>\n\n"
        "🔒 Ab ye user Vanya ko use nahi kar sakta."
    )


async def unblacklist(update, context):
    """Owner-only removal from the bot blacklist."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        await update.effective_message.reply_text("⛔ Owner only.")
        return

    target_id, target_user_obj = await _resolve_user_id(update, context)
    if not target_id:
        await update.effective_message.reply_html(
            "♻️ <b>Unblacklist User</b>\n\n"
            "Reply to the user's message with <code>/unblacklist</code>\n"
            "or use <code>/unblacklist &lt;user_id&gt;</code>."
        )
        return

    existing = await get_user(target_id)
    if not existing or not existing.get("blacklisted", False):
        await update.effective_message.reply_text("ℹ️ Ye user blacklist mein nahi hai.")
        return

    await users.update_one(
        {"_id": target_id},
        {"$set": {"blacklisted": False},
         "$unset": {"blacklisted_at": "", "blacklisted_by": ""}},
    )

    target_name = (
        target_user_obj.full_name
        if target_user_obj
        else str(existing.get("name") or f"User {target_id}")
    )
    await update.effective_message.reply_html(
        "♻️ <b>USER UNBLACKLISTED</b>\n\n"
        f"👤 <b>{html.escape(target_name)}</b>\n"
        f"🆔 <code>{target_id}</code>\n\n"
        "✅ Ab ye user Vanya ko dobara use kar sakta hai."
    )


async def blacklist_message_guard(update, context):
    """Stop blacklisted users before any normal command/chat/game handler runs."""
    user = update.effective_user
    if not user or user.id == OWNER_ID:
        return

    try:
        record = await get_user(user.id)
    except Exception:
        return

    if not record or not record.get("blacklisted", False):
        return

    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        raise ApplicationHandlerStop

    # Never post a blacklist notice into groups. A blacklisted user's group
    # messages/commands are simply ignored. In a private chat (including when
    # they open/start the bot), show the access-blocked notice in DM instead.
    if chat.type == "private":
        try:
            await message.reply_html(
                "🚫 <b>ACCESS BLOCKED</b>\\n\\n"
                "Aap Vanya se blacklisted ho.\\n"
                "Bot ke commands, chat aur games aapke liye disabled hain."
            )
        except Exception as exc:
            print(f"[Blacklist] DM notice failed: {type(exc).__name__}: {exc}")

    raise ApplicationHandlerStop


async def blacklist_callback_guard(update, context):
    """Block blacklisted users from using inline buttons too."""
    query = update.callback_query
    user = query.from_user if query else None
    if not query or not user or user.id == OWNER_ID:
        return

    try:
        record = await get_user(user.id)
    except Exception:
        return

    if not record or not record.get("blacklisted", False):
        return

    try:
        await query.answer(
            "🚫 Aap Vanya se blacklisted ho.",
            show_alert=True,
        )
    except Exception:
        pass
    raise ApplicationHandlerStop

