import html
import random
import time

from db import ensure_user, add_coins, record_game_result

REWARD = 25
GAME_TIMEOUT = 90
CHARADES_GAMES = {}

PROMPTS = [
    ("a movie hero", ("hero", "superhero")),
    ("a cat", ("cat", "kitten")),
    ("a cricket shot", ("cricket", "shot")),
    ("someone late for class", ("late", "class")),
    ("eating spicy food", ("spicy", "food")),
]


async def charades(update, context):
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    current = CHARADES_GAMES.get(chat_id)
    if current and time.monotonic() - current["started_at"] < GAME_TIMEOUT:
        await update.message.reply_text("🎭 <b>Charades already running!</b> Guess the action directly.", parse_mode="HTML")
        return

    prompt, answers = random.choice(PROMPTS)
    CHARADES_GAMES[chat_id] = {
        "prompt": prompt,
        "answers": answers,
        "started_at": time.monotonic(),
    }
    await update.message.reply_html(
        "🎭 <b>CHARADES</b>\n\n"
        f"🎬 Act out: <b>{html.escape(prompt)}</b>\n\n"
        f"🏆 Reward: <b>+{REWARD} coins</b>\n"
        "💬 Others guess by typing the answer!\n"
        "⏱️ 90 seconds."
    )


async def charades_answer(update, context):
    if not update.message or not update.message.text or not update.effective_chat:
        return False
    chat_id = update.effective_chat.id
    game = CHARADES_GAMES.get(chat_id)
    if not game:
        return False

    if time.monotonic() - game["started_at"] >= GAME_TIMEOUT:
        CHARADES_GAMES.pop(chat_id, None)
        await update.message.reply_text("⏰ <b>Charades expired!</b> Start again with /charades.", parse_mode="HTML")
        return True

    guess = update.message.text.strip().casefold()
    if not guess:
        return True
    if guess not in {str(x).casefold() for x in game["answers"]}:
        await update.message.reply_text("❌ Nope 😏", parse_mode="HTML")
        return True

    CHARADES_GAMES.pop(chat_id, None)
    user = update.effective_user
    await ensure_user(user)
    await add_coins(user.id, REWARD)
    await record_game_result(user.id, "CHARADES", REWARD, True, chat_id)
    await update.message.reply_html(
        "🎉 <b>Correct!</b>\n\n"
        f"👑 <b>{html.escape(user.first_name or 'Player')}</b> guessed it!\n"
        f"💰 Reward: <b>+{REWARD} coins</b>\n"
        "✨ Start another with /charades"
    )
    return True
