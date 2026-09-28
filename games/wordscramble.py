import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def wordscramble(update, context):
    words = ["delhi", "vanya", "friendship", "telegram", "arcade", "coffee", "mystery"]
    answer = random.choice(words)
    scrambled = "".join(random.sample(answer, len(answer)))
    reward=25
    await add_coins(update.effective_user.id,reward)
    await record_game_result(update.effective_user.id, "WORDS", reward, True, update.effective_chat.id)
    await update.message.reply_text(f"🔤 Unscramble: <b>{scrambled}</b>", parse_mode="HTML")
