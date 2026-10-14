"""Create a mobile-friendly, readable quote card for /q replies."""
import io
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys


# Near-square ratio gives the card more height on phones; large fonts remain
# clear after Telegram scales the image to the screen width.
W, H = 900, 660


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
        draw.text(xy, value.encode("ascii", "replace").decode("ascii"),
                  font=font, fill=fill, **kwargs)


def _fit_lines(draw, value, font, max_width, max_lines=4):
    value = " ".join((value or "").split()) or "(empty message)"
    words = value.split(" ")
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        try:
            width = draw.textbbox((0, 0), candidate, font=font)[2]
        except Exception:
            width = len(candidate) * 28
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
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-120, 30, 330, 490), fill=(219, 54, 238, 112))
    gd.ellipse((540, -55, 1010, 500), fill=(17, 194, 246, 100))
    glow = glow.filter(ImageFilter.GaussianBlur(68))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((13, 13, W-13, H-13), radius=32,
                           fill=(15, 18, 43, 247), outline=(146, 99, 255, 245), width=3)
    draw.rounded_rectangle((22, 22, W-22, H-22), radius=26,
                           outline=(58, 215, 255, 185), width=2)

    # Sender header; all elements stay away from the image edges.
    ax, ay, ar = 43, 39, 88
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
        f = _font(43, True)
        bbox = ad.textbbox((0, 0), initials, font=f)
        _text(ad, ((ar-(bbox[2]-bbox[0]))//2, (ar-(bbox[3]-bbox[1]))//2-4),
              initials, f, "#ffffff")
    avatar_mask = Image.new("L", (ar, ar), 0)
    ImageDraw.Draw(avatar_mask).ellipse((0, 0, ar-1, ar-1), fill=255)
    draw.ellipse((ax-4, ay-4, ax+ar+4, ay+ar+4), outline="#70efff", width=4)
    canvas.paste(avatar, (ax, ay), avatar_mask)
    draw = ImageDraw.Draw(canvas)

    _text(draw, (151, 39), name[:22], _font(36, True), "#e8a4ff")
    if handle:
        _text(draw, (153, 82), "@" + handle.lstrip("@")[:26],
              _font(20), "#afc2ff")
    draw.rounded_rectangle((724, 53, 858, 100), radius=22,
                           fill=(38, 60, 124, 245), outline=(97, 220, 255, 220), width=2)
    _text(draw, (745, 64), time_label, _font(23, True), "#ffffff")

    # Quote panel uses nearly the full width and a taller message area for phones.
    bubble = _gradient((814, 386), (234, 144, 225), (145, 229, 242))
    mask = Image.new("L", bubble.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 813, 385), radius=28, fill=255)
    canvas.paste(bubble, (43, 151), mask)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((43, 151, 857, 537), radius=28,
                           outline=(255, 232, 255, 235), width=2)
    draw.rounded_rectangle((66, 181, 74, 246), radius=4, fill="#ffffff")

    quote_font = _font(49, True)
    lines = _fit_lines(draw, quoted_text[:650], quote_font, 720, max_lines=4)
    line_height = 61
    block_height = line_height * len(lines)
    y = 219 + max(0, (270 - block_height) // 2)
    for line in lines:
        _text(draw, (98, y), line, quote_font, "#27194f")
        y += line_height

    # Small signature on the card; avoid a large footer that wastes mobile space.
    _text(draw, (52, 575), "✦  VANYA QUOTE", _font(21, True), "#e1c6ff")
    _text(draw, (560, 575), "BETTER VIBES", _font(19, True), "#83edff")

    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    output.name = "vanya_quote.png"
    return output


async def quote_cmd(update, context):
    """Reply with /q to turn the replied-to message into a mobile-friendly quote card."""
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
