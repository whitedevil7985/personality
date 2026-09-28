import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def dice(update,context):
    n=random.randint(1,6);await update.message.reply_text(f"🎲 You rolled <b>{n}</b>",parse_mode="HTML")
