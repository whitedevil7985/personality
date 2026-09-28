import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from config import OWNER_ID
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

WORDS = [
    "VANYA", "DELHI", "ARCADE", "CHAT", "FRIEND",
    "MUSIC", "RAIN", "MAGIC", "SMILE", "DREAM",
    "APPLE", "MANGO", "RIVER", "CLOUD", "HEART",
    "TIGER", "SPACE", "ROBOT", "PARTY", "NIGHT",
    "SUMMER", "WINTER", "FLOWER", "FOREST", "GALAXY",
]
WORDSEEK_GAMES = {}
WORDSEEK_QUEUE = []


def _next_wordseek_word():
    """Return a fresh Wordseek word without repetition until the pool resets."""
    global WORDSEEK_QUEUE
    if not WORDSEEK_QUEUE:
        WORDSEEK_QUEUE = WORDS[:]
        random.shuffle(WORDSEEK_QUEUE)
    return WORDSEEK_QUEUE.pop()


def _scramble_word(answer: str) -> str:
    """Shuffle letters while trying not to return the original word."""
    if len(answer) < 2:
        return answer
    letters = list(answer)
    for _ in range(8):
        random.shuffle(letters)
        scrambled = "".join(letters)
        if scrambled != answer:
            return scrambled
    return "".join(letters)


async def _start_wordseek_round(update, answer: str, prefix: str = "🔎 <b>Wordseek</b>"):
    chat_id = update.effective_chat.id
    scrambled = _scramble_word(answer)
    WORDSEEK_GAMES[chat_id] = {
        "answer": answer,
        "found": False,
        "created_by": update.effective_user.id if update.effective_user else None,
    }
    await update.message.reply_text(
        f"{prefix}: find the hidden word from these letters:\n\n"
        f"<code>{scrambled}</code>\n\n"
        "Reply with <code>/answer &lt;word&gt;</code>",
        parse_mode="HTML",
    )


async def wordseek(update, context):
    answer = _next_wordseek_word()
    await _start_wordseek_round(update, answer)


async def answer(update, context):
    chat_id = update.effective_chat.id
    game = WORDSEEK_GAMES.get(chat_id)
    if not game:
        await update.message.reply_text("❌ No active Wordseek game here. Start one with /wordseek.")
        return
    if game.get("found"):
        await update.message.reply_text("👀 Wordseek is already solved. Start a new one with /wordseek.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /answer <word>")
        return

    guess = "".join(context.args).strip().upper()
    if guess != game["answer"]:
        await update.message.reply_text("❌ Not quite 😅 Try again!")
        return

    game["found"] = True
    uid = update.effective_user.id
    await add_xp(uid, 50)
    await add_coins(uid, 50)
    await record_game_result(uid, "WORDSEEK", 50, True, chat_id)
    await update.message.reply_text(
        "🎉 <b>Correct!</b> You found the Wordseek word!\n"
        "⭐ +50 XP  •  💰 +50 coins  •  🏆 +50 points",
        parse_mode="HTML",
    )

    # Automatically start the next round in the same chat so players can
    # continue solving without sending /wordseek again.
    next_answer = _next_wordseek_word()
    await _start_wordseek_round(
        update,
        next_answer,
        prefix="➡️ <b>Next Wordseek</b>",
    )


async def reveal_wordseek(update, context):
    """Owner/Sudo Wordseek answer reveal; never exposes the answer to groups."""
    if not update.effective_user:
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return
    uid = update.effective_user.id
    if uid != OWNER_ID:
        from db import get_user
        u = await get_user(uid)
        if uid not in getattr(__import__("config"), "SUDO_IDS", set()) and not (u and u.get("is_sudo")):
            await update.message.reply_text("⛔ Owner/Sudo only.")
            return

    chat_id = update.effective_chat.id if update.effective_chat else None
    game = WORDSEEK_GAMES.get(chat_id)
    if not game:
        await update.message.reply_text("❌ No active Wordseek game in this chat.")
        return

    answer = game.get("answer", "").upper()
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=(
                    f"📩 <b>Wordseek Answer — {html.escape(update.effective_chat.title or 'Group')}</b>\n\n"
                    f"🔐 <code>{html.escape(answer)}</code>"
                ),
                parse_mode="HTML",
            )
            await update.message.reply_text("✅ Wordseek answer sent to your private chat.")
        except Exception:
            await update.message.reply_text(
                "⚠️ I couldn't DM you. Open a private chat with Vanya first, then use the Owner Panel."
            )
        return

    await update.message.reply_html(
        f"🔐 <b>Wordseek Answer</b>\n\n<code>{html.escape(answer)}</code>"
    )
