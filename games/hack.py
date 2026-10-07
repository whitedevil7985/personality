import asyncio
import html
import base64
import random
import re
import time
from pathlib import Path
from datetime import datetime, timezone

from telegram import InputFile
from PIL import Image, ImageOps

from db import ensure_user, add_coins, record_game_result, games

REWARD = 30
GAME_TIMEOUT = 90
HACK_GAMES = {}


HACK_CHALLENGES = [
    ("SEQUENCE", "2, 4, 8, 16, ?", ("32",), "Find the next value in the sequence."),
    ("SEQUENCE", "3, 6, 12, 24, ?", ("48",), "Find the next value in the sequence."),
    ("SEQUENCE", "1, 4, 9, 16, ?", ("25",), "Find the next value in the sequence."),
    ("SEQUENCE", "5, 10, 20, 40, ?", ("80",), "Find the next value in the sequence."),
    ("CODE", "7-2-9-4", ("6",), "Take the largest digit and subtract the smallest digit."),
    ("CODE", "8-3-5-1", ("7",), "Take the largest digit and subtract the smallest digit."),
    ("SEQUENCE", "2, 6, 18, 54, ?", ("162",), "Multiply each value by 3."),
    ("SEQUENCE", "100, 90, 80, 70, ?", ("60",), "Subtract 10 each time."),
    ("SEQUENCE", "1, 8, 27, 64, ?", ("125",), "Find the next cube."),
    ("SEQUENCE", "2, 3, 5, 7, ?", ("11",), "Find the next prime number."),
    ("CODE", "9-1-4-6", ("8",), "Take the largest digit and subtract the smallest digit."),
    ("CODE", "6-2-8-3", ("6",), "Take the largest digit and subtract the smallest digit."),
    ("SEQUENCE", "4, 8, 12, 16, ?", ("20",), "Add 4 each time."),
    ("SEQUENCE", "81, 27, 9, 3, ?", ("1",), "Divide by 3 each time."),
    ("SEQUENCE", "7, 14, 28, 56, ?", ("112",), "Double each value."),
];

async def _next_unique_puzzle():
    """Atomically claim a never-used Hack challenge from MongoDB."""
    state_id = "hack_puzzle_pool"
    state = await games.find_one({"_id": state_id}) or {}
    used = {str(x) for x in state.get("used_codes", [])}

    available = [
        (index, challenge)
        for index, challenge in enumerate(HACK_CHALLENGES)
        if str(index) not in used
    ]
    if not available:
        return None

    # A conditional update makes the claim atomic even if two groups start
    # /hack at nearly the same time.
    random.shuffle(available)
    for index, challenge in available:
        result = await games.update_one(
            {"_id": state_id, "used_codes": {"$ne": str(index)}},
            {
                "$addToSet": {"used_codes": str(index)},
                "$set": {
                    "total_challenges": len(HACK_CHALLENGES),
                    "updated_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )
        if result.modified_count == 1 or result.upserted_id:
            return challenge

    return None


def _terminal_text(stage, target, ports, challenge=None, extra=""):
    lines = [
        "💻 <b>VANYA CYBER LAB</b>",
        f"🎯 Target: <code>{html.escape(target)}</code>  •  🔌 <code>{html.escape(ports)}</code>",
        f"🟢 Status: <b>{html.escape(stage)}</b>",
        "",
    ]
    if challenge:
        lines.extend([
            f"🧩 <b>{html.escape(challenge[0])}</b>",
            f"🔐 <code>{html.escape(challenge[1])}</code>",
            f"💡 {html.escape(challenge[3])}",
            "⌨️ <b>Reply with the numeric answer.</b>",
        ])
    else:
        lines.append(f"▸ {html.escape(extra)}")
    return "\n".join(lines)


async def _animate_start(message, target, ports):
    frames = [
        _terminal_text("CONNECTING", target, ports, extra="Establishing encrypted lab channel…"),
        _terminal_text("SCANNING", target, ports, extra="Checking simulated service fingerprints…"),
        _terminal_text("BREACH GATE", target, ports, extra="Challenge gate locked. Authentication required."),
    ]
    for index, frame in enumerate(frames):
        try:
            if index > 0:
                await asyncio.sleep(0.55)
            await message.edit_caption(caption=frame, parse_mode="HTML")
        except Exception as exc:
            print(f"[HACK] caption animation error: {type(exc).__name__}: {exc}")


async def _animate_text_fallback(message, target, ports):
    frames = [
        _terminal_text("CONNECTING", target, ports, extra="Establishing encrypted lab channel…"),
        _terminal_text("SCANNING", target, ports, extra="Checking simulated service fingerprints…"),
        _terminal_text("BREACH GATE", target, ports, extra="Challenge gate locked. Authentication required."),
    ]
    for index, frame in enumerate(frames):
        try:
            if index > 0:
                await asyncio.sleep(0.55)
            await message.edit_text(frame, parse_mode="HTML")
        except Exception as exc:
            print(f"[HACK] text animation error: {type(exc).__name__}: {exc}")


async def _send_hack_image(update, context, initial_caption):
    """Send the sharp Hack Lab artwork once; the caption is the live game UI."""
    data_path = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "hack_terminal_b64.txt"
    )
    try:
        encoded = data_path.read_text(encoding="ascii").strip()
        image_bytes = base64.b64decode(encoded, validate=True)
        with Image.open(__import__("io").BytesIO(image_bytes)) as source:
            source = source.convert("RGB")
            temp_path = Path("/tmp/vanya_hack_terminal.jpg")
            source.save(temp_path, "JPEG", quality=95, optimize=True, progressive=True)
        with temp_path.open("rb") as image_handle:
            return await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=InputFile(image_handle, filename="hack_terminal.jpg"),
                caption=initial_caption,
                parse_mode="HTML",
            )
    except Exception as exc:
        print(f"[HACK] bundled image send error: {type(exc).__name__}: {exc}")
        return None


async def hack(update, context):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat_id = update.effective_chat.id
    current = HACK_GAMES.get(chat_id)
    if current and time.monotonic() - current["started_at"] < GAME_TIMEOUT:
        await update.message.reply_text(
            "💻 <b>Cyber Lab already running!</b> Solve the current access gate first.",
            parse_mode="HTML",
        )
        return

    if current:
        HACK_GAMES.pop(chat_id, None)

    challenge = await _next_unique_puzzle()
    if challenge is None:
        await update.message.reply_text(
            "🧩 <b>Hack challenge pool finished!</b> No puzzle will be repeated. Ask the owner to add more challenges.",
            parse_mode="HTML",
        )
        return

    target = f"192.0.2.{random.randint(10, 240)}"
    ports = ",".join(str(p) for p in random.sample([22, 80, 443, 8080], 3))
    boot = _terminal_text("BOOTING", target, ports, extra="Preparing simulated security lab…")

    game = {
        "challenge": challenge,
        "answers": tuple(str(x).casefold() for x in challenge[2]),
        "started_at": time.monotonic(),
        "target": target,
        "ports": ports,
        "ready": False,
        "message_id": None,
    }
    HACK_GAMES[chat_id] = game

    sent = await _send_hack_image(update, context, boot)
    if sent is None:
        sent = await update.message.reply_html(boot)
        await _animate_text_fallback(sent, target, ports)
    else:
        await _animate_start(sent, target, ports)

    current = HACK_GAMES.get(chat_id)
    if not current:
        return

    current["ready"] = True
    final_text = _terminal_text("AWAITING INPUT", target, ports, challenge=challenge)
    try:
        if getattr(sent, "photo", None):
            await sent.edit_caption(caption=final_text, parse_mode="HTML")
        else:
            await sent.edit_text(final_text, parse_mode="HTML")
        current["message_id"] = sent.message_id
    except Exception as exc:
        print(f"[HACK] final-prompt error: {type(exc).__name__}: {exc}")


async def hack_answer(update, context):
    if not update.message or not update.message.text or not update.effective_chat:
        return False

    chat_id = update.effective_chat.id
    game = HACK_GAMES.get(chat_id)
    if not game:
        return False

    if time.monotonic() - game["started_at"] >= GAME_TIMEOUT:
        HACK_GAMES.pop(chat_id, None)
        await update.message.reply_text(
            "⏰ <b>Cyber Lab session expired!</b> Start again with /hack.",
            parse_mode="HTML",
        )
        return True

    guess = update.message.text.strip().casefold()

    if not game.get("ready", False):
        return False

    # Ignore ordinary conversation while the hack puzzle is active.
    # Answers are intentionally numeric, so random chat words never trigger
    # an "Access denied" message.
    if not re.fullmatch(r"\d{1,6}", guess):
        return False

    answers = {str(x).casefold() for x in game.get("answers", ())}
    if guess not in answers:
        await update.message.reply_text(
            "🔒 <b>AUTH FAILED</b> — wrong code. Try again.",
            parse_mode="HTML",
        )
        return True

    HACK_GAMES.pop(chat_id, None)
    user = update.effective_user
    await ensure_user(user)
    await add_coins(user.id, REWARD)
    await record_game_result(user.id, "HACK", REWARD, True, chat_id)

    target = html.escape(str(game.get("target", "SIM-LAB")))
    result_text = (
        "✅ <b>ACCESS GRANTED</b>\n"
        f"🎯 Target: <code>{target}</code>\n"
        "🔓 Security gate: <b>BYPASSED</b>\n"
        "🟢 Session: <b>COMPLETE</b>\n\n"
        f"👑 <b>{html.escape(user.first_name or 'Player')}</b> cracked the lab!\n"
        f"💰 Reward: <b>+{REWARD} coins</b>\n"
        "🛡️ Fictional simulated security challenge.\n"
        "✨ Start another with /hack"
    )
    try:
        message_id = game.get("message_id")
        if message_id:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=result_text,
                parse_mode="HTML",
            )
            await update.message.reply_text("✅ Access granted! Reward added.")
        else:
            await update.message.reply_html(result_text)
    except Exception as exc:
        print(f"[HACK] success edit error: {type(exc).__name__}: {exc}")
        await update.message.reply_html(result_text)
    return True
