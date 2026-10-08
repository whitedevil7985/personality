"""Daily random group-game event scheduler.

Posts one random existing bot game per active group each calendar day, including Ludo and Scribble Mini Apps.
"""

import asyncio
import html
import os
import random
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from types import SimpleNamespace

# Bridge into the initialized bot namespace, matching the project's modular
# handler pattern.
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

IST = timezone(timedelta(hours=5, minutes=30))
CHECK_INTERVAL = max(
    30,
    int(os.getenv("RANDOM_GAME_CHECK_INTERVAL_SECONDS", "60")),
)

# Existing bot games. Ludo and Scribble are included through their normal launch handlers.
RANDOM_GAME_HANDLERS = {
    "dice": dice,
    "slots": slots,
    "tap": tap,
    "mines": mines,
    "wordseek": wordseek,
    "wordgrid": wordgrid,
    "jumble": jumble,
    "wordscramble": wordscramble,
    "wordchain": wordchain,
    "rps": rps,
    "card": card,
    "crash": crash,
    "charades": charades,
    "hack": hack,
    "ludo": ludo,
    "scribble": scribble,
}

RANDOM_GAME_LABELS = {
    "dice": "🎲 Dice",
    "slots": "🎰 Slots",
    "tap": "⚡ Tap Challenge",
    "mines": "💎 Mines",
    "wordseek": "🔎 Wordseek",
    "wordgrid": "🔍 Wordgrid",
    "jumble": "🔤 Jumble",
    "wordscramble": "🧩 Wordscramble",
    "wordchain": "🔗 Wordchain",
    "rps": "🪨 RPS",
    "card": "🃏 Card Match",
    "crash": "🚀 Crash",
    "charades": "🎭 Charades",
    "hack": "💻 Hack",
    "ludo": "🎲 Ludo",
    "scribble": "🖌️ Scribble",
}

def _random_time_for_date(day):
    """Pick a natural-looking random IST time between 10:00 and 22:59."""
    return datetime(
        day.year,
        day.month,
        day.day,
        random.randint(10, 22),
        random.randint(0, 59),
        tzinfo=IST,
    ).astimezone(timezone.utc)

async def _ensure_next_time(group_id, now_utc):
    row = await groups.find_one({"_id": group_id}) or {}
    next_at = row.get("random_game_next_at")
    if next_at:
        return next_at

    now_local = now_utc.astimezone(IST)
    candidate = _random_time_for_date(now_local.date())
    if candidate <= now_utc + timedelta(minutes=2):
        candidate = _random_time_for_date(now_local.date() + timedelta(days=1))

    await groups.update_one(
        {"_id": group_id, "random_game_next_at": {"$exists": False}},
        {"$set": {
            "random_game_next_at": candidate,
            "random_game_last_date": None,
        }},
    )
    return candidate

async def start_daily_random_game(update, context, game_key):
    """Start one of the existing native games from the daily event button."""
    handler = RANDOM_GAME_HANDLERS.get(game_key)
    label = RANDOM_GAME_LABELS.get(game_key, "Game")
    q = getattr(update, "callback_query", None)
    if not q or not q.message or not q.from_user:
        return

    if handler is None:
        await q.answer("This game is unavailable right now.", show_alert=True)
        return

    try:
        await q.answer(f"Starting {label}…")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        proxy = SimpleNamespace(
            message=q.message,
            effective_message=q.message,
            effective_chat=q.message.chat,
            effective_user=q.from_user,
        )
        await handler(proxy, context)
    except Exception as exc:
        print(f"[RandomGame] start {game_key} failed: {type(exc).__name__}: {exc}")
        try:
            await q.answer(
                "⚠️ Game start failed. You can start it with its normal command.",
                show_alert=True,
            )
        except Exception:
            pass

async def random_game_callback(update, context):
    q = getattr(update, "callback_query", None)
    if not q or not q.data:
        return
    parts = q.data.split(":", 1)
    if len(parts) != 2 or parts[0] != "dailygame":
        return
    await start_daily_random_game(update, context, parts[1])

async def random_game_scheduler(bot):
    """Send one random existing game invitation per active group per day."""
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)
            now_utc = datetime.now(timezone.utc)
            today_key = now_utc.astimezone(IST).strftime("%Y-%m-%d")

            # Initialize a random daily slot for newly tracked groups.
            active_groups = groups.find({"active": {"$ne": False}})
            async for active_group in active_groups:
                group_id = active_group.get("_id")
                if group_id is not None and not active_group.get("random_game_next_at"):
                    await _ensure_next_time(group_id, now_utc)

            cursor = groups.find({
                "active": {"$ne": False},
                "random_game_next_at": {"$exists": True, "$lte": now_utc},
                "random_game_last_date": {"$ne": today_key},
            })

            async for group in cursor:
                group_id = group.get("_id")
                if group_id is None:
                    continue

                game_key = random.choice(tuple(RANDOM_GAME_HANDLERS))
                label = RANDOM_GAME_LABELS[game_key]

                # Claim this calendar day atomically before sending, preventing
                # duplicate daily posts if two scheduler ticks overlap.
                tomorrow = now_utc.astimezone(IST).date() + timedelta(days=1)
                next_at = _random_time_for_date(tomorrow)
                claimed = await groups.update_one(
                    {
                        "_id": group_id,
                        "active": {"$ne": False},
                        "random_game_next_at": {"$lte": now_utc},
                        "random_game_last_date": {"$ne": today_key},
                    },
                    {"$set": {
                        "random_game_last_date": today_key,
                        "random_game_next_at": next_at,
                        "random_game_name": game_key,
                    }},
                )
                if claimed.modified_count != 1:
                    continue

                title = html.escape(str(group.get("title") or "this group"))
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🎮 START THIS GAME",
                        callback_data=f"dailygame:{game_key}",
                    )
                ]])

                game_label = html.escape(label)
                text = (
                    "╭━━━〔 🎮 <b>VANYA DAILY DROP</b> 〕━━━╮\n"
                    f"👋 <b>{title}</b>\n\n"
                    "✨ <b>Today's random pick is here!</b>\n"
                    f"🔥 <b>{game_label}</b>\n\n"
                    "👥 <b>Gather the group & jump in!</b>\n"
                    "⚡ Quick game • Live fun • One daily drop\n\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n"
                    "👇 <b>Tap below to PLAY NOW</b> 🎯"
                )

                try:
                    await bot.send_message(
                        chat_id=group_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
                except Exception as exc:
                    print(
                        f"[RandomGame] send failed for {group_id}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    # Retry later only when Telegram rejected a transient send.
                    # If the group is gone/forbidden, stop future daily drops there.
                    error_name = type(exc).__name__.casefold()
                    if "forbidden" in error_name or "badrequest" in error_name:
                        await groups.update_one(
                            {"_id": group_id},
                            {"$set": {"active": False}},
                        )
                    else:
                        await groups.update_one(
                            {"_id": group_id, "random_game_last_date": today_key},
                            {"$set": {
                                "random_game_last_date": None,
                                "random_game_next_at": now_utc + timedelta(minutes=10),
                            }},
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[RandomGame] scheduler error: {type(exc).__name__}: {exc}")
