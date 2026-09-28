import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result
WORDS=["telegram","galaxy","phantom","python","diamond","rainbow","vanya","dragon","keyboard"]

async def jumble(update,context):
    w=random.choice(WORDS);sh=list(w);random.shuffle(sh)
    reward=25
    await add_coins(update.effective_user.id,reward)
    await record_game_result(update.effective_user.id, "JUMBLE", reward, True, update.effective_chat.id)
    await update.message.reply_text(f"🔤 Unscramble: <b>{''.join(sh)}</b>\nReply with the answer.",parse_mode="HTML")
