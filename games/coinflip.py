import html
import random
import asyncio

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

    # Resolve the outcome first, but reveal it only after a short visual
    # flip sequence so the game feels like an actual coin toss.
    result = random.choice(["heads", "tails"])
    won = result == choice
    reward = REWARD if won else 0

    flip = await update.message.reply_text(
        "🪙 <b>COIN FLIP</b>\n\n"
        f"🎯 Your pick: <b>{choice.upper()}</b>\n"
        "🌀 Spinning the coin…",
        parse_mode="HTML",
    )

    frames = [
        "🪙 <b>FLIP 1/5</b>\n\n🎯 Your pick: <b>"+choice.upper()+"</b>\n🌀 <b>Heads…</b>",
        "🪙 <b>FLIP 2/5</b>\n\n🎯 Your pick: <b>"+choice.upper()+"</b>\n🌀 <b>↕ Tails…</b>",
        "🪙 <b>FLIP 3/5</b>\n\n🎯 Your pick: <b>"+choice.upper()+"</b>\n🌀 <b>Heads…</b>",
        "🪙 <b>FLIP 4/5</b>\n\n🎯 Your pick: <b>"+choice.upper()+"</b>\n🌀 <b>↕ Tails…</b>",
        "🪙 <b>FLIP 5/5</b>\n\n🎯 Your pick: <b>"+choice.upper()+"</b>\n⏳ <b>Almost there…</b>",
    ]
    for frame in frames:
        await asyncio.sleep(0.32)
        try:
            await flip.edit_text(frame, parse_mode="HTML")
        except Exception:
            pass

    await asyncio.sleep(0.25)
    if won:
        final = (
            "╭━━━〔 🪙 <b>COIN FLIP</b> 〕━━━╮\n"
            f"🎯 You picked: <b>{choice.upper()}</b>\n"
            f"🪙 Coin landed on: <b>{result.upper()}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎉 <b>YOU WON!</b>\n"
            f"💰 <b>+{reward} coins</b>\n"
            f"⭐ <b>+{reward} points</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯"
        )
    else:
        final = (
            "╭━━━〔 🪙 <b>COIN FLIP</b> 〕━━━╮\n"
            f"🎯 You picked: <b>{choice.upper()}</b>\n"
            f"🪙 Coin landed on: <b>{result.upper()}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "😵 <b>YOU LOST</b>\n"
            "💸 No reward this round.\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯"
        )

    try:
        await flip.edit_text(final, parse_mode="HTML")
    except Exception:
        await update.message.reply_text(final, parse_mode="HTML")

    if reward:
        await add_coins(update.effective_user.id, reward)

    await record_game_result(
        update.effective_user.id,
        "COINFLIP",
        reward,
        won,
        update.effective_chat.id,
    )
