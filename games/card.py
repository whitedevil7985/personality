import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def card(update,context):
    ranks=list("23456789JQKA"); suits=["♠️","♥️","♦️","♣️"]
    await update.message.reply_text(f"🃏 {random.choice(ranks)}{random.choice(suits)}")
