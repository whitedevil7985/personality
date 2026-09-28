import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result
ludo_games={}

ludo_games={}
def ludo_board(g):
    cells=["⬜"]*25
    icons=["🔴","🟢","🟡","🔵"]
    for i,uid in enumerate(g["players"]):
        cells[min(24,g["pos"][uid])]=icons[i]
    return "\n".join("".join(cells[i:i+5]) for i in range(0,25,5))

async def ludo(update,context):
    gid=f"{update.effective_chat.id}-{random.randint(1000,9999)}";uid=update.effective_user.id
    ludo_games[gid]={"players":[uid],"pos":{uid:0},"turn":0}
    await update.message.reply_text(
        f"╭━━━〔 🎲 <b>LUDO ARENA</b> 〕━━━╮\n┃ Room: <code>{gid}</code>\n┃ Players: 1/4\n╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Invite friends with <code>/ludojoin</code>.", parse_mode="HTML",
        reply_markup=kb([
            [InlineKeyboardButton("🎯 Roll Dice",callback_data=f"ludo:{gid}")],
            [InlineKeyboardButton("💬 Game Chat",callback_data=f"gchat:LUDO:{gid}")],
            [InlineKeyboardButton("🎮 All Games",callback_data="cat:games")],
        ]))

async def ludojoin(update,context):
    if not ludo_games:await update.message.reply_text("No room. Use /ludo.");return
    gid,g=next(reversed(ludo_games.items()));uid=update.effective_user.id
    if uid not in g["players"] and len(g["players"])<4:g["players"].append(uid);g["pos"][uid]=0
    await update.message.reply_text(f"🎲 Ludo: {len(g['players'])}/4 players.")

async def ludo_cb(q,gid):
    g=ludo_games.get(gid)
    if not g:return
    uid=q.from_user.id
    if uid not in g["players"]:await q.answer("Join first.",show_alert=True);return
    if uid!=g["players"][g["turn"]]:await q.answer("Wait for your turn.",show_alert=True);return
    roll=random.randint(1,6);g["pos"][uid]=min(24,g["pos"][uid]+roll)
    if g["pos"][uid]>=24:
        await add_coins(uid, 500)
        await record_game_result(uid, "LUDO", 500, True, q.message.chat_id if q.message else None)
        await q.edit_message_text(f"🏆 <b>{q.from_user.first_name}</b> won Ludo!\n\n{ludo_board(g)}\n\n⭐ +500 points!",parse_mode="HTML");ludo_games.pop(gid,None);return
    g["turn"]=(g["turn"]+1)%len(g["players"])
    await q.edit_message_text(f"🎲 Rolled <b>{roll}</b>\n\n{ludo_board(g)}\n\nTurn: <code>{g['players'][g['turn']]}</code>",parse_mode="HTML",
        reply_markup=kb([[InlineKeyboardButton("🎯 Roll Dice",callback_data=f"ludo:{gid}"), InlineKeyboardButton("💬 Chat",callback_data=f"gchat:LUDO:{gid}")], [InlineKeyboardButton("🎮 Games",callback_data="cat:games"), InlineKeyboardButton("⌂ Home",callback_data="home")]]))
