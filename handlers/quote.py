"""Create a mobile-first, attractive quote card for /q replies."""
import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys


# Near-square image: Telegram can show it larger on phones than a very wide banner.
W, H = 900, 800


def _font(size, bold=False):
    candidates = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
         "DejaVuSans-Bold.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
         "DejaVuSans.ttf"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, ValueError):
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text(draw, xy, value, font, fill, **kwargs):
    try:
        draw.text(xy, value, font=font, fill=fill, **kwargs)
    except (UnicodeEncodeError, ValueError):
        safe = value.encode("ascii", "replace").decode("ascii")
        draw.text(xy, safe, font=font, fill=fill, **kwargs)


def _measure(draw, value, font):
    try:
        return draw.textbbox((0, 0), value, font=font)[2]
    except Exception:
        return len(value) * 25


def _fit_lines(draw, value, font, max_width, max_lines=6):
    value = " ".join((value or "").split()) or "(empty message)"
    words = value.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _measure(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            # Break a single very long word rather than let it leave the card.
            current = ""
            fragment = ""
            for char in word:
                if _measure(draw, fragment + char, font) > max_width and fragment:
                    lines.append(fragment)
                    fragment = char
                else:
                    fragment += char
            current = fragment
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + "…"
    return lines


def _gradient(size, start, end):
    width, height = size
    img = Image.new("RGB", size, start)
    draw = ImageDraw.Draw(img)
    for x in range(width):
        p = x / max(1, width - 1)
        color = tuple(round(start[i] * (1-p) + end[i] * p) for i in range(3))
        draw.line((x, 0, x, height), fill=color)
    return img


def _make_quote_card(name, handle, quoted_text, time_label, avatar_bytes=None):
    # Premium midnight background with restrained purple/cyan glow.
    canvas = Image.new("RGB", (W, H), "#090d20")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-150, 0, 360, 530), fill=(220, 52, 242, 115))
    gd.ellipse((530, -90, 1030, 520), fill=(0, 195, 255, 105))
    gd.ellipse((290, 530, 760, 900), fill=(95, 48, 210, 48))
    glow = glow.filter(ImageFilter.GaussianBlur(75))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow)
    draw = ImageDraw.Draw(canvas)

    # Card frame with clean margins for Telegram/mobile scaling.
    draw.rounded_rectangle((16, 16, W-16, H-16), radius=36,
                           fill=(12, 16, 41, 245), outline=(176, 93, 255, 255), width=4)
    draw.rounded_rectangle((25, 25, W-25, H-25), radius=29,
                           outline=(64, 219, 255, 205), width=2)

    # Sender avatar, cropped circularly.
    ax, ay, ar = 48, 48, 102
    avatar = None
    if avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
            avatar = ImageOps.fit(avatar, (ar, ar), method=Image.Resampling.LANCZOS)
        except Exception:
            avatar = None
    if avatar is None:
        avatar = Image.new("RGB", (ar, ar), "#493071")
        ad = ImageDraw.Draw(avatar)
        initial = (name[:1] or "?").upper()
        f = _font(47, True)
        bbox = ad.textbbox((0, 0), initial, font=f)
        _text(ad, ((ar-(bbox[2]-bbox[0]))//2, (ar-(bbox[3]-bbox[1]))//2-4),
              initial, f, "#ffffff")
    avatar_mask = Image.new("L", (ar, ar), 0)
    ImageDraw.Draw(avatar_mask).ellipse((0, 0, ar-1, ar-1), fill=255)
    draw.ellipse((ax-5, ay-5, ax+ar+5, ay+ar+5), outline="#71f2ff", width=5)
    canvas.paste(avatar, (ax, ay), avatar_mask)
    draw = ImageDraw.Draw(canvas)

    display_name = (name or "Unknown")[:25]
    _text(draw, (177, 48), display_name, _font(38, True), "#e7a3ff")
    if handle:
        _text(draw, (180, 96), "@" + handle.lstrip("@")[:28],
              _font(21), "#b7c7ff")

    # Small VANYA badge and time occupy separate areas to prevent overlap.
    draw.rounded_rectangle((180, 128, 300, 162), radius=17,
                           fill=(103, 49, 162, 225), outline=(222, 135, 255, 180), width=1)
    _text(draw, (197, 134), "✦ QUOTE", _font(17, True), "#ffffff")
    draw.rounded_rectangle((724, 63, 855, 111), radius=24,
                           fill=(36, 60, 122, 245), outline=(99, 220, 255, 225), width=2)
    _text(draw, (746, 73), time_label, _font(23, True), "#ffffff")

    # Main quote bubble; roomier and taller so text never feels squeezed on phones.
    bubble = _gradient((812, 478), (233, 135, 224), (115, 220, 242))
    bubble_mask = Image.new("L", bubble.size, 0)
    ImageDraw.Draw(bubble_mask).rounded_rectangle((0, 0, 811, 477), radius=32, fill=255)
    canvas.paste(bubble, (44, 190), bubble_mask)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((44, 190, 856, 668), radius=32,
                           outline=(255, 231, 255, 245), width=3)

    # Quote marker and subtle inset label.
    draw.rounded_rectangle((70, 219, 80, 286), radius=5, fill="#ffffff")
    _text(draw, (99, 225), "MESSAGE", _font(19, True), "#493078")

    clean_message = (quoted_text or " ").strip()[:650]
    selected_font = _font(49, True)
    selected_lines = _fit_lines(draw, clean_message, selected_font, 704, max_lines=6)
    line_height = 59
    # If there are many lines, scale the font down a little while keeping it readable.
    if len(selected_lines) >= 5:
        selected_font = _font(40, True)
        selected_lines = _fit_lines(draw, clean_message, selected_font, 704, max_lines=6)
        line_height = 50
    if len(selected_lines) >= 6:
        selected_font = _font(35, True)
        selected_lines = _fit_lines(draw, clean_message, selected_font, 704, max_lines=6)
        line_height = 44
    block_height = len(selected_lines) * line_height
    y = 315 + max(0, (315 - block_height) // 2)
    for line in selected_lines:
        _text(draw, (99, y), line, selected_font, "#281748")
        y += line_height

    # Footer branding is subtle and stays inside the frame.
    _text(draw, (52, 711), "VANYA", _font(22, True), "#e4caff")
    _text(draw, (154, 713), "REAL WORDS  •  BETTER VIBES", _font(19, True), "#82edff")
    # Tiny decorative sparkles in corners, well clear of the quote text.
    draw.ellipse((818, 711, 830, 723), outline="#ff83e8", width=3)
    draw.ellipse((838, 727, 847, 736), outline="#8da7ff", width=2)

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    output.name = "vanya_quote.png"
    return output


async def quote_cmd(update, context):
    """Reply with /q to turn the replied-to message into a mobile-first quote card."""
    message = update.effective_message
    if not message:
        return
    target = message.reply_to_message
    if not target:
        await message.reply_text(
            "💜 Kisi message par reply karke /q likho, main uska stylish quote card bana dungi."
        )
        return

    user = target.from_user
    name = (user.full_name if user else (target.sender_chat.title if target.sender_chat else target.chat.title)) or "Unknown"
    username = (user.username if user else None)
    if target.text:
        quoted_text = target.text
    elif target.caption:
        quoted_text = target.caption
    elif target.sticker:
        quoted_text = "Sticker message " + (target.sticker.emoji or "")
    elif target.photo:
        quoted_text = "Photo message"
    elif target.video:
        quoted_text = "Video message"
    elif target.animation:
        quoted_text = "GIF message"
    elif target.document:
        quoted_text = "File: " + (target.document.file_name or "document")
    elif target.voice:
        quoted_text = "Voice message"
    else:
        quoted_text = "A message from the group"
    quoted_text = quoted_text[:650]

    time_label = target.date.strftime("%H:%M") if target.date else datetime.now().strftime("%H:%M")
    avatar_bytes = None
    if user:
        try:
            photos = await context.bot.get_user_profile_photos(user_id=user.id, limit=1)
            if photos.total_count and photos.photos:
                photo_file = await context.bot.get_file(photos.photos[0][-1].file_id)
                avatar_bytes = bytes(await photo_file.download_as_bytearray())
        except Exception:
            avatar_bytes = None

    try:
        card = _make_quote_card(name, username, quoted_text, time_label, avatar_bytes)
        await message.reply_photo(
            photo=card,
            caption="✨ Quoted by Vanya",
            reply_to_message_id=target.message_id,
            allow_sending_without_reply=True,
        )
    except Exception as exc:
        print(f"[QuoteCard] {type(exc).__name__}: {exc}")
        await message.reply_text("😿 Quote card abhi nahi ban paaya. Thodi der baad phir try karna.")
