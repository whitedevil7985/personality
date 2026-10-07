import asyncio
import html
import random
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import ensure_user, get_user, add_coins, record_game_result


DEFAULT_BET = 100
MAX_BET = 1_000_000
MIN_CRASH = 1.01
MAX_CRASH = 25.00

# One live Crash round per player.
CRASH_GAMES = {}
_CRASH_LOCKS = {}


def _lock(uid):
    uid = int(uid)
    if uid not in _CRASH_LOCKS:
        _CRASH_LOCKS[uid] = asyncio.Lock()
    return _CRASH_LOCKS[uid]


def _cashout_markup(uid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💰 CASH OUT",
            callback_data=f"crash:{int(uid)}:cashout",
        )
    ]])


def _pick_crash_point():
    # Crash games usually stop near the lower multipliers, with occasional
    # larger spikes. This gives the round a more natural-looking curve.
    value = 1.0 + random.expovariate(0.65)
    value = min(MAX_CRASH, max(MIN_CRASH, value))
    return round(value, 2)


def _progress_text(user, amount, multiplier, elapsed, status="RUNNING"):
    name = html.escape(user.first_name or "Player")
    return (
        "╭━━━〔 🚀 <b>CRASH</b> 〕━━━╮\n"
        f"┃ 👤 <b>{name}</b>\n"
        f"┃ 💰 Bet: <b>{amount:,}</b> coins\n"
        f"┃ 📈 Multiplier: <b>{multiplier:.2f}x</b>\n"
        f"┃ ⏱️ Time: <b>{elapsed:.1f}s</b>\n"
        f"┃ 🟢 Status: <b>{status}</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "💰 Cash out before the rocket crashes!\n"
        "⚠️ If it crashes first, the stake is lost."
    )


async def _run_round(state, message, user):
    uid = state["uid"]
    amount = state["amount"]
    crash_point = state["crash_point"]
    started = state["started_at"]
    multiplier = 1.00

    try:
        while True:
            await asyncio.sleep(0.7)
            current = CRASH_GAMES.get(uid)

            # Player already cashed out / round was otherwise finished.
            if current is not state:
                return

            elapsed = time.monotonic() - started
            # Smooth accelerating curve.
            multiplier = min(crash_point, 1.00 + (elapsed * 0.10) + (elapsed ** 1.35) * 0.035)
            multiplier = round(multiplier, 2)

            if multiplier >= crash_point:
                async with _lock(uid):
                    current = CRASH_GAMES.get(uid)
                    if current is not state:
                        return
                    CRASH_GAMES.pop(uid, None)

                await record_game_result(
                    uid,
                    "CRASH",
                    0,
                    False,
                    message.chat_id,
                )

                try:
                    await message.edit_text(
                        "╭━━━〔 💥 <b>CRASH</b> 〕━━━╮\n"
                        f"┃ 📈 Reached: <b>{crash_point:.2f}x</b>\n"
                        f"┃ 💸 Lost: <b>{amount:,}</b> coins\n"
                        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                        "💥 The rocket crashed before cash out!\n"
                        "🎮 Use /crash <amount> to play again.",
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    print(f"[CRASH] crash-message error: {type(exc).__name__}: {exc}")
                return

            try:
                await message.edit_text(
                    _progress_text(user, amount, multiplier, elapsed),
                    parse_mode="HTML",
                    reply_markup=_cashout_markup(uid),
                )
            except Exception as exc:
                # Message edits can occasionally race with Telegram updates.
                print(f"[CRASH] animation edit error: {type(exc).__name__}: {exc}")
    except asyncio.CancelledError:
        return
    except Exception as exc:
        print(f"[CRASH] round task error: {type(exc).__name__}: {exc}")
        current = CRASH_GAMES.get(uid)
        if current is state:
            CRASH_GAMES.pop(uid, None)


async def crash(update, context):
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    uid = user.id

    try:
        amount = int(context.args[0]) if context.args else DEFAULT_BET
    except (TypeError, ValueError):
        amount = DEFAULT_BET

    if amount <= 0 or amount > MAX_BET:
        await update.message.reply_text(
            f"⚠️ Bet 1–{MAX_BET:,} coins ke beech honi chahiye."
        )
        return

    await ensure_user(user)

    async with _lock(uid):
        existing = CRASH_GAMES.get(uid)
        if existing:
            await update.message.reply_text(
                f"🚀 Crash already running at <b>{existing.get('current_multiplier', 1.00):.2f}x</b>. "
                "Pehle Cash Out karo.",
                parse_mode="HTML",
            )
            return

        db_user = await get_user(uid)
        balance = int((db_user or {}).get("coins", 0) or 0)
        if balance < amount:
            await update.message.reply_text(
                f"❌ Not enough virtual coins. Balance: <b>{balance:,}</b>",
                parse_mode="HTML",
            )
            return

        # Stake is locked before the rocket starts.
        await add_coins(uid, -amount)

        crash_point = _pick_crash_point()
        state = {
            "uid": uid,
            "amount": amount,
            "crash_point": crash_point,
            "started_at": time.monotonic(),
            "current_multiplier": 1.00,
            "task": None,
        }

        sent = await update.message.reply_html(
            _progress_text(user, amount, 1.00, 0.0),
            reply_markup=_cashout_markup(uid),
        )
        state["message_id"] = sent.message_id
        state["task"] = asyncio.create_task(_run_round(state, sent, user))
        CRASH_GAMES[uid] = state


async def crash_cb(q, data):
    if not q or not q.from_user:
        return

    uid = q.from_user.id
    async with _lock(uid):
        parts = list(data or [])
        if len(parts) != 3 or parts[0] != "crash":
            await q.answer("Invalid Crash button.", show_alert=True)
            return

        try:
            board_uid = int(parts[1])
        except (TypeError, ValueError):
            await q.answer("Invalid Crash round.", show_alert=True)
            return

        if board_uid != uid:
            await q.answer("🚀 This Crash round belongs to another player.", show_alert=True)
            return

        if parts[2] != "cashout":
            await q.answer("Invalid Crash action.", show_alert=True)
            return

        state = CRASH_GAMES.get(uid)
        if not state:
            await q.answer("💥 This Crash round has already ended.", show_alert=True)
            return

        elapsed = time.monotonic() - state["started_at"]
        multiplier = float(state.get("current_multiplier", 1.00))
        # Recalculate from elapsed time so the cash-out uses the live curve,
        # not a stale last-edited value.
        multiplier = min(
            state["crash_point"],
            1.00 + (elapsed * 0.10) + (elapsed ** 1.35) * 0.035,
        )
        multiplier = round(max(1.00, multiplier), 2)

        if multiplier >= state["crash_point"]:
            CRASH_GAMES.pop(uid, None)
            task = state.get("task")
            if task:
                task.cancel()
            await q.answer("💥 Too late — it crashed!", show_alert=True)
            try:
                await q.edit_message_text(
                    "╭━━━〔 💥 <b>CRASH</b> 〕━━━╮\n"
                    f"┃ 📈 Crash point: <b>{state['crash_point']:.2f}x</b>\n"
                    f"┃ 💸 Lost: <b>{state['amount']:,}</b> coins\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "💥 You tried to cash out too late.",
                    parse_mode="HTML",
                )
            except Exception as exc:
                print(f"[CRASH] late-cashout edit error: {type(exc).__name__}: {exc}")
            await record_game_result(uid, "CRASH", 0, False, q.message.chat_id if q.message else None)
            return

        amount = int(state["amount"])
        payout = max(amount, int(amount * multiplier))
        profit = payout - amount

        CRASH_GAMES.pop(uid, None)
        task = state.get("task")
        if task:
            task.cancel()

        await add_coins(uid, payout)
        points = max(0, min(300, profit // 5))
        await record_game_result(
            uid,
            "CRASH",
            points,
            profit > 0,
            q.message.chat_id if q.message else None,
        )

        new_user = await get_user(uid)
        new_balance = int((new_user or {}).get("coins", 0) or 0)

        await q.answer(f"💰 Cashed out at {multiplier:.2f}x!")
        try:
            await q.edit_message_text(
                "╭━━━〔 🏆 <b>CRASH CASHED OUT</b> 〕━━━╮\n"
                f"┃ 📈 Multiplier: <b>{multiplier:.2f}x</b>\n"
                f"┃ 💰 Payout: <b>+{payout:,}</b> coins\n"
                f"┃ ✨ Profit: <b>+{profit:,}</b> coins\n"
                f"┃ 💳 Balance: <b>{new_balance:,}</b> coins\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                "🚀 Nice timing! Play again with /crash <amount>.",
                parse_mode="HTML",
            )
        except Exception as exc:
            print(f"[CRASH] cashout-message error: {type(exc).__name__}: {exc}")
