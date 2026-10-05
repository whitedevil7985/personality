import html
import random

from db import ensure_user, add_coins, record_game_result

REWARD = 25


async def coinflip(update, context):
    if not update.message or not update.effective_user:
        return

    choice = (context.args[0].strip().lower() if context.args else "")
    aliases = {
        "h": "heads", "head": "heads", "heads": "heads",
        "t": "tails", "tail": "tails", "tails": "tails",
    }
    choice = aliases.get(choice)

    if not choice:
        await update.message.reply_text(
            "🪙 <b>Coinflip</b>\n\n"
            "Choose your side:\n"
            "<code>/coinflip heads</code> or <code>/coinflip tails</code>",
            parse_mode="HTML",
        )
        return

    await ensure_user(update.effective_user)
    result = random.choice(["heads", "tails"])
    won = result == choice
    reward = REWARD if won else 0

    if reward:
        await add_coins(update.effective_user.id, reward)

    await record_game_result(
        update.effective_user.id,
        "COINFLIP",
        reward,
        won,
        update.effective_chat.id,
    )

    if won:
        text = f"🪙 <b>{result.upper()}</b> — you won!\n💰 +{reward} coins • ⭐ +{reward} points"
    else:
        text = f"🪙 <b>{result.upper()}</b> — you lost.\n💸 No reward this round."

    await update.message.reply_text(text, parse_mode="HTML")
