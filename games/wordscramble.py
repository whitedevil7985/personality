import html
import random
import time

from telegram import InlineKeyboardButton

from games.common import kb, safe_name
from db import ensure_user, add_coins, add_xp, record_game_result


# One active puzzle per chat.
WORDSCRAMBLE_GAMES = {}

WORDS = [
    "delhi",
    "vanya",
    "friendship",
    "telegram",
    "arcade",
    "coffee",
    "mystery",
    "python",
    "rainbow",
    "diamond",
    "computer",
    "keyboard",
    "adventure",
    "birthday",
    "champion",
    "treasure",
    "sunshine",
    "moonlight",
]

REWARD = 50
GAME_TIMEOUT = 90


def _scramble(word: str) -> str:
    letters = list(word)
    # Never show the answer unchanged.
    for _ in range(12):
        random.shuffle(letters)
        result = "".join(letters)
        if result != word:
            return result
    return "".join(reversed(letters))


async def wordscramble(update, context):
    """Start a Wordscramble round. Players answer by typing the word."""
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id

    old = WORDSCRAMBLE_GAMES.get(chat_id)
    if old and time.monotonic() - old["started_at"] < GAME_TIMEOUT:
        await update.message.reply_text(
            "🔤 <b>Wordscramble already running!</b>\n"
            "Type the scrambled word to answer it. 👀",
            parse_mode="HTML",
        )
        return

    answer = random.choice(WORDS)
    scrambled = _scramble(answer)

    WORDSCRAMBLE_GAMES[chat_id] = {
        "answer": answer,
        "scrambled": scrambled,
        "started_at": time.monotonic(),
    }

    await update.message.reply_text(
        "🔤 <b>WORDSCRAMBLE</b>\n\n"
        f"🧩 Unscramble: <b>{html.escape(scrambled.upper())}</b>\n\n"
        f"🏆 Reward: <b>+{REWARD} coins</b>\n"
        "⏱️ You have 90 seconds.\n"
        "💬 Type your answer directly!",
        parse_mode="HTML",
    )


async def wordscramble_answer(update, context):
    """Handle a player's plain-text answer. Returns True when consumed."""
    if not update.message or not update.message.text or not update.effective_chat:
        return False

    chat_id = update.effective_chat.id
    game = WORDSCRAMBLE_GAMES.get(chat_id)
    if not game:
        return False

    if time.monotonic() - game["started_at"] >= GAME_TIMEOUT:
        WORDSCRAMBLE_GAMES.pop(chat_id, None)
        await update.message.reply_text(
            "⏰ <b>Wordscramble expired!</b>\nStart a new one with /wordscramble.",
            parse_mode="HTML",
        )
        return True

    guess = update.message.text.strip().casefold()
    answer = game["answer"].casefold()

    if not guess:
        return True

    if guess != answer:
        await update.message.reply_text("❌ Not quite! Try again 😏")
        return True

    # Consume the round before awarding coins so a duplicate Telegram update
    # cannot pay the winner twice.
    WORDSCRAMBLE_GAMES.pop(chat_id, None)

    user = update.effective_user
    await ensure_user(user)
    await add_coins(user.id, REWARD)
    await add_xp(user.id, 10)
    await record_game_result(
        user.id,
        "WORDS",
        REWARD,
        True,
        chat_id,
    )

    name = safe_name(user.first_name or user.username or "Player")
    await update.message.reply_text(
        "🎉 <b>Correct!</b>\n\n"
        f"👑 <b>{name}</b> solved it!\n"
        f"🔤 Word: <b>{html.escape(game['answer'].upper())}</b>\n"
        f"💰 Reward: <b>+{REWARD} coins</b>\n"
        "✨ Start another round with /wordscramble",
        parse_mode="HTML",
    )
    return True
