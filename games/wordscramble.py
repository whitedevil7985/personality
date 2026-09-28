import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def wordscramble(update, context):
    words = ["delhi", "vanya", "friendship", "telegram", "arcade", "coffee", "mystery"]
    answer = random.choice(words)
    scrambled = "".join(random.sample(answer, len(answer)))
    await update.message.reply_text(f"🔤 Unscramble: <b>{scrambled}</b>", parse_mode="HTML")
