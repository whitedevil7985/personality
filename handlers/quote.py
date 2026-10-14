"""Create a compact, readable quote bubble for /q replies."""
import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys


# Compact landscape layout: close to a chat bubble, not a giant poster.
W, H = 1000, 400


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
    # Avoid Pillow's tiny default bitmap font when system fonts are absent.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text(draw, xy, value, font, fill, **kwargs):
    try:
        draw.text(xy, value, font=font, fill=fill, **kwargs)
    except (UnicodeEncodeError, ValueError):
        # Keep the card renderable on minimal hosts without emoji glyphs.
        draw.text(xy, value.encode("ascii", "replace").decode("ascii"),
                  font=font, fill=fill, **kwargs)


def _fit_lines(draw, value, font, max_width, max_lines=3):
    value = " ".join((value or "").split()) or "(empty message)"
    words = value.split(" ")
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        try:
            width = draw.textbbox((0, 0), candidate, font=font)[2]
        except Exception:
            width = len(candidate) * 25
        if width <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + "…"
    return lines


def _gradient(size, start, end):
    width, height = size
    img = Image.new("RGB", size, start)
    d = ImageDraw.Draw(img)
    for x in range(width):
        p = x / max(1, width - 1)
        c = tuple(round(start[i] * (1-p) + end[i] * p) for i in range(3))
        d.line((x, 0, x, height), fill=c)
    return img


def _make_quote_card(name, handle, quoted_text, time_label, avatar_bytes=None):
    canvas = Image.new("RGB", (W, H), "#0c1025")
    # Soft colored glow tucked behind the message bubble.
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-110, 35, 400, 420), fill=(219, 54, 238, 105))
    gd.ellipse((580, -70, 1110, 380), fill=(17, 194, 246, 95))
    glow = glow.filter(ImageFilter.GaussianBlur(65))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((14, 14, W-14, H-14), radius=34,
                           fill=(15, 18, 43, 244), outline=(146, 99, 255, 245), width=3)
    draw.rounded_rectangle((22, 22, W-22, H-22), radius=29,
                           outline=(58, 215, 255, 170), width=2)

    # Compact sender header.
    ax, ay, ar = 42, 38, 88
    avatar = None
    if avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
            avatar = ImageOps.fit(avatar, (ar, ar), method=Image.Resampling.LANCZOS)
        except Exception:
            avatar = None
    if avatar is None:
        avatar = Image.new("RGB", (ar, ar), "#493071")
        initials = (name[:1] or "?").upper()
        ad = ImageDraw.Draw(avatar)
        f = _font(44, True)
        bbox = ad.textbbox((0, 0), initials, font=f)
        _text(ad, ((ar-(bbox[2]-bbox[0]))//2, (ar-(bbox[3]-bbox[1]))//2-4),
              initials, f, "#ffffff")
    avatar_mask = Image.new("L", (ar, ar), 0)
    ImageDraw.Draw(avatar_mask).ellipse((0, 0, ar-1, ar-1), fill=255)
    draw.ellipse((ax-4, ay-4, ax+ar+4, ay+ar+4), outline="#70efff", width=4)
    canvas.paste(avatar, (ax, ay), avatar_mask)
    draw = ImageDraw.Draw(canvas)

    _text(draw, (150, 39), name[:25], _font(39, True), "#e8a4ff")
    if handle:
        _text(draw, (152, 86), "@" + handle.lstrip("@")[:30],
              _font(21), "#afc2ff")
    draw.rounded_rectangle((824, 49, 948, 98), radius=23,
                           fill=(38, 60, 124, 245), outline=(97, 220, 255, 210), width=2)
    _text(draw, (846, 59), time_label, _font(23, True), "#ffffff")

    # Main gradient bubble: no oversized title, no footer or empty space.
    bubble = _gradient((914, 220), (234, 144, 225), (145, 229, 242))
    mask = Image.new("L", bubble.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 913, 219), radius=28, fill=255)
    canvas.paste(bubble, (43, 146), mask)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((43, 146, 957, 366), radius=28,
                           outline=(255, 232, 255, 235), width=2)
    draw.rounded_rectangle((66, 174, 74, 235), radius=4, fill="#ffffff")

    quote_font = _font(48, True)
    lines = _fit_lines(draw, quoted_text[:520], quote_font, 825, max_lines=3)
    line_height = 56
    block_height = line_height * len(lines)
    y = 174 + max(0, (164 - block_height) // 2)
    for line in lines:
        _text(draw, (98, y), line, quote_font, "#27194f",
              stroke_width=0)
        y += line_height

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    output.name = "vanya_quote.png"
    return output


async def quote_cmd(update, context):
    """Reply with /q to turn the replied-to message into a compact quote bubble."""
    message = update.effective_message
    if not message:
        return
    target = message.reply_to_message
    if not target:
        await message.reply_text(
            "💜 Kisi message par reply karke /q likho, main uska compact quote card bana dungi."
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
