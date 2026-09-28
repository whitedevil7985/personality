import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def scribble(update, context):
    reward=15
    await add_coins(update.effective_user.id,reward)
    await record_game_result(update.effective_user.id, "SCRIBBLE", reward, True, update.effective_chat.id)
    await update.message.reply_text(
        "🖌 Scribble room is ready as a social placeholder. "
        "For a full shared canvas, connect the bot to a web-app URL via your deployment."
    )
