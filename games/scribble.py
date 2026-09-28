import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def scribble(update, context):
    await update.message.reply_text(
        "🖌 Scribble room is ready as a social placeholder. "
        "For a full shared canvas, connect the bot to a web-app URL via your deployment."
    )
