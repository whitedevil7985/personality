import html
import os
import random
import time
import asyncio
from datetime import datetime, timezone

from db import ensure_user, add_coins, record_game_result, games

REWARD = 25
GAME_TIMEOUT = 90
JUMBLE_ROUNDS = 7

# One active 7-round Jumble session per chat.
JUMBLE_GAMES = {}
_JUMBLE_LOCK = asyncio.Lock()


def _load_jumble_words():
    """Load the external Jumble word bank."""
    fallback = [
        "telegram", "galaxy", "phantom", "python", "diamond",
        "rainbow", "vanya", "dragon", "keyboard", "adventure",
        "birthday", "champion", "treasure", "sunshine", "moonlight",
    ]
    path = os.path.join(os.path.dirname(__file__), "jumble_words.txt")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            words = []
            seen = set()
            for line in handle:
                word = line.strip().casefold()
                if not word.isalpha() or not (4 <= len(word) <= 10) or word in seen:
                    continue
                seen.add(word)
                words.append(word)
        if len(words) >= 1000:
            return words
    except Exception as exc:
        print(f"[Jumble] external word bank load failed: {type(exc).__name__}: {exc}")
    return fallback


WORDS = _load_jumble_words()


async def _next_unique_word():
    """Reserve a Jumble word permanently so it is never recycled."""
    async with _JUMBLE_LOCK:
        state_id = "jumble_pool"
        state = await games.find_one({"_id": state_id}) or {}
        used = {
            str(x).strip().casefold()
            for x in state.get("used_words", [])
            if str(x).strip()
        }
        available = [word for word in WORDS if word.casefold() not in used]
        if not available:
            return None

        word = random.choice(available)
        await games.update_one(
            {"_id": state_id},
            {
                "$addToSet": {"used_words": word},
                "$set": {
                    "total_words": len(WORDS),
                    "updated_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )
        return word


def _scramble(word):
    letters = list(word)
    for _ in range(12):
        random.shuffle(letters)
        value = "".join(letters)
        if value != word:
            return value
    return "".join(reversed(letters))


async def _send_round(update, answer, round_number):
    scrambled = _scramble(answer)
    JUMBLE_GAMES[update.effective_chat.id] = {
        "answer": answer.casefold(),
        "scrambled": scrambled,
        "started_at": time.monotonic(),
        "round": int(round_number),
        "total": JUMBLE_ROUNDS,
    }

    await update.message.reply_text(
        "🔤 <b>JUMBLE</b>\n\n"
        f"🧩 Unscramble: <b>{html.escape(scrambled.upper())}</b>\n\n"
        f"🔎 <b>Round:</b> {round_number}/{JUMBLE_ROUNDS}\n"
        f"💰 <b>Reward:</b> +{REWARD} coins\n"
        "⏱️ 90 seconds\n"
        "💬 Type the answer directly!",
        parse_mode="HTML",
    )


async def jumble(update, context):
    if not update.message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    current = JUMBLE_GAMES.get(chat_id)
    if current and time.monotonic() - current["started_at"] < GAME_TIMEOUT:
        await update.message.reply_text(
            f"🔤 <b>Jumble already running!</b>\n"
            f"Round {current.get('round', 1)}/{current.get('total', JUMBLE_ROUNDS)}. "
            "Type the answer directly.",
            parse_mode="HTML",
        )
        return

    if current:
        JUMBLE_GAMES.pop(chat_id, None)

    answer = await _next_unique_word()
    if answer is None:
        await update.message.reply_text(
            "🏁 <b>JUMBLE WORD POOL FINISHED!</b>\n"
            "Saare available words already use ho chuke hain. "
            "Koi purana word repeat nahi kiya jayega.",
            parse_mode="HTML",
        )
        return

    await _send_round(update, answer, 1)


async def jumble_answer(update, context):
    if not update.message or not update.message.text or not update.effective_chat:
        return False

    # Replying to another human is normal group conversation, not a guess.
    if (
        update.effective_chat.type in ("group", "supergroup")
        and update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.id != context.bot.id
    ):
        return False

    chat_id = update.effective_chat.id
    game = JUMBLE_GAMES.get(chat_id)
    if not game:
        return False

    if time.monotonic() - game["started_at"] >= GAME_TIMEOUT:
        JUMBLE_GAMES.pop(chat_id, None)
        await update.message.reply_text(
            "⏰ <b>Jumble expired!</b> Start a new 7-round session with /jumble.",
            parse_mode="HTML",
        )
        return True

    guess = update.message.text.strip().casefold()
    if not guess:
        return True

    if guess != game["answer"]:
        await update.message.reply_text("❌ Not quite! Try again 😏")
        return True

    round_number = int(game.get("round", 1))
    total_rounds = int(game.get("total", JUMBLE_ROUNDS))

    # Consume the round before awarding so repeated Telegram updates cannot
    # pay twice for the same answer.
    JUMBLE_GAMES.pop(chat_id, None)

    user = update.effective_user
    await ensure_user(user)
    await add_coins(user.id, REWARD)
    await record_game_result(user.id, "JUMBLE", REWARD, True, chat_id)

    if round_number >= total_rounds:
        bonus = REWARD
        await add_coins(user.id, bonus)
        await record_game_result(user.id, "JUMBLE", bonus, True, chat_id)
        await update.message.reply_html(
            "🏆 <b>JUMBLE COMPLETE!</b>\n\n"
            f"👑 <b>{html.escape(user.first_name or 'Player')}</b> completed all "
            f"<b>{total_rounds}/{total_rounds}</b> rounds!\n"
            f"🔤 Last word: <b>{html.escape(game['answer'].upper())}</b>\n"
            f"💰 Round reward: <b>+{REWARD} coins</b>\n"
            f"🎁 Completion bonus: <b>+{bonus} coins</b>\n"
            "✨ Start another 7-round session with /jumble"
        )
        return True

    await update.message.reply_html(
        "🎉 <b>Correct!</b>\n\n"
        f"👑 <b>{html.escape(user.first_name or 'Player')}</b> solved it!\n"
        f"🔤 Word: <b>{html.escape(game['answer'].upper())}</b>\n"
        f"🔎 <b>Round:</b> {round_number}/{total_rounds}\n"
        f"💰 Reward: <b>+{REWARD} coins</b>"
    )

    next_answer = await _next_unique_word()
    if next_answer is None:
        await update.message.reply_html(
            "🏁 <b>JUMBLE WORD POOL FINISHED!</b>\n\n"
            "✅ No old word will be repeated. Add more words to continue."
        )
        return True

    await _send_round(update, next_answer, round_number + 1)
    return True
