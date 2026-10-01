import os
import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

def _kingdom_url():
    value = (os.getenv("KINGDOM_WARS_WEBAPP_URL") or "").strip().strip('"').strip("'")
    if not value:
        domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().strip("/")
        if domain:
            value = "https://" + domain + "/kingdom-wars"
    if value and not value.startswith(("https://", "http://")):
        value = "https://" + value
    return value.rstrip("/")

async def kingdomwars(update, context):
    if not update.effective_chat or not update.message:
        return

    from webserver import create_kingdom_room_for_group
    code = await create_kingdom_room_for_group(
        update.effective_chat.id if update.effective_chat.type != "private" else None
    )
    url = _kingdom_url()
    if not url:
        await update.message.reply_text(
            "🏰 Kingdom Wars Web App is not configured. Set KINGDOM_WARS_WEBAPP_URL or MINIAPP_DOMAIN."
        )
        return

    room_url = f"{url}?room={code}"
    button = (
        InlineKeyboardButton("🔐 Join as Telegram", callback_data=f"kingdom:join:{code}")
        if update.effective_chat.type in ("group", "supergroup")
        else InlineKeyboardButton("🏰 Open Kingdom Wars", web_app=WebAppInfo(url=room_url))
    )

    await update.message.reply_html(
        "╭━━━〔 🏰 <b>KINGDOM WARS</b> 〕━━━╮\n"
        "┃ <i>Live strategy • build • attack • conquer</i> ⚔️\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "👑 Build your kingdom, gather resources, recruit an army and fight for the crown.\n"
        "👥 <b>2–6 players</b> can share this live room.\n\n"
        f"🎫 Room: <code>{html.escape(code)}</code>\n"
        "🔐 <b>Telegram verification is required.</b> Each Telegram ID can occupy only one ruler seat in this room.\n\n"
        "Click <b>Join as Telegram</b>; Vanya will send you your personal verified game link in DM.",
        reply_markup=InlineKeyboardMarkup([[button]]),
        disable_web_page_preview=True,
    )
