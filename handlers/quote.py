"""Generate a readable neon quote card when /q is used as a reply."""
import io
import textwrap
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys


# A near-square card is shown much larger in Telegram's chat preview than a
# wide banner. Text sizes are intentionally large for mobile readability.
W, H = 1000, 1120


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
    # Important: default Pillow bitmap font is tiny if no size is passed.
    # Pillow 10+ includes a scalable bundled font; use it as a safe fallback.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_text(draw, xy, text, font, fill, **kwargs):
    try:
        draw.text(xy, text, font=font, fill=fill, **kwargs)
    except (UnicodeEncodeError, ValueError):
        # Some minimal containers lack emoji glyphs. Preserve readable text
        # rather than letting one unsupported character break card creation.
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
    words = textwrap.wrap(text, width=70, break_long_words=True, break_on_hyphens=True)
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        try:
            width = draw.textbbox((0, 0), candidate, font=font)[2]
        except Exception:
            width = len(candidate) * 32
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
    # Dark navy backdrop, with a soft purple-to-cyan glow.
    img = Image.new("RGB", (W, H), "#090b1c")
    bgdraw = ImageDraw.Draw(img)
    for x in range(W):
        t = x / max(1, W - 1)
        color = (int(11 + 14*t), int(8 + 10*t), int(28 + 37*t))
        bgdraw.line((x, 0, x, H), fill=color)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-170, 130, 410, 690), fill=(218, 45, 255, 100))
    gd.ellipse((650, 20, 1170, 700), fill=(0, 205, 255, 85))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img.convert("RGBA"), glow)

    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((27, 27, 973, 1093), radius=42,
                           fill=(12, 15, 40, 245), outline=(169, 86, 255, 255), width=4)
    draw.rounded_rectangle((38, 38, 962, 1082), radius=34,
                           outline=(49, 210, 255, 210), width=2)

    # Restrained sparkles keep the quote text as the visual focus.
    for x, y, r, c in [
        (86, 250, 6, "#ff86ed"), (908, 250, 6, "#6bf4ff"),
        (905, 865, 7, "#c49aff"), (92, 875, 5, "#6bf4ff"),
        (500, 78, 4, "#ff91e8"), (825, 1012, 5, "#79e8ff"),
    ]:
        draw.ellipse((x-r, y-r, x+r, y+r), fill=c)
    draw.line((880, 280, 880, 310), fill="#ff9deb", width=4)
    draw.line((865, 295, 895, 295), fill="#ff9deb", width=4)

    # Sender avatar, with a monogram fallback if Telegram has no public photo.
    ax, ay, ar = 78, 78, 150
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
        f = _font(66, True)
        box = ad.textbbox((0, 0), initials, font=f)
        _draw_text(ad, ((ar-(box[2]-box[0]))//2, (ar-(box[3]-box[1]))//2-8),
                   initials, f, "#ffffff")
    avatar_mask = Image.new("L", (ar, ar), 0)
    ImageDraw.Draw(avatar_mask).ellipse((0, 0, ar-1, ar-1), fill=255)
    draw.ellipse((ax-6, ay-6, ax+ar+6, ay+ar+6), outline="#77f4ff", width=6)
    img.paste(avatar, (ax, ay), avatar_mask)
    draw = ImageDraw.Draw(img)

    _draw_text(draw, (260, 91), name[:25], _font(50, True), "#e7a2ff")
    if handle:
        _draw_text(draw, (263, 157), "@" + handle.lstrip("@")[:28],
                   _font(27), "#a8c5ff")
    _draw_text(draw, (265, 208), "QUOTED MESSAGE", _font(22, True), "#8eefff")

    # High-contrast time pill.
    draw.rounded_rectangle((752, 103, 918, 161), radius=28,
                           fill=(35, 61, 126, 245), outline=(92, 214, 255, 230), width=2)
    _draw_text(draw, (778, 116), time_label, _font(29, True), "#ffffff")

    # Large, legible quote panel.
    grad, mask = _rounded_gradient((860, 535), (195, 65, 230), (23, 160, 225), 38)
    grad_rgba = grad.convert("RGBA")
    overlay = Image.new("RGBA", grad_rgba.size, (12, 11, 42, 58))
    grad_rgba = Image.alpha_composite(grad_rgba, overlay)
    img.paste(grad_rgba, (70, 300), mask)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((70, 300, 930, 835), radius=38,
                           outline=(245, 220, 255, 245), width=4)

    draw.rounded_rectangle((104, 345, 116, 420), radius=6, fill="#ffffff")
    _draw_text(draw, (142, 350), "THE ORIGINAL MESSAGE", _font(24, True), "#fff2ff")

    quote_font = _font(64, True)
    lines = _wrap_by_width(draw, quoted_text, quote_font, 730, max_lines=5)
    # Vertically center the quote lines, while leaving the title above.
    line_height = 80
    max_quote_height = line_height * len(lines)
    y = 425 + max(0, (345 - max_quote_height) // 2)
    for line in lines:
        _draw_text(draw, (142, y), line, quote_font, "#ffffff",
                   stroke_width=1, stroke_fill=(38, 24, 96))
        y += line_height

    # Branding/footer.
    draw.line((75, 895, 925, 895), fill=(111, 103, 214, 210), width=2)
    _draw_text(draw, (84, 938), "✦  VANYA QUOTE CARD", _font(29, True), "#e1c6ff")
    _draw_text(draw, (84, 988), "REAL WORDS  •  BETTER VIBES", _font(22, True), "#83edff")
    draw.ellipse((861, 952, 892, 983), outline="#ff8be9", width=4)
    draw.ellipse((888, 972, 911, 995), outline="#9b8cff", width=4)

    output = io.BytesIO()
    img.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    output.name = "vanya_quote.png"
    return output


async def quote_cmd(update, context):
    """Reply with /q to turn the replied-to message into a readable quote card."""
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
