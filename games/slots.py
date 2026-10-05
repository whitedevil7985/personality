from games.common import safe_name
from db import get_user, add_coins, record_game_result, ensure_user, get_user_lock


def _slot_symbols(value: int):
    """Decode Telegram's 1..63 slot outcome into its 3 symbol indexes."""
    mapping = (1, 2, 3, 0)
    n = max(0, value - 1)
    return (
        mapping[n & 3],
        mapping[(n >> 2) & 3],
        mapping[(n >> 4) & 3],
    )


async def slots(update, context):
    """
    Telegram-native slot machine.

    Telegram generates the animation/outcome server-side. Matching combinations
    pay out according to the virtual-coin rules below.
    """
    user_id = update.effective_user.id
    await ensure_user(update.effective_user)

    async with get_user_lock(user_id):
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

        await add_coins(user_id, -amount)

        spin = await update.message.reply_dice(emoji="🎰")
        value = int(getattr(spin.dice, "value", 0) or 0)

        if value == 64:
            payout = amount * 10
            profit = payout - amount
            won = True
            title = "🎰 JACKPOT — 777!"
            result = f"💎 +{profit:,} coins"
        else:
            symbols = _slot_symbols(value)
            unique = len(set(symbols))

            if unique == 1:
                payout = amount * 3
                profit = payout - amount
                won = True
                title = "🎰 THREE MATCH!"
                result = f"🔥 +{profit:,} coins"
            elif unique == 2:
                payout = max(amount + 1, round(amount * 1.2))
                profit = payout - amount
                won = True
                title = "🎰 TWO MATCH!"
                result = f"✨ +{profit:,} coins"
            else:
                payout = 0
                profit = -amount
                won = False
                title = "🎰 No match"
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

    await update.message.reply_text(
        f"{title}\n"
        f"🎟️ Bet: {amount:,} coins\n"
        f"{result}\n"
        f"💰 Balance: {new_balance:,} coins"
    )
