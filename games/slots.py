import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def slots(update,context):
    x=[random.choice(["🍒","🍋","⭐","💎","7️⃣"]) for _ in range(3)]
    if len(set(x))==1: reward=500
    elif len(set(x))==2: reward=100
    else: reward=0
    if reward: await add_coins(update.effective_user.id,reward)
    await update.message.reply_text(f"🎰 {' | '.join(x)}\n{'🎉 +' + str(reward) + ' coins' if reward else 'Better luck next spin!'}")
