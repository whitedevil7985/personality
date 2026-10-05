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

    await ensure_user(update.effective_user)
    user = await get_user(update.effective_user.id)
    balance = int((user or {}).get("coins", 0))
    if balance < amount:
        await update.message.reply_text("❌ Not enough virtual coins.")
        return

    await add_coins(update.effective_user.id, -amount)

    # A one-shot crash round can genuinely lose: below 1.00x the stake burns.
    # Above 1.00x the player receives the multiplied payout.
    multiplier = round(random.uniform(0.50, 4.00), 2)
    payout = int(amount * multiplier) if multiplier >= 1.00 else 0
    profit = payout - amount

    if payout:
        await add_coins(update.effective_user.id, payout)

    won = profit > 0
    points = max(0, min(300, profit // 5))
    await record_game_result(
        update.effective_user.id,
        "CRASH",
        points,
        won,
        update.effective_chat.id,
    )

    if won:
        result = f"🚀 <b>{multiplier}x</b> — +{profit:,} coins profit."
    else:
        result = f"💥 <b>{multiplier}x</b> — you lost {amount - payout:,} coins."

    new_balance = balance - amount + payout
    await update.message.reply_text(
        f"📈 <b>CRASH</b>\n\n{result}\n💰 Balance: <b>{new_balance:,}</b> coins",
        parse_mode="HTML",
    )
