import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def crash(update, context):
    try:
        amount = max(1, int(context.args[0]))
    except Exception:
        amount = 100
    u = await get_user(update.effective_user.id)
    if u.get("coins", 0) < amount:
        await update.message.reply_text("Not enough virtual coins.")
        return
    await add_coins(update.effective_user.id, -amount)
    multiplier = round(random.uniform(1.05, 4.0), 2)
    payout = int(amount * multiplier)
    await add_coins(update.effective_user.id, payout)
    points = max(10, min(300, payout // 10))
    await record_game_result(update.effective_user.id, "CRASH", points, True, update.effective_chat.id)
    await update.message.reply_text(f"📈 Crash landed at <b>{multiplier}x</b> — payout +{payout:,} virtual coins.", parse_mode="HTML")
