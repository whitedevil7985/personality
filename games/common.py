import html
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import get_user, add_coins, add_xp, users

def kb(rows):
    return InlineKeyboardMarkup(rows)

def safe_name(name):
    return html.escape(name or "Player")
