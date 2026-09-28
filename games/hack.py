import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def hack(update, context):
    codes = ["VANYA-42", "DELHI-7", "ARCADE-99", "CHAT-X1"]
    await update.message.reply_text(
        f"💻 Fictional hack puzzle!\nDecode this training code: <code>{random.choice(codes)}</code>\n"
        "Hint: look for the number pattern. 😈", parse_mode="HTML"
    )
