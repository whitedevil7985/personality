"""Moderation handlers for ItzVanyaBot Ultimate.

The entrypoint owns shared runtime state; this module keeps moderation
commands isolated while using the existing runtime namespace during migration.
"""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys


async def is_admin(update):
    if update.effective_chat.type == "private":
        return update.effective_user.id == OWNER_ID

    # owner.py is imported after this module, so resolve the helper at runtime.
    from handlers.owner import is_owner_or_sudo
    if await is_owner_or_sudo(update):
        return True

    try:
        member = await update.effective_chat.get_member(update.effective_user.id)
        return member.status in ("administrator", "creator")
    except Exception:
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


async def ban(update, context):
    if not await _moderation_ready(update, context, "ban"):
        return

    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to a user.")
        return

    await update.effective_chat.ban_member(target.id)
    await update.message.reply_text(f"🔨 Banned {target.first_name}")


async def unban(update, context):
    if not await _moderation_ready(update, context, "ban"):
        return

    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("Use /unban <user_id>")
        return

    try:
        user_id = (
            update.message.reply_to_message.from_user.id
            if update.message.reply_to_message
            else int(context.args[0])
        )
    except (ValueError, TypeError):
        await update.message.reply_text("Use /unban <user_id>")
        return

    await update.effective_chat.unban_member(user_id, only_if_banned=True)
    await update.message.reply_text("✅ Unbanned.")


async def warn(update, context):
    if not await _moderation_ready(update, context, "warn"):
        return

    target = await target_user(update)
    if not target:
        return

    await ensure_user(target)
    user_record = await get_user(target.id)
    warnings = user_record.get("warnings", 0) + 1

    await users.update_one(
        {"_id": target.id},
        {"$set": {"warnings": warnings}},
    )

    await update.message.reply_text(
        f"⚠️ {target.first_name}: warning {warnings}/3"
    )

    if warnings >= 3:
        await update.effective_chat.ban_member(target.id)
        await update.message.reply_text(
            "🔨 3 warnings reached — banned."
        )


async def mute(update, context):
    if not await _moderation_ready(update, context, "mute"):
        return

    target = await target_user(update)
    if not target:
        return

    await update.effective_chat.restrict_member(
        target.id,
        ChatPermissions(can_send_messages=False),
    )
    await update.message.reply_text(f"🔇 Muted {target.first_name}")


async def unmute(update, context):
    if not await _moderation_ready(update, context, "mute"):
        return

    target = await target_user(update)
    if not target:
        return

    await update.effective_chat.restrict_member(
        target.id,
        ChatPermissions(
            can_send_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ),
    )
    await update.message.reply_text(f"🔊 Unmuted {target.first_name}")


async def purge(update, context):
    if not await _moderation_ready(update, context, "purge"):
        return

    if update.message.reply_to_message:
        try:
            await update.message.reply_to_message.delete()
            await update.message.delete()
        except Exception:
            pass
