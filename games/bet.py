import html
import io
import os
import random

from telegram import InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont

from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result


def _bet_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _make_bet_result_image(won: bool, amount: int, balance: int):
    """Create a clean, easy-to-understand BET result card."""
    width, height = 1000, 620
    bg = (13, 18, 28)
    accent = (35, 180, 105) if won else (205, 65, 65)
    panel = (28, 36, 50)
    white = (250, 250, 252)
    muted = (190, 198, 210)

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (25, 25, width - 25, height - 25),
        radius=32,
        fill=panel,
        outline=accent,
        width=6,
    )
    draw.rounded_rectangle(
        (55, 55, width - 55, 185),
        radius=24,
        fill=accent,
    )

    title = "BET WON" if won else "BET LOST"
    result = f"+{amount:,} COINS" if won else f"-{amount:,} COINS"
    subtitle = "YOU GAINED COINS" if won else "YOU LOST COINS"

    title_font = _bet_font(68, True)
    result_font = _bet_font(72, True)
    subtitle_font = _bet_font(32, True)
    balance_font = _bet_font(34, True)
    label_font = _bet_font(28, False)

    def centered(text, font, y, fill):
        box = draw.textbbox((0, 0), text, font=font)
        x = (width - (box[2] - box[0])) / 2
        draw.text((x, y), text, font=font, fill=fill)

    centered(title, title_font, 83, white)
    centered(result, result_font, 225, accent)
    centered(subtitle, subtitle_font, 325, white)

    draw.line((180, 385, width - 180, 385), fill=(70, 80, 96), width=2)
    centered("CURRENT BALANCE", label_font, 410, muted)
    centered(f"{balance:,} COINS", balance_font, 455, white)

    # Simple visual checkmark / cross, drawn as shapes (no Telegram emoji).
    cx, cy = width // 2, 565
    draw.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), fill=accent)
    if won:
        draw.line((cx - 14, cy, cx - 3, cy + 12), fill=white, width=7)
        draw.line((cx - 3, cy + 12, cx + 18, cy - 13), fill=white, width=7)
    else:
        draw.line((cx - 14, cy - 14, cx + 14, cy + 14), fill=white, width=7)
        draw.line((cx + 14, cy - 14, cx - 14, cy + 14), fill=white, width=7)

    output = io.BytesIO()
    output.name = "bet_result.png"
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output

async def bet(update, context):
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError, TypeError):
        await update.message.reply_text("Usage: /bet <amount>")
        return

    u = await get_user(update.effective_user.id)
    if not u or amount <= 0 or u.get("coins", 0) < amount:
        await update.message.reply_text("❌ Invalid amount.")
        return

    won = random.random() < 0.48

    if won:
        await add_coins(update.effective_user.id, amount)
        await record_game_result(
            update.effective_user.id, "BET", amount, True, update.effective_chat.id
        )
        balance = int(u.get("coins", 0)) + amount
        caption = f"🎉 You gained {amount:,} coins!"
    else:
        await add_coins(update.effective_user.id, -amount)
        await record_game_result(
            update.effective_user.id, "BET", 0, False, update.effective_chat.id
        )
        balance = int(u.get("coins", 0)) - amount
        caption = f"💥 You lost {amount:,} coins."

    image = _make_bet_result_image(won, amount, balance)
    try:
        await update.message.reply_photo(photo=image, caption=caption)
    finally:
        image.close()
