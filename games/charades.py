import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def charades(update, context):
    prompts = ["act like a movie hero 🎬", "mime a cat 🐈", "act out a cricket shot 🏏",
               "pretend you're late for class 😂", "mime eating spicy food 🌶️"]
    await update.message.reply_text("🎭 Charades:\n" + random.choice(prompts))
