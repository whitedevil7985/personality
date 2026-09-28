import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def wordchain(update, context):
    word = context.args[0].lower() if context.args else ""
    if not word.isalpha() or len(word) < 2:
        await update.message.reply_text("Usage: /wordchain <word>")
        return
    reward=20
    await add_coins(update.effective_user.id,reward)
    await record_game_result(update.effective_user.id, "WORDCHAIN", reward, True, update.effective_chat.id)
    reply = random.choice(["nice!", "good one 👀", "my turn 😎", "solid word!"])
    await update.message.reply_text(f"🔗 {reply} Next word should start with <b>{html.escape(word[-1].upper())}</b>.", parse_mode="HTML")
