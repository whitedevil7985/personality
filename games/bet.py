import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def bet(update,context):
    try: amount=int(context.args[0])
    except: await update.message.reply_text("Usage: /bet <amount>");return
    u=await get_user(update.effective_user.id)
    if amount<=0 or u.get("coins",0)<amount: await update.message.reply_text("❌ Invalid amount.");return
    if random.random()<0.48:
        await add_coins(update.effective_user.id,amount)
        await update.message.reply_text(f"🎉 You won {amount:,} coins!")
    else:
        await add_coins(update.effective_user.id,-amount)
        await update.message.reply_text(f"💥 You lost {amount:,} coins.")
