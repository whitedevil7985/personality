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
    """Create the BET result card in memory, so no image files are required."""
    width, height = 1200, 630
    # Dark casino-style background with a different accent for win/loss.
    bg = (18, 24, 35)
    accent = (46, 204, 113) if won else (231, 76, 60)
    accent_dark = (25, 112, 65) if won else (125, 38, 31)

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    # Soft card + accent bands.
    draw.rounded_rectangle(
        (35, 35, width - 35, height - 35),
        radius=42,
        fill=(27, 36, 51),
        outline=accent,
        width=5,
    )
    draw.rounded_rectangle(
        (65, 65, width - 65, 185),
        radius=30,
        fill=accent_dark,
    )

    title = "YOU GAINED" if won else "YOU LOST"
    title_font = _bet_font(68, True)
    amount_font = _bet_font(100, True)
    small_font = _bet_font(34, False)
    balance_font = _bet_font(42, True)

    def centered(text, font, y, fill):
        box = draw.textbbox((0, 0), text, font=font)
        x = (width - (box[2] - box[0])) / 2
        draw.text((x, y), text, font=font, fill=fill)

    centered(title, title_font, 83, (255, 255, 255))
    centered(f"{amount:,} COINS", amount_font, 225, accent)
    centered(
        "Your bet paid off!" if won else "Better luck next time!",
        small_font,
        355,
        (210, 220, 235),
    )
    centered(f"Balance: {balance:,} coins", balance_font, 430, (255, 255, 255))

    # Decorative casino chips.
    for x, y, r in ((115, 525, 34), (180, 550, 22), (1020, 525, 34), (1085, 550, 22)):
        draw.ellipse((x-r, y-r, x+r, y+r), fill=accent_dark, outline=accent, width=5)

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
