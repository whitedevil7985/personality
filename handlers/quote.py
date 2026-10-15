"""Create a mobile-first, attractive quote card for /q replies."""
import glob
import io
import os
import unicodedata
from datetime import datetime
from functools import lru_cache

from fontTools.ttLib import TTFont

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys


# Near-square image: Telegram can show it larger on phones than a very wide banner.
W, H = 900, 800


def _font(size, bold=False):
    candidates = (
        ["/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
         "DejaVuSans-Bold.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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


def _normalise_display_name(value):
    """Clean whitespace only; preserve the sender's exact Unicode name."""
    value = str(value or "Unknown").replace(chr(13), " ").replace(chr(10), " ")
    value = " ".join(value.split()).strip()
    return value or "Unknown"


@lru_cache(maxsize=1)
def _name_font_paths():
    """List ordinary fonts first, then fonts with broad symbol/math coverage."""
    base = [
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
    ]
    extra = []
    for pattern in (
        "/usr/share/fonts/truetype/noto/*Math*.ttf",
        "/usr/share/fonts/truetype/noto/*Symbols*.ttf",
        "/usr/share/fonts/truetype/noto/*Sans*.ttf",
        "/usr/share/fonts/truetype/noto/*Serif*.ttf",
        "/usr/share/fonts/truetype/noto/*Mono*.ttf",
        "/usr/share/fonts/opentype/noto/*.otf",
        "/usr/share/fonts/opentype/stix/*.otf",
        "/usr/share/fonts/opentype/stix-word/*.otf",
    ):
        extra.extend(glob.glob(pattern))
    # Extra packs occasionally place uncommon alphabets in separate font files.
    paths = []
    for path in base + sorted(extra):
        if path not in paths and os.path.isfile(path):
            paths.append(path)
    return tuple(paths)


@lru_cache(maxsize=256)
def _font_cmap(path):
    """Return codepoints supported by a font, using its real Unicode cmap."""
    try:
        font = TTFont(path, lazy=True)
        points = set()
        for table in font["cmap"].tables:
            if table.isUnicode():
                points.update(table.cmap.keys())
        font.close()
        return frozenset(points)
    except Exception:
        return frozenset()


@lru_cache(maxsize=512)
def _load_name_font(path, size):
    try:
        return ImageFont.truetype(path, size=size)
    except (OSError, ValueError):
        return _font(size, False)


def _font_for_cluster(cluster):
    """Pick a font that actually contains this name character/character cluster."""
    paths = _name_font_paths()
    meaningful = [
        ord(ch) for ch in cluster
        if unicodedata.category(ch) not in {"Cf", "Cc", "Cs", "Mn", "Mc", "Me"}
        and ord(ch) not in (0xFE0E, 0xFE0F)
    ]
    if not meaningful:
        return paths[0] if paths else None

    best_path = paths[0] if paths else None
    best_count = -1
    for path in paths:
        cmap = _font_cmap(path)
        count = sum(codepoint in cmap for codepoint in meaningful)
        if count > best_count:
            best_count, best_path = count, path
        if count == len(meaningful):
            return path
    return best_path


def _name_clusters(value):
    """Keep combining marks and joined glyph sequences attached to their base."""
    clusters = []
    for ch in value:
        category = unicodedata.category(ch)
        if clusters and (
            unicodedata.combining(ch)
            or category in {"Mn", "Mc", "Me", "Cf"}
            or ord(ch) in (0xFE0E, 0xFE0F)
            or clusters[-1].endswith(chr(0x200D))
        ):
            clusters[-1] += ch
        else:
            clusters.append(ch)
    return clusters


def _name_runs(value, size):
    runs = []
    for cluster in _name_clusters(value):
        path = _font_for_cluster(cluster)
        if not path:
            path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if runs and runs[-1][0] == path:
            runs[-1][1] += cluster
        else:
            runs.append([path, cluster])
    measured = []
    width = 0
    for path, text in runs:
        font = _load_name_font(path, size)
        measured.append((text, font))
        try:
            width += font.getlength(text)
        except Exception:
            width += _measure(ImageDraw.Draw(Image.new("RGB", (1, 1))), text, font)
    return measured, width


def _draw_display_name(draw, value, x, y, max_width, base_size=38):
    """Render every original character with a glyph-capable font; never truncate."""
    value = _normalise_display_name(value)
    chosen_runs = None
    chosen_width = 0
    chosen_size = 16
    for size in range(base_size, 15, -2):
        runs, width = _name_runs(value, size)
        chosen_runs, chosen_width, chosen_size = runs, width, size
        if width <= max_width:
            break

    cursor = x
    for text, font in chosen_runs or []:
        _text(draw, (round(cursor), y), text, font, "#e7a3ff", stroke_width=0)
        try:
            cursor += font.getlength(text)
        except Exception:
            cursor += len(text) * chosen_size
    return chosen_width


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

    # Preserve the account's exact Unicode name and draw uncommon glyphs
    # using whichever installed font truly supports each character.
    _draw_display_name(draw, name, 177, 48, 525, base_size=38)
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
    # Do not NFKC-normalize the sender name: that changes stylized Unicode.
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
