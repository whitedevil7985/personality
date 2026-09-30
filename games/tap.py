import random
import time

from telegram import InlineKeyboardButton
from games.common import kb
from db import add_coins, record_game_result


# message_id -> challenge data
TAP_GAMES = {}
TAP_TIMEOUT = 15.0


async def tap(update, context):
    user = update.effective_user
    if not user or not update.message:
        return

    # Store the challenge server-side so the callback cannot be replayed or
    # changed by editing callback_data.
    challenge_id = random.randint(100000, 999999)
    TAP_GAMES[challenge_id] = {
        "user_id": user.id,
        "created": time.monotonic(),
    }

    # Keep this store small.
    now = time.monotonic()
    for key, game in list(TAP_GAMES.items()):
        if now - game["created"] > TAP_TIMEOUT:
            TAP_GAMES.pop(key, None)

    await update.message.reply_html(
        "⚡ <b>TAP CHALLENGE!</b>\n\n"
        "Tap the button as fast as you can!\n"
        "⏱️ You have <b>15 seconds</b>.",
        reply_markup=kb([
            [InlineKeyboardButton(
                "⚡ TAP NOW",
                callback_data=f"tap:{user.id}:{challenge_id}",
            )]
        ]),
    )


async def tap_cb(q, data):
    try:
        if not q or not q.from_user:
            return

        parts = list(data or [])
        if len(parts) != 3 or parts[0] != "tap":
            await q.answer("Invalid tap challenge.", show_alert=True)
            return

        user_id = int(parts[1])
        challenge_id = int(parts[2])

        if user_id != q.from_user.id:
            await q.answer(
                "❌ This tap challenge belongs to another player.",
                show_alert=True,
            )
            return

        challenge = TAP_GAMES.get(challenge_id)
        if not challenge:
            await q.answer(
                "⏱️ This tap challenge has expired. Start a new one with /tap.",
                show_alert=True,
            )
            return

        if challenge["user_id"] != q.from_user.id:
            await q.answer("❌ Invalid player.", show_alert=True)
            return

        if time.monotonic() - challenge["created"] > TAP_TIMEOUT:
            TAP_GAMES.pop(challenge_id, None)
            await q.answer(
                "⏱️ Too slow! Start another /tap.",
                show_alert=True,
            )
            return

        # Consume the challenge before paying, so double-clicks cannot pay twice.
        TAP_GAMES.pop(challenge_id, None)

        reward = random.randint(20, 100)
        await add_coins(q.from_user.id, reward)

        chat_id = q.message.chat_id if q.message else None
        await record_game_result(
            q.from_user.id,
            "TAP",
            reward,
            True,
            chat_id,
        )

        await q.answer(f"⚡ +{reward} coins!")

        result_text = (
            "⚡ <b>TAP COMPLETE!</b>\n\n"
            f"🏆 <b>+{reward:,} coins</b>\n"
            "🔥 Fast fingers!"
        )

        try:
            if q.message:
                await q.edit_message_text(
                    result_text,
                    parse_mode="HTML",
                )
            else:
                await q.message.reply_html(result_text)
        except Exception:
            # If the original message was already edited/deleted, still show
            # the reward instead of making the callback look broken.
            if q.message:
                try:
                    await q.message.reply_html(result_text)
                except Exception:
                    pass

    except Exception as exc:
        try:
            await q.answer(
                "⚠️ Tap game error. Please start /tap again.",
                show_alert=True,
            )
        except Exception:
            pass
        print(f"[TAP] callback error: {type(exc).__name__}: {exc}")
