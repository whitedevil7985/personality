import html
import html
import random
import time
from datetime import datetime, timezone

from telegram import InlineKeyboardButton

from games.common import kb, safe_name
from db import ensure_user, add_coins, add_xp, record_game_result, games


# One active puzzle per chat.
WORDSCRAMBLE_GAMES = {}
_WORDSCRAMBLE_LOCK = None

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


async def _next_unique_word():
    """Reserve a word permanently in MongoDB so it never repeats after a restart."""
    global _WORDSCRAMBLE_LOCK
    if _WORDSCRAMBLE_LOCK is None:
        import asyncio
        _WORDSCRAMBLE_LOCK = asyncio.Lock()

    async with _WORDSCRAMBLE_LOCK:
        state_id = "wordscramble_pool"
        state = await games.find_one({"_id": state_id}) or {}
        used = {str(x).strip().casefold() for x in state.get("used_words", []) if str(x).strip()}
        available = [word for word in WORDS if word.casefold() not in used]
        if not available:
            return None
        word = random.choice(available)
        await games.update_one(
            {"_id": state_id},
            {"$addToSet": {"used_words": word},
             "$set": {"updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return word


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

    answer = await _next_unique_word()
    if answer is None:
        await update.message.reply_text(
            "🔤 <b>Wordscramble word pool finished!</b>\n"
            "All current words have already been used. Add more words to continue.",
            parse_mode="HTML",
        )
        return

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
