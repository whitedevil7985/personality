import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def hack(update, context):
    codes = ["VANYA-42", "DELHI-7", "ARCADE-99", "CHAT-X1"]
    reward=30
    await add_coins(update.effective_user.id,reward)
    await record_game_result(update.effective_user.id, "HACK", reward, True, update.effective_chat.id)
    await update.message.reply_text(
        f"💻 Fictional hack puzzle!\nDecode this training code: <code>{random.choice(codes)}</code>\n"
        "Hint: look for the number pattern. 😈", parse_mode="HTML"
    )
