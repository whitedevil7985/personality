import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def wordseek(update, context):
    words = ["VANYA", "DELHI", "ARCADE", "CHAT", "FRIEND"]
    answer = random.choice(words)
    scrambled = "".join(random.sample(answer, len(answer)))
    await update.message.reply_text(f"🔎 Wordseek: find the hidden word from these letters:\n\n`{scrambled}`\n\nReply with `/answer {answer}`", parse_mode="Markdown")


async def answer(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /answer <word>")
        return
    await update.message.reply_text("🎉 Nice guess! If that was your Wordseek answer, you've got it. +50 XP!")
    await add_xp(update.effective_user.id, 50)
