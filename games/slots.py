import asyncio
from games.common import safe_name
from db import get_user, add_coins, record_game_result


async def slots(update, context):
    """
    Telegram-native slot machine.

    Telegram generates the slot outcome server-side and animates the real
    🎰 machine in the client. For Telegram's slot machine, value 64 is the
    jackpot (777); other values are non-winning combinations.
    """
    user_id = update.effective_user.id

    try:
        amount = int(context.args[0]) if context.args else 100
    except (IndexError, ValueError, TypeError):
        amount = 100

    if amount <= 0:
        await update.message.reply_text("❌ Bet must be greater than 0.")
        return

    user = await get_user(user_id)
    balance = int((user or {}).get("coins", 0))

    if balance < amount:
        await update.message.reply_text(
            f"❌ Not enough coins.\n"
            f"💰 Balance: {balance:,}\n"
            f"🎰 Bet: {amount:,}"
        )
        return

    # Take the stake before spinning.
    await add_coins(user_id, -amount)

    # This is Telegram's actual animated slot machine. The server generates
    # the result; the returned Dice.value is the exact outcome of the spin.
    spin = await update.message.reply_dice(emoji="🎰")
    value = int(getattr(spin.dice, "value", 0) or 0)

    # Telegram documents value 64 as the winning 777 combination.
    if value == 64:
        payout = amount * 20
        profit = payout - amount
        won = True
        title = "🎰 JACKPOT — 777!"
        result = f"💎 +{profit:,} coins"
    else:
        payout = 0
        profit = -amount
        won = False
        title = "🎰 No win this spin"
        result = f"💥 -{amount:,} coins"

    if payout:
        await add_coins(user_id, payout)

    await record_game_result(
        user_id,
        "SLOTS",
        profit if won else 0,
        won,
        update.effective_chat.id,
    )

    new_balance = balance - amount + payout

    # Give Telegram a moment to finish the native animation before the result.
    await asyncio.sleep(0.35)

    await update.message.reply_text(
        f"{title}\n"
        f"🎟️ Bet: {amount:,} coins\n"
        f"{result}\n"
        f"💰 Balance: {new_balance:,} coins"
    )
