"""Modular handler module for ItzVanyaBot Ultimate."""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

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
