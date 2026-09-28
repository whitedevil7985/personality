import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def coinflip(update,context):
    result=random.choice(['HEADS','TAILS'])
    await record_game_result(update.effective_user.id, "COINFLIP", 0, False, update.effective_chat.id)
    await update.message.reply_text(f"🪙 <b>{result}</b>",parse_mode="HTML")
