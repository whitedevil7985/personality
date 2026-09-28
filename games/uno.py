import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result
UNO_COLORS=["R","G","B","Y"]
UNO_NAMES={"R":"🔴","G":"🟢","B":"🔵","Y":"🟡"}
uno_games={}

def uno_card():
    return {"color":random.choice(UNO_COLORS),"value":random.choice(list("0123456789")+["skip","reverse","+2"])}

def uno_name(c): return f"{UNO_NAMES[c['color']]} {c['value'].upper()}"

async def uno(update,context):
    gid=f"{update.effective_chat.id}-{random.randint(1000,9999)}";u=update.effective_user
    uno_games[gid]={"players":[u.id],"names":{u.id:u.first_name},"hands":{u.id:[uno_card() for _ in range(7)]},"turn":0,"top":uno_card()}
    await update.message.reply_html(
        f"╭━━━〔 🃏 <b>UNO ARENA</b> 〕━━━╮\n┃ Room: <code>{gid}</code>\n┃ Players: 1/8\n╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Invite friends with <code>/unojoin</code> and open the arena.",
        reply_markup=kb([
            [InlineKeyboardButton("🃏 Open Arena",callback_data=f"uno:view:{gid}")],
            [InlineKeyboardButton("💬 Game Chat",callback_data=f"gchat:UNO:{gid}")],
            [InlineKeyboardButton("🎮 All Games",callback_data="cat:games")],
        ]))

async def unojoin(update,context):
    if not uno_games: await update.message.reply_text("No UNO room. Use /uno.");return
    gid,g=next(reversed(uno_games.items()));u=update.effective_user
    if u.id not in g["players"] and len(g["players"])<8:
        g["players"].append(u.id);g["names"][u.id]=u.first_name;g["hands"][u.id]=[uno_card() for _ in range(7)]
    await update.message.reply_text(f"🃏 UNO players: {len(g['players'])}/8")

def uno_markup(gid,uid):
    g=uno_games[gid];buttons=[]
    for i,c in enumerate(g["hands"][uid]):
        buttons.append(InlineKeyboardButton(uno_name(c),callback_data=f"uno:play:{gid}:{i}"))
    rows=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    rows.append([InlineKeyboardButton("➕ Draw",callback_data=f"uno:draw:{gid}"),
                 InlineKeyboardButton("💬 Chat",callback_data=f"gchat:UNO:{gid}")])
    rows.append([InlineKeyboardButton("🎮 Games",callback_data="cat:games"), InlineKeyboardButton("⌂ Home",callback_data="home")])
    return kb(rows)

async def uno_cb(q,parts):
    action=parts[1];gid=parts[2];g=uno_games.get(gid)
    if not g:return
    uid=q.from_user.id
    if uid not in g["hands"]:await q.answer("Join first with /unojoin.",show_alert=True);return
    if action=="view":
        await q.edit_message_text(f"🃏 <b>UNO</b>\nTop: {uno_name(g['top'])}\nCards: {len(g['hands'][uid])}\nTurn: {g['names'][g['players'][g['turn']]]}",
                                  parse_mode="HTML",reply_markup=uno_markup(gid,uid));return
    if uid!=g["players"][g["turn"]]:await q.answer("Not your turn.",show_alert=True);return
    if action=="draw":
        g["hands"][uid].append(uno_card());g["turn"]=(g["turn"]+1)%len(g["players"])
    elif action=="play":
        i=int(parts[3])
        if i>=len(g["hands"][uid]):return
        c=g["hands"][uid][i]
        if c["color"]!=g["top"]["color"] and c["value"]!=g["top"]["value"]:
            await q.answer("Match the color or value.",show_alert=True);return
        g["top"]=g["hands"][uid].pop(i);g["turn"]=(g["turn"]+1)%len(g["players"])
        if not g["hands"][uid]:
            await add_coins(uid, 500)
            await record_game_result(uid, "UNO", 500, True, q.message.chat_id if q.message else None)
            await q.edit_message_text(f"🏆 <b>{html.escape(g['names'][uid])}</b> won UNO!\n\n⭐ +500 points!",parse_mode="HTML");uno_games.pop(gid,None);return
    await q.answer("Move played!")
    await q.edit_message_text(f"🃏 <b>UNO</b>\nTop: {uno_name(g['top'])}\nCards: {len(g['hands'][uid])}\nTurn: {g['names'][g['players'][g['turn']]]}",parse_mode="HTML",reply_markup=uno_markup(gid,uid))
