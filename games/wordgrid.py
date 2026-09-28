import random
from io import BytesIO
from typing import Dict, List, Set, Tuple

from PIL import Image, ImageDraw, ImageFont
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import OWNER_ID, SUDO_IDS
from db import get_user

GRID_SIZE = 8
WORDS = [
    ("ANT", 3),
    ("LID", 3),
    ("OAK", 3),
    ("RAY", 3),
    ("MINT", 4),
    ("GREEN", 5),
    ("PURPLE", 6),
]
DIRECTIONS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc]


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # Railway/slim images may not ship system TTF fonts. Pillow 10+
    # supports a scalable built-in fallback; keep the letters readable.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _place_word(grid: List[List[str]], word: str):
    options = []
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            for dr, dc in DIRECTIONS:
                end_r = row + dr * (len(word) - 1)
                end_c = col + dc * (len(word) - 1)
                if not (0 <= end_r < GRID_SIZE and 0 <= end_c < GRID_SIZE):
                    continue
                if all(
                    not grid[row + dr * i][col + dc * i]
                    or grid[row + dr * i][col + dc * i] == ch
                    for i, ch in enumerate(word)
                ):
                    options.append((row, col, dr, dc))
    if not options:
        return None

    row, col, dr, dc = random.choice(options)
    positions = []
    for i, ch in enumerate(word):
        rr = row + dr * i
        cc = col + dc * i
        grid[rr][cc] = ch
        positions.append((rr, cc))
    return positions


def _build_grid():
    words = [w for w, _ in WORDS]
    for _ in range(100):
        grid = [["" for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        random.shuffle(words)
        placements = {}
        ok = True
        for word in words:
            positions = _place_word(grid, word)
            if positions is None:
                ok = False
                break
            placements[word] = positions

        if ok:
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    if not grid[r][c]:
                        grid[r][c] = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            return grid, words[:], placements

    # Very safe fallback: place words on rows, then fill blanks.
    grid = [["" for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    placements = {}
    for r, word in enumerate(words[:GRID_SIZE]):
        positions = []
        for c, ch in enumerate(word[:GRID_SIZE]):
            grid[r][c] = ch
            positions.append((r, c))
        placements[word] = positions

    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if not grid[r][c]:
                grid[r][c] = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return grid, words[:], placements


def _render_grid(grid: List[List[str]], highlighted: Set[Tuple[int, int]] = None) -> BytesIO:
    # Screenshot-inspired lavender Word Grid design.
    W, H = 900, 1030
    bg = (224, 207, 241)
    card = (231, 218, 246)
    stroke = (177, 145, 213)
    inner = (238, 226, 250)
    inner_stroke = (211, 191, 231)
    letter = (59, 43, 91)
    highlight = (204, 239, 212)
    highlight_stroke = (58, 145, 86)

    highlighted = highlighted or set()

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    margin_x = 34
    top = 22
    board_w = W - margin_x * 2
    board_h = 756
    gap = 7
    cell = (board_w - gap * (GRID_SIZE - 1)) / GRID_SIZE

    d.rounded_rectangle(
        (margin_x - 8, top - 8, W - margin_x + 8, top + board_h + 8),
        radius=22,
        fill=card,
        outline=stroke,
        width=5,
    )

    font = _font(84, bold=True)
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            x0 = margin_x + c * (cell + gap)
            y0 = top + r * (cell / 1.0 + 3)  # evenly packed within the board
            # Normalize rows to the exact board height for a clean 8x8 grid.
            y0 = top + r * ((board_h - gap * (GRID_SIZE - 1)) / GRID_SIZE + gap)
            cell_h = (board_h - gap * (GRID_SIZE - 1)) / GRID_SIZE
            x1 = x0 + cell
            y1 = y0 + cell_h
            is_found = (r, c) in highlighted
            d.rounded_rectangle(
                (x0, y0, x1, y1),
                radius=10,
                fill=highlight if is_found else inner,
                outline=highlight_stroke if is_found else inner_stroke,
                width=4 if is_found else 2,
            )
            text = grid[r][c]
            bbox = d.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            d.text(
                (x0 + (cell - tw) / 2, y0 + (cell_h - th) / 2 - 2),
                text,
                font=font,
                fill=letter,
            )

    title_font = _font(31, bold=True)
    title = "▣ WORD GRID CHALLENGE"
    bbox = d.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) / 2, 865), title, font=title_font, fill=letter)

    bio = BytesIO()
    bio.name = "wordgrid.png"
    img.save(bio, format="PNG", optimize=True)
    bio.seek(0)
    return bio


def _found_positions(active) -> Set[Tuple[int, int]]:
    positions = set()
    placements = active.get("placements", {})
    for word in active.get("found", set()):
        positions.update(placements.get(word, []))
    return positions


def _wordgrid_caption(active, game_over: bool = False) -> str:
    found = active.get("found", set())
    words_list = active.get("words_list", [])
    total = len(words_list)
    points = active.get("points", {})

    lines = [
        "🎮 <b>Word grid challenge</b> 🎮",
        "",
        "find these words:",
    ]
    for word, length in WORDS:
        if word.lower() in found:
            lines.append(f"✅ <code>{word}</code> ({length})")
        else:
            lines.append(f"<code>{word[0]}</code> " + "_ " * (length - 1) + f"({length})")

    my_id = active.get("last_finder")
    my_points = int(points.get(my_id, 0)) if my_id else 0
    lines.extend([
        "",
        f"🔎 <b>Found:</b> {len(found)}/{total}",
        f"⭐ <b>Your points:</b> {my_points}",
    ])

    if game_over:
        leaderboard = sorted(points.items(), key=lambda item: item[1], reverse=True)
        lines.extend(["", "🏁 <b>GAME OVER</b>"])
        if leaderboard:
            lines.append("<b>Final points:</b>")
            for index, (uid, score) in enumerate(leaderboard[:5], 1):
                lines.append(f"{index}. <a href=\"tg://user?id={uid}\">Player {uid}</a> — <b>{score} pts</b>")
        lines.append("")
        lines.append("✅ All hidden words have been found!")

    lines.extend([
        "",
        "💡 <b>How to play:</b> Find the hidden words and send <code>/answer WORD</code>.",
        "✨ Words can be horizontal, vertical, or diagonal.",
    ])
    return "\n".join(lines)


async def _refresh_wordgrid_message(context, chat_id: int, active, game_over: bool = False):
    message_id = active.get("message_id")
    if not message_id:
        return

    from telegram import InputMediaPhoto

    await context.bot.edit_message_media(
        chat_id=chat_id,
        message_id=message_id,
        media=InputMediaPhoto(
            media=_render_grid(active["grid"], _found_positions(active)),
            caption=_wordgrid_caption(active, game_over=game_over),
            parse_mode="HTML",
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 New Grid", callback_data="wordgrid:new")],
        ]) if not game_over else None,
    )


async def send_wordgrid(message, context, user_id=None):
    grid, words, placements = _build_grid()
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    if chat_id is None:
        return
    active = context.application.bot_data.setdefault("wordgrid_active", {})
    active[chat_id] = {
        "words": {w.lower() for w in words},
        "found": set(),
        "created_by": user_id,
        "grid": grid,
        "words_list": words[:],
        "placements": {word.lower(): positions for word, positions in placements.items()},
        "points": {},
        "message_id": None,
        "last_finder": None,
    }

    sent = await message.reply_photo(
        photo=_render_grid(grid),
        caption=_wordgrid_caption(active),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 New Grid", callback_data="wordgrid:new")],
        ]),
    )
    active["message_id"] = sent.message_id


async def reveal_wordgrid(update, context):
    """Reveal the current Wordgrid answer to the Owner only.

    In groups, the answer is sent to the requesting admin's DM so regular
    group members never see the solution.
    """
    if not update.effective_user:
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return
    uid = update.effective_user.id
    if uid != OWNER_ID and uid not in SUDO_IDS:
        user = await get_user(uid)
        if not user or not user.get("is_sudo"):
            await update.message.reply_text("⛔ Owner/Sudo only.")
            return

    chat_id = update.effective_chat.id if update.effective_chat else None
    active = context.application.bot_data.get("wordgrid_active", {}).get(chat_id)
    if not active:
        await update.message.reply_text("❌ No active Wordgrid game in this chat.")
        return

    words = [w.upper() for w in active.get("words_list", sorted(active.get("words", [])))]
    answer_text = (
        "🔐 <b>Wordgrid Answer</b>\n\n"
        + " • ".join(words)
        + "\n\n🔒 This answer is visible only to the Owner/Sudo staff member who requested it."
    )

    if update.effective_chat.type in ("group", "supergroup"):
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=f"📩 <b>Answer for {getattr(update.effective_chat, 'title', 'this group')}</b>\n\n🔐 " + " • ".join(words),
                parse_mode="HTML",
            )
            await update.message.reply_text("✅ Answer sent to your private chat.")
            return
        except Exception:
            await update.message.reply_text("⚠️ I couldn't DM you. Open a private chat with Vanya first, then use /revealgrid.")
            return

    await update.message.reply_html(answer_text)


async def wordgrid(update, context):
    await send_wordgrid(update.message, context, getattr(update.effective_user, "id", None))


async def wordgrid_answer(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /answer <word>")
        return
    chat_id = update.effective_chat.id
    active = context.application.bot_data.get("wordgrid_active", {}).get(chat_id)
    if not active:
        await update.message.reply_text("No active Wordgrid game here. Start one with /wordgrid")
        return

    guess = "".join(context.args).strip().lower()
    if guess not in active["words"]:
        await update.message.reply_text("❌ That word isn't in this grid. Try again!")
        return
    if guess in active["found"]:
        await update.message.reply_text("👀 You already found that word!")
        return

    active["found"].add(guess)
    user_id = update.effective_user.id
    word_points = len(guess) * 10
    points = active.setdefault("points", {})
    points[user_id] = int(points.get(user_id, 0)) + word_points
    active["last_finder"] = user_id

    from db import add_coins, add_xp
    await add_coins(user_id, 40)
    await add_xp(user_id, 20)

    remaining = len(active["words"] - active["found"])
    if remaining == 0:
        completion_bonus = 50
        points[user_id] += completion_bonus
        await add_coins(user_id, 100)
        await add_xp(user_id, 50)
        await _refresh_wordgrid_message(
            context,
            chat_id,
            active,
            game_over=True,
        )
        total_points = points[user_id]
        await update.message.reply_text(
            f"🏆 <b>Wordgrid GAME OVER!</b>\n\n"
            f"✅ <b>{guess.upper()}</b> found!\n"
            f"⭐ Word points: +{word_points}\n"
            f"🎁 Completion bonus: +{completion_bonus}\n"
            f"💎 <b>Your total: {total_points} points</b>\n\n"
            f"🪙 Bonus rewards: +100 coins +50 XP",
            parse_mode="HTML",
        )
    else:
        await _refresh_wordgrid_message(context, chat_id, active)
        await update.message.reply_text(
            f"✅ <b>{guess.upper()}</b> found!\n"
            f"⭐ +{word_points} points | +40 coins | +20 XP\n"
            f"🔎 {remaining} word(s) left.",
            parse_mode="HTML",
        )
