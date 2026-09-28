import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def coinflip(update,context):
    await update.message.reply_text(f"🪙 <b>{random.choice(['HEADS','TAILS'])}</b>",parse_mode="HTML")
