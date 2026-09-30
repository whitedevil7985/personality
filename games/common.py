import html
import random
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import get_user, add_coins, add_xp, users

# Telegram custom-emoji markup must never be exposed by game messages.
# Games can safely pass their normal text through this helper before sending.
def sanitize_game_text(text):
    text = str(text or "")
    text = re.sub(r"<tg-emoji\\b[^>]*>(.*?)</tg-emoji>", r"\\1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<tg-emoji\\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</tg-emoji>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"emoji[-_ ]?id\\s*=\\s*[\\\"']?[^\\s>\\\"']+[\\\"']?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"emoji[-_ ]?id\\s*[:=]\\s*\\d+", "", text, flags=re.IGNORECASE)
    return text

def kb(rows):
    return InlineKeyboardMarkup(rows)

def safe_name(name):
    return html.escape(sanitize_game_text(name or "Player"))
