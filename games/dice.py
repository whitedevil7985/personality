import asyncio

from db import add_coins, ensure_user, record_game_result


DICE_REWARD = 60
DICE_EMOJI = "🎲"


async def dice(update, context):
    """Real Telegram animated dice roll with a natural result message."""
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    chat_id = update.effective_chat.id if update.effective_chat else None

    await ensure_user(user)

    try:
        # Telegram generates the actual dice value and shows the native
        # animated rolling dice to users, instead of using random.randint().
        roll_message = await update.message.reply_dice(emoji=DICE_EMOJI)
        roll = int(getattr(getattr(roll_message, "dice", None), "value", 0) or 0)

        # Give the client a moment to show the roll animation before the
        # result card appears, making the interaction feel more like a real roll.
        await asyncio.sleep(1.2)

        won = roll == 6
        reward = DICE_REWARD if won else 0

        if won:
            await add_coins(user.id, reward)

        await record_game_result(
            user.id,
            "DICE",
            reward,
            won,
            chat_id,
        )

        name = (user.first_name or "Player").replace("<", "&lt;").replace(">", "&gt;")
        if won:
            text = (
                "🎲 <b>DICE ROLL</b>\n\n"
                f"👤 <b>{name}</b> rolled <b>6</b>!\n"
                "✨ <b>JACKPOT!</b>\n"
                f"💰 Reward: <b>+{reward} coins</b>"
            )
        else:
            text = (
                "🎲 <b>DICE ROLL</b>\n\n"
                f"👤 <b>{name}</b> rolled <b>{roll}</b>.\n"
                "😏 No jackpot this time — roll again!"
            )

        await update.message.reply_html(text)

    except Exception as exc:
        print(f"[DICE] error: {type(exc).__name__}: {exc}")
        # Avoid breaking the command if Telegram's native dice animation fails.
        await update.message.reply_text(
            "⚠️ Dice roll nahi ho paya. Thodi der baad /dice try karo."
        )
