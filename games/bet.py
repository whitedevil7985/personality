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
    """Create a simple, highly readable BET result card."""
    width, height = 1200, 700
    bg = (12, 17, 27)
    accent = (25, 150, 85) if won else (190, 55, 55)

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    # Main card
    draw.rounded_rectangle(
        (40, 45, width - 40, height - 45),
        radius=35,
        fill=(29, 38, 54),
        outline=accent,
        width=7,
    )

    # Header
    draw.rounded_rectangle(
        (65, 75, width - 65, 205),
        radius=28,
        fill=accent,
    )

    title = "YOU WON!" if won else "YOU LOST!"
    amount_text = f"+{amount:,} COINS" if won else f"-{amount:,} COINS"
    message = "Your bet paid off!" if won else "Better luck next time!"

    title_font = _bet_font(70, True)
    amount_font = _bet_font(64, True)
    small_font = _bet_font(36, False)
    balance_font = _bet_font(40, True)
    coin_font = _bet_font(46, True)

    def centered(text, font, y, fill):
        box = draw.textbbox((0, 0), text, font=font)
        x = (width - (box[2] - box[0])) / 2
        draw.text((x, y), text, font=font, fill=fill)

    centered(title, title_font, 95, (255, 255, 255))
    centered(amount_text, amount_font, 270, accent)
    centered(message, small_font, 375, (220, 225, 235))
    centered(f"Balance: {balance:,} coins", balance_font, 460, (255, 255, 255))

    # Large coin icon
    cx, cy = width // 2, 610
    draw.ellipse(
        (cx - 48, cy - 48, cx + 48, cy + 48),
        fill=(242, 190, 50),
        outline=(255, 230, 120),
        width=5,
    )
    box = draw.textbbox((0, 0), "$", font=coin_font)
    draw.text(
        (cx - (box[2] - box[0]) / 2, cy - (box[3] - box[1]) / 2 - 5),
        "$",
        font=coin_font,
        fill=(100, 70, 10),
    )

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
