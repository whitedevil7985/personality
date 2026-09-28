import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def coinflip(update,context):
    result=random.choice(['HEADS','TAILS'])
    reward=25
    await add_coins(update.effective_user.id, reward)
    await record_game_result(update.effective_user.id, "COINFLIP", reward, True, update.effective_chat.id)
    await update.message.reply_text(f"🪙 <b>{result}</b>\n💰 +{reward} coins • 🏆 +{reward} points",parse_mode="HTML")
