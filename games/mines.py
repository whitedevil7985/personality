import random
import asyncio

from telegram import InlineKeyboardButton
from games.common import kb
from db import ensure_user, get_user, add_coins, users, record_game_result


BOARD_SIZE = 5
MINE_COUNT = 5
SAFE_REWARD = 100

_MINES_LOCKS = {}


def _mines_lock(uid):
    lock = _MINES_LOCKS.get(int(uid))
    if lock is None:
        lock = asyncio.Lock()
        _MINES_LOCKS[int(uid)] = lock
    return lock


def _board_markup(uid, safe_tiles, mines_set=None, reveal_mines=False):
    safe_tiles = set(safe_tiles or [])
    mines_set = set(mines_set or []) if reveal_mines else set()

    rows = []
    for row_index in range(BOARD_SIZE):
        row = []
        for col_index in range(BOARD_SIZE):
            pos = row_index * BOARD_SIZE + col_index

            if pos in mines_set:
                label = "💣"
            elif pos in safe_tiles:
                label = "💎"
            else:
                label = "⬜"

            # A mine that is already hit/revealed should not be clickable.
            callback = f"mine:{int(uid)}:{pos}"
            row.append(InlineKeyboardButton(label, callback_data=callback))
        rows.append(row)

    rows.append([
        InlineKeyboardButton("💰 Cash Out", callback_data=f"mine:{int(uid)}:cashout")
    ])
    return kb(rows)


async def mines(update, context):
    user = update.effective_user
    if not user or not update.message:
        return

    await ensure_user(user)

    # Start a fresh round and clear any previous round for this player.
    board = list(range(BOARD_SIZE * BOARD_SIZE))
    mines_set = set(random.sample(board, MINE_COUNT))

    await users.update_one(
        {"_id": user.id},
        {
            "$set": {
                "mines_active": True,
                "mines_set": list(mines_set),
                "mines_safe": [],
                "mines_bet": 0,
                "mines_chat_id": update.effective_chat.id if update.effective_chat else None,
            }
        },
        upsert=True,
    )

    await update.message.reply_html(
        "💎 <b>MINES 5×5</b>\n\n"
        f"💣 <b>{MINE_COUNT} mines</b> hidden\n"
        "💎 Open safe tiles and cash out whenever you want.\n"
        f"💰 Each safe tile: <b>+{SAFE_REWARD} coins</b>\n\n"
        "⚠️ Hitting a mine ends the round.",
        reply_markup=_board_markup(user.id, []),
    )


async def mines_cb(q, data):
    try:
        if not q or not q.from_user:
            return

        uid = q.from_user.id
        async with _mines_lock(uid):
            parts = list(data or [])
            if len(parts) != 3 or parts[0] != "mine":
                await q.answer("Invalid Mines button.", show_alert=True)
                return

            try:
                board_uid = int(parts[1])
            except (TypeError, ValueError):
                await q.answer("Invalid Mines board.", show_alert=True)
                return

            if board_uid != uid:
                await q.answer(
                    "⛏️ This Mines board belongs to another player.",
                    show_alert=True,
                )
                return

            action = parts[2]
            u = await get_user(uid)

            if not u or not u.get("mines_active"):
                await q.answer(
                    "⛏️ No active Mines round. Use /mines to start one.",
                    show_alert=True,
                )
                return

            if action == "cashout":
                safe = list(u.get("mines_safe", []))
                if not safe:
                    await q.answer(
                        "Open at least one safe tile first.",
                        show_alert=True,
                    )
                    return

                reward = len(safe) * SAFE_REWARD
                await add_coins(uid, reward)
                await record_game_result(
                    uid,
                    "MINES",
                    reward,
                    True,
                    q.message.chat_id if q.message else None,
                )
                await users.update_one(
                    {"_id": uid},
                    {
                        "$set": {
                            "mines_active": False,
                            "mines_safe": [],
                            "mines_set": [],
                            "mines_bet": 0,
                            "mines_chat_id": None,
                        }
                    },
                )

                await q.answer("💰 Cash out successful!")
                await q.edit_message_text(
                    "💰 <b>MINES CASHED OUT!</b>\n\n"
                    f"💎 Safe tiles: <b>{len(safe)}</b>\n"
                    f"🏆 Reward: <b>+{reward:,} coins</b>",
                    parse_mode="HTML",
                )
                return

            try:
                pos = int(action)
            except (TypeError, ValueError):
                await q.answer("Invalid tile.", show_alert=True)
                return

            if pos < 0 or pos >= BOARD_SIZE * BOARD_SIZE:
                await q.answer("Invalid tile.", show_alert=True)
                return

            safe = list(u.get("mines_safe", []))
            mines_set = set(u.get("mines_set", []))

            if pos in safe:
                await q.answer("💎 Already opened.", show_alert=False)
                return

            if pos in mines_set:
                await record_game_result(
                    uid,
                    "MINES",
                    0,
                    False,
                    q.message.chat_id if q.message else None,
                )
                await users.update_one(
                    {"_id": uid},
                    {
                        "$set": {
                            "mines_active": False,
                            "mines_safe": [],
                            "mines_set": [],
                            "mines_bet": 0,
                        }
                    },
                )

                await q.answer("💥 BOOM!", show_alert=True)
                await q.edit_message_text(
                    "💥 <b>BOOM!</b>\n\n"
                    "You hit a mine. The round is over.\n"
                    "🎮 Use /mines to try again.",
                    parse_mode="HTML",
                )
                return

            safe.append(pos)
            await users.update_one(
                {"_id": uid},
                {"$set": {"mines_safe": safe}},
            )

            # If every non-mine tile is opened, automatically cash out.
            if len(safe) >= (BOARD_SIZE * BOARD_SIZE - MINE_COUNT):
                reward = len(safe) * SAFE_REWARD
                await add_coins(uid, reward)
                await record_game_result(
                    uid,
                    "MINES",
                    reward,
                    True,
                    q.message.chat_id if q.message else None,
                )
                await users.update_one(
                    {"_id": uid},
                    {
                        "$set": {
                            "mines_active": False,
                            "mines_safe": [],
                            "mines_set": [],
                            "mines_bet": 0,
                        }
                    },
                )
                await q.answer("🏆 All safe tiles found!")
                await q.edit_message_text(
                    "🏆 <b>MINES CLEARED!</b>\n\n"
                    f"💎 Safe tiles: <b>{len(safe)}</b>\n"
                    f"💰 Reward: <b>+{reward:,} coins</b>",
                    parse_mode="HTML",
                )
                return

            await q.answer("💎 Safe!")
            await q.edit_message_reply_markup(
                reply_markup=_board_markup(uid, safe),
            )

    except Exception as exc:
        try:
            await q.answer(
                "⚠️ Mines error. Start a new round with /mines.",
                show_alert=True,
            )
        except Exception:
            pass
        print(f"[MINES] callback error: {type(exc).__name__}: {exc}")
