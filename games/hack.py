import html
import random
import time

from db import ensure_user, add_coins, record_game_result

REWARD = 30
GAME_TIMEOUT = 90
HACK_GAMES = {}


def _new_puzzle():
    puzzles = [
        ("2, 4, 6, ?", ("8",)),
        ("5, 10, 15, ?", ("20",)),
        ("1, 3, 6, 10, ?", ("15",)),
        ("10, 8, 6, ?", ("4",)),
    ]
    return random.choice(puzzles)


async def hack(update, context):
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    current = HACK_GAMES.get(chat_id)
    if current and time.monotonic() - current["started_at"] < GAME_TIMEOUT:
        await update.message.reply_text("💻 <b>Hack puzzle already running!</b> Solve the current code first.", parse_mode="HTML")
        return

    puzzle, answers = _new_puzzle()
    HACK_GAMES[chat_id] = {
        "puzzle": puzzle,
        "answers": answers,
        "started_at": time.monotonic(),
    }
    await update.message.reply_html(
        "💻 <b>HACK PUZZLE</b>\n\n"
        f"🔐 Decode the sequence: <code>{html.escape(puzzle)}</code>\n\n"
        f"🏆 Reward: <b>+{REWARD} coins</b>\n"
        "💬 Type the answer directly.\n"
        "⏱️ 90 seconds."
    )


async def hack_answer(update, context):
    if not update.message or not update.message.text or not update.effective_chat:
        return False
    chat_id = update.effective_chat.id
    game = HACK_GAMES.get(chat_id)
    if not game:
        return False

    if time.monotonic() - game["started_at"] >= GAME_TIMEOUT:
        HACK_GAMES.pop(chat_id, None)
        await update.message.reply_text("⏰ <b>Hack puzzle expired!</b> Start again with /hack.", parse_mode="HTML")
        return True

    guess = update.message.text.strip().casefold()
    if not guess:
        return True
    if guess not in {str(x).casefold() for x in game["answers"]}:
        await update.message.reply_text("❌ Access denied 😏", parse_mode="HTML")
        return True

    HACK_GAMES.pop(chat_id, None)
    user = update.effective_user
    await ensure_user(user)
    await add_coins(user.id, REWARD)
    await record_game_result(user.id, "HACK", REWARD, True, chat_id)
    await update.message.reply_html(
        "✅ <b>ACCESS GRANTED!</b>\n\n"
        f"👑 <b>{html.escape(user.first_name or 'Player')}</b> cracked it!\n"
        f"💰 Reward: <b>+{REWARD} coins</b>\n"
        "✨ Start another with /hack"
    )
    return True
