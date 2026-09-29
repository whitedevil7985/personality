import html
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result


def get_scribble_webapp_url():
    url = (os.getenv("SCRIBBLE_WEBAPP_URL") or "").strip()
    if not url:
        domain = (
            os.getenv("MINIAPP_DOMAIN")
            or os.getenv("RAILWAY_PUBLIC_DOMAIN")
            or ""
        ).strip().strip("/")
        if domain:
            url = "https://" + domain + "/scribble"
    if not url:
        return ""
    if not url.startswith(("https://", "http://")):
        url = "https://" + url
    return url.rstrip("/")


async def scribble(update, context):
    await ensure_user(update.effective_user)
    url = get_scribble_webapp_url()
    if not url:
        await update.message.reply_text(
            "🖌️ Scribble Web App URL is not configured. "
            "Set SCRIBBLE_WEBAPP_URL to your public HTTPS /scribble URL in Railway Variables."
        )
        return

    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖌️ Open Scribble", url=url)],
            [InlineKeyboardButton("💬 Game Chat", callback_data="gchat:SCRIBBLE")],
        ])
    else:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖌️ Play Scribble", web_app=WebAppInfo(url=url))],
            [InlineKeyboardButton("💬 Game Chat", callback_data="gchat:SCRIBBLE")],
        ])

    await update.message.reply_html(
        "╭━━━〔 🖌️ <b>VANYA SCRIBBLE</b> 〕━━━╮\n"
        "┃ <i>Real-time shared drawing room</i> ✦\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "🎨 Draw together on the same canvas.\n"
        "👥 Share the room code and invite friends.\n"
        "💬 Built-in room chat included.\n\n"
        "Tap <b>Open Scribble</b> to create or join a room.",
        reply_markup=markup,
    )

