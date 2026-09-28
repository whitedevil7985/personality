import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users
rps_choices=['rock','paper','scissors']

async def rps(update,context):
    choice=(context.args[0].lower() if context.args else "").strip()
    if choice not in rps_choices:
        await update.message.reply_text("Usage: /rps rock | paper | scissors");return
    bot=random.choice(rps_choices)
    win=(choice=="rock" and bot=="scissors") or (choice=="paper" and bot=="rock") or (choice=="scissors" and bot=="paper")
    result="🏆 You win!" if win else ("🤝 Draw!" if choice==bot else "😈 Bot wins!")
    if win: await add_coins(update.effective_user.id,100)
    await update.message.reply_text(f"🪨 {choice}  vs  {bot}\n{result}")
