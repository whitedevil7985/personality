import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def dice(update,context):
    n=random.randint(1,6);win=n==6
    if win: await add_coins(update.effective_user.id,60)
    await record_game_result(update.effective_user.id, "DICE", 60 if win else 0, win, update.effective_chat.id)
    await update.message.reply_text(f"🎲 You rolled <b>{n}</b>" + ("\n🏆 +60 points!" if win else ""),parse_mode="HTML")
