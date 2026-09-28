import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users
WORDS=["telegram","galaxy","phantom","python","diamond","rainbow","vanya","dragon","keyboard"]

async def jumble(update,context):
    w=random.choice(WORDS);sh=list(w);random.shuffle(sh)
    await update.message.reply_text(f"🔤 Unscramble: <b>{''.join(sh)}</b>\nReply with the answer.",parse_mode="HTML")
