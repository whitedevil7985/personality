import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users

async def mines(update, context):
    await ensure_user(update.effective_user)
    # 5x5 board; 5 mines. No real money is involved—only the bot's virtual coins.
    board = list(range(25))
    mines_set = set(random.sample(board, 5))
    await users.update_one({"_id": update.effective_user.id}, {"$set": {
        "mines_active": True, "mines_set": list(mines_set), "mines_safe": [],
        "mines_bet": 0
    }})
    rows = []
    for r in range(5):
        row = []
        for c in range(5):
            pos = r*5+c
            row.append(InlineKeyboardButton("⬜", callback_data=f"mine:{pos}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("💰 Cash Out", callback_data="mine:cashout")])
    await update.message.reply_text(
        "💎 <b>MINES 5×5</b>\nTap a tile. Hit a mine and the round ends. "
        "Virtual coins only. Cash out anytime.",
        parse_mode="HTML", reply_markup=kb(rows)
    )

async def mines_cb(q, data):
    uid = q.from_user.id
    u = await get_user(uid)
    if not u or not u.get("mines_active"):
        await q.answer("No active Mines round.", show_alert=True)
        return
    action = data[1]
    if action == "cashout":
        safe = len(u.get("mines_safe", []))
        if safe <= 0:
            await q.answer("Open at least one safe tile first.", show_alert=True)
            return
        reward = safe * 100
        await add_coins(uid, reward)
        await users.update_one({"_id": uid}, {"$set": {"mines_active": False}})
        await q.edit_message_text(f"💰 Cashed out <b>+{reward:,} coins</b> from Mines!", parse_mode="HTML")
        return
    pos = int(action)
    mines_set = set(u.get("mines_set", []))
    safe = list(u.get("mines_safe", []))
    if pos in safe:
        await q.answer("Already opened.", show_alert=False)
        return
    if pos in mines_set:
        await users.update_one({"_id": uid}, {"$set": {"mines_active": False}})
        await q.edit_message_text("💥 <b>BOOM!</b> You hit a mine. Round over.", parse_mode="HTML")
        return
    safe.append(pos)
    await users.update_one({"_id": uid}, {"$set": {"mines_safe": safe}})
    await q.answer("Safe! 💎")
    # Rebuild board with opened tiles.
    rows = []
    for r in range(5):
        row = []
        for c in range(5):
            p = r*5+c
            row.append(InlineKeyboardButton("💎" if p in safe else "⬜", callback_data=f"mine:{p}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("💰 Cash Out", callback_data="mine:cashout")])
    await q.edit_message_reply_markup(reply_markup=kb(rows))
