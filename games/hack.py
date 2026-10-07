import asyncio
import html
import os
import random
import re
import time
from pathlib import Path

from telegram import InputFile

from db import ensure_user, add_coins, record_game_result

REWARD = 30
GAME_TIMEOUT = 90
HACK_GAMES = {}


def _new_puzzle():
    """Return a solvable, fictional cybersecurity-lab challenge."""
    challenges = [
        ("SEQUENCE",
         "2, 4, 8, 16, ?",
         ("32",),
         "Find the next value in the sequence."),
        ("SEQUENCE",
         "3, 6, 12, 24, ?",
         ("48",),
         "Find the next value in the sequence."),
        ("SEQUENCE",
         "1, 4, 9, 16, ?",
         ("25",),
         "Find the next value in the sequence."),
        ("SEQUENCE",
         "5, 10, 20, 40, ?",
         ("80",),
         "Find the next value in the sequence."),
        ("CODE",
         "7-2-9-4",
         ("6",),
         "Take the largest digit and subtract the smallest digit."),
        ("CODE",
         "8-3-5-1",
         ("7",),
         "Take the largest digit and subtract the smallest digit."),
    ]
    return random.choice(challenges)


def _terminal_text(stage, target, ports, challenge=None, extra=""):
    lines = [
        "╭━━━〔 💻 <b>VANYA CYBER LAB</b> 〕━━━╮",
        f"┃ 🎯 Target: <code>{html.escape(target)}</code>",
        f"┃ 🔌 Ports: <code>{html.escape(ports)}</code>",
        f"┃ 🟢 Status: <b>{html.escape(stage)}</b>",
        "╰━━━━━━━━━━━━━━━━━━━━━━━━╯",
        "",
        "▣ SIMULATED SECURITY TEST",
        "",
    ]
    if challenge:
        lines.extend([
            f"🧩 <b>Challenge:</b> {html.escape(challenge[0])}",
            f"🔐 Code: <code>{html.escape(challenge[1])}</code>",
            "",
            f"💡 {html.escape(challenge[3])}",
            "",
            "⌨️ Type the numeric answer to continue.",
        ])
    else:
        lines.extend([
            "▸ Initializing secure test environment…",
            "▸ Enumerating simulated services…",
            f"▸ {html.escape(extra)}",
        ])
    return "\n".join(lines)


async def _animate_start(message, target, ports):
    frames = [
        _terminal_text("CONNECTING", target, ports, extra="Establishing encrypted lab channel…"),
        _terminal_text("SCANNING", target, ports, extra="Checking simulated service fingerprints…"),
        _terminal_text("BREACH GATE", target, ports, extra="Challenge gate locked. Authentication required."),
    ]

    for index, frame in enumerate(frames):
        try:
            if index == 0:
                await message.edit_text(frame, parse_mode="HTML")
            else:
                await asyncio.sleep(0.55)
                await message.edit_text(frame, parse_mode="HTML")
        except Exception as exc:
            print(f"[HACK] animation error: {type(exc).__name__}: {exc}")


async def _send_hack_image(update, context):
    """Send the Hack Lab image reliably from the bundle, with a public fallback."""
    caption = "💻 <b>VANYA CYBER LAB</b> — simulated security challenge"

    candidates = [
        Path(__file__).resolve().parent.parent / "assets" / "hack_terminal.jpg",
        Path.cwd() / "assets" / "hack_terminal.jpg",
    ]

    last_error = None
    for image_path in candidates:
        if not image_path.is_file():
            continue
        try:
            with image_path.open("rb") as image_handle:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=InputFile(image_handle, filename="hack_terminal.jpg"),
                    caption=caption,
                    parse_mode="HTML",
                )
            return True
        except Exception as exc:
            last_error = exc
            print(f"[HACK] local image send error ({image_path}): {type(exc).__name__}: {exc}")

    # Fallback keeps the image working even if the runtime image path is wrong.
    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo="https://raw.githubusercontent.com/whitedevil7985/personality/main/assets/hack_terminal.jpg",
            caption=caption,
            parse_mode="HTML",
        )
        return True
    except Exception as exc:
        print(f"[HACK] remote image send error: {type(exc).__name__}: {exc}")
        if last_error:
            print(f"[HACK] previous local error: {type(last_error).__name__}: {last_error}")
        return False


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

    challenge = _new_puzzle()
    target = f"192.0.2.{random.randint(10, 240)}"
    ports = ",".join(str(p) for p in random.sample([22, 80, 443, 8080], 3))

    HACK_GAMES[chat_id] = {
        "challenge": challenge,
        "answers": tuple(str(x).casefold() for x in challenge[2]),
        "started_at": time.monotonic(),
        "target": target,
        "ports": ports,
        "ready": False,
    }

    await _send_hack_image(update, context)

    sent = await update.message.reply_html(
        _terminal_text("BOOTING", target, ports, extra="Preparing simulated security lab…")
    )
    await _animate_start(sent, target, ports)

    game = HACK_GAMES.get(chat_id)
    if not game:
        return

    game["ready"] = True
    try:
        await sent.edit_text(
            _terminal_text(
                "AWAITING INPUT",
                target,
                ports,
                challenge=challenge,
            ),
            parse_mode="HTML",
        )
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
    await update.message.reply_html(
        "╭━━━〔 ✅ <b>ACCESS GRANTED</b> 〕━━━╮\n"
        f"┃ 🎯 Target: <code>{target}</code>\n"
        "┃ 🔓 Security gate: <b>BYPASSED</b>\n"
        "┃ 🟢 Session: <b>COMPLETE</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👑 <b>{html.escape(user.first_name or 'Player')}</b> cracked the lab!\n"
        f"💰 Reward: <b>+{REWARD} coins</b>\n"
        "🛡️ This was a fictional simulated security challenge.\n"
        "✨ Start another with /hack"
    )
    return True
