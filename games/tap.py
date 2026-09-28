import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def tap(update,context):
    n=random.randint(1,100)
    await update.message.reply_text(f"⚡ <b>TAP!</b>\nYour reaction number: {n}\nTap the button as fast as you can!",
        parse_mode="HTML",reply_markup=kb([[InlineKeyboardButton("⚡ TAP NOW",callback_data=f"tap:{update.effective_user.id}:{n}")]]))

async def tap_cb(q,data):
    _,uid,n=data.split(":")
    if int(uid)!=q.from_user.id:
        await q.answer("This tap challenge isn't yours.",show_alert=True);return
    reward=random.randint(20,100);await add_coins(q.from_user.id,reward)
    await q.edit_message_text(f"⚡ <b>FAST!</b>\n💰 +{reward} coins",parse_mode="HTML")
