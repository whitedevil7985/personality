import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

async def charades(update, context):
    prompts = ["act like a movie hero 🎬", "mime a cat 🐈", "act out a cricket shot 🏏",
               "pretend you're late for class 😂", "mime eating spicy food 🌶️"]
    reward=25
    await add_coins(update.effective_user.id,reward)
    await record_game_result(update.effective_user.id, "CHARADES", reward, True, update.effective_chat.id)
    await update.message.reply_text("🎭 Charades:\n" + random.choice(prompts) + f"\n\n💰 +{reward} coins • 🏆 +{reward} points")
