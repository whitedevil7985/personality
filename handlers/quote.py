"""Generate a polished image card when /q is used as a reply."""
import io
import textwrap
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys


W, H = 1200, 760


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
            continue
    return ImageFont.load_default()


def _draw_text(draw, xy, text, font, fill, **kwargs):
    try:
        draw.text(xy, text, font=font, fill=fill, **kwargs)
    except (UnicodeEncodeError, ValueError):
        safe = text.encode("ascii", "replace").decode("ascii")
        draw.text(xy, safe, font=font, fill=fill, **kwargs)


def _rounded_gradient(size, left, right, radius):
    w, h = size
    base = Image.new("RGB", size, left)
    d = ImageDraw.Draw(base)
    for x in range(w):
        t = x / max(1, w - 1)
        color = tuple(int(left[i] * (1 - t) + right[i] * t) for i in range(3))
        d.line((x, 0, x, h), fill=color)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    return base, mask


def _wrap_by_width(draw, text, font, max_width, max_lines=5):
    text = " ".join((text or "").split())
    if not text:
        return ["(empty message)"]
    words = textwrap.wrap(text, width=55, break_long_words=True, break_on_hyphens=True)
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        try:
            width = draw.textbbox((0, 0), candidate, font=font)[2]
        except Exception:
            width = len(candidate) * 20
        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + "…"
    return lines


def _make_quote_card(name, handle, quoted_text, time_label, avatar_bytes=None):
    # Deep navy background with cyan/purple atmosphere.
    img = Image.new("RGB", (W, H), "#090b1c")
    pix = img.load()
    for x in range(W):
        t = x / W
        color = (
            int(10 + 18 * t),
            int(8 + 8 * t),
            int(29 + 38 * t),
        )
        ImageDraw.Draw(img).line((x, 0, x, H), fill=color)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-150, 120, 430, 690), fill=(218, 45, 255, 100))
    gd.ellipse((740, -130, 1360, 470), fill=(0, 205, 255, 95))
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    draw = ImageDraw.Draw(img)

    # Outer neon border and glass-like panel.
    draw.rounded_rectangle((38, 36, 1162, 724), radius=42,
                           fill=(12, 15, 40, 235), outline=(135, 86, 255, 255), width=3)
    draw.rounded_rectangle((47, 45, 1153, 715), radius=36,
                           outline=(49, 210, 255, 210), width=2)

    # Tiny stars and sparkles.
    for x, y, r, c in [
        (105, 112, 6, "#ff86ed"), (1080, 116, 5, "#6bf4ff"),
        (1030, 600, 7, "#c49aff"), (115, 590, 4, "#6bf4ff"),
        (950, 245, 4, "#ff86ed"), (180, 655, 4, "#bba6ff"),
        (1010, 480, 5, "#79e8ff"), (520, 100, 3, "#ff91e8"),
    ]:
        draw.ellipse((x-r, y-r, x+r, y+r), fill=c)
    draw.line((1025, 170, 1025, 194), fill="#ff9deb", width=3)
    draw.line((1013, 182, 1037, 182), fill="#ff9deb", width=3)

    # Avatar: Telegram profile photo when available, otherwise a monogram.
    ax, ay, ar = 100, 92, 112
    avatar = None
    if avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
            avatar = ImageOps.fit(avatar, (ar, ar), method=Image.Resampling.LANCZOS)
        except Exception:
            avatar = None
    if avatar is None:
        avatar = Image.new("RGB", (ar, ar), "#32245f")
        ad = ImageDraw.Draw(avatar)
        initials = (name[:1] or "?").upper()
        _draw_text(ad, (36, 26), initials, _font(48, True), "#ffffff")
    mask = Image.new("L", (ar, ar), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, ar-1, ar-1), fill=255)
    draw.ellipse((ax-5, ay-5, ax+ar+5, ay+ar+5), outline="#77f4ff", width=5)
    img.paste(avatar, (ax, ay), mask)
    draw = ImageDraw.Draw(img)

    _draw_text(draw, (245, 95), name[:28], _font(43, True), "#e7a2ff")
    if handle:
        handle_line = "@" + handle.lstrip("@")
        _draw_text(draw, (248, 147), handle_line[:32], _font(20), "#a8b4ed")
    _draw_text(draw, (870, 104), "QUOTED MESSAGE", _font(18, True), "#8eefff")
    draw.rounded_rectangle((965, 137, 1112, 182), radius=22,
                           fill=(35, 61, 126, 245), outline=(92, 214, 255, 220), width=2)
    _draw_text(draw, (989, 147), time_label, _font(22, True), "#ffffff")

    # Main quote gradient block.
    grad, mask = _rounded_gradient((970, 360), (201, 80, 238), (27, 174, 230), 32)
    grad_rgba = grad.convert("RGBA")
    overlay = Image.new("RGBA", grad_rgba.size, (18, 12, 55, 74))
    grad_rgba = Image.alpha_composite(grad_rgba, overlay)
    img.paste(grad_rgba, (115, 230), mask)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((115, 230, 1085, 590), radius=32,
                           outline=(241, 211, 255, 230), width=3)
    # Translucent-style inset quotation marker.
    draw.rounded_rectangle((148, 267, 158, 335), radius=5, fill="#ffffff")
    _draw_text(draw, (184, 263), "ORIGINAL MESSAGE", _font(18, True), "#f5eaff")

    quote_font = _font(35, True)
    lines = _wrap_by_width(draw, quoted_text, quote_font, 820, max_lines=5)
    y = 320
    for line in lines:
        _draw_text(draw, (184, y), line, quote_font, "#ffffff", stroke_width=1, stroke_fill=(38, 24, 96))
        y += 57

    # Footer / branding.
    draw.line((75, 625, 1125, 625), fill=(111, 103, 214, 190), width=2)
    _draw_text(draw, (90, 652), "✦  VANYA QUOTE CARD", _font(22, True), "#d8b8ff")
    _draw_text(draw, (770, 654), "REAL WORDS  •  BETTER VIBES", _font(17, True), "#83edff")
    for cx, cy in [(1064, 657), (1090, 674)]:
        draw.ellipse((cx-7, cy-7, cx+7, cy+7), outline="#ff8be9", width=3)

    output = io.BytesIO()
    img.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    output.name = "vanya_quote.png"
    return output


async def quote_cmd(update, context):
    """Reply with /q to turn the replied-to message into a neon quote card."""
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
