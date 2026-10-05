import html
import random
import time

from db import ensure_user, add_coins, record_game_result

WORDS = ["telegram","galaxy","phantom","python","diamond","rainbow","vanya","dragon","keyboard"]
REWARD = 25
GAME_TIMEOUT = 90

# One active Jumble puzzle per chat.
JUMBLE_GAMES = {}


def _scramble(word):
    letters = list(word)
    for _ in range(12):
        random.shuffle(letters)
        value = "".join(letters)
        if value != word:
            return value
    return "".join(reversed(letters))


async def jumble(update, context):
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    current = JUMBLE_GAMES.get(chat_id)
    if current and time.monotonic() - current["started_at"] < GAME_TIMEOUT:
        await update.message.reply_text(
            "🔤 <b>Jumble already running!</b>\nType the answer directly.",
            parse_mode="HTML",
        )
        return

    answer = random.choice(WORDS)
    JUMBLE_GAMES[chat_id] = {
        "answer": answer.casefold(),
        "scrambled": _scramble(answer),
        "started_at": time.monotonic(),
    }

    await update.message.reply_text(
        "🔤 <b>JUMBLE</b>\n\n"
        f"🧩 Unscramble: <b>{html.escape(JUMBLE_GAMES[chat_id]['scrambled'].upper())}</b>\n\n"
        f"💰 Reward: <b>+{REWARD} coins</b>\n"
        "⏱️ 90 seconds\n"
        "💬 Type the answer directly!",
        parse_mode="HTML",
    )


async def jumble_answer(update, context):
    if not update.message or not update.message.text or not update.effective_chat:
        return False

    chat_id = update.effective_chat.id
    game = JUMBLE_GAMES.get(chat_id)
    if not game:
        return False

    if time.monotonic() - game["started_at"] >= GAME_TIMEOUT:
        JUMBLE_GAMES.pop(chat_id, None)
        await update.message.reply_text(
            "⏰ <b>Jumble expired!</b> Start a new one with /jumble.",
            parse_mode="HTML",
        )
        return True

    guess = update.message.text.strip().casefold()
    if not guess:
        return True

    if guess != game["answer"]:
        await update.message.reply_text("❌ Not quite! Try again 😏")
        return True

    # Consume before awarding so repeated updates cannot win the same round.
    JUMBLE_GAMES.pop(chat_id, None)

    user = update.effective_user
    await ensure_user(user)
    await add_coins(user.id, REWARD)
    await record_game_result(user.id, "JUMBLE", REWARD, True, chat_id)

    await update.message.reply_html(
        "🎉 <b>Correct!</b>\n\n"
        f"👑 <b>{html.escape(user.first_name or 'Player')}</b> solved it!\n"
        f"🔤 Word: <b>{html.escape(game['answer'].upper())}</b>\n"
        f"💰 Reward: <b>+{REWARD} coins</b>\n"
        "✨ Start another with /jumble"
    )
    return True
