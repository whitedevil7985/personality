import html
import random
from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users
try:
    import chess
except Exception:
    chess=None
chess_games={}

try:
    import chess
except Exception:
    chess=None
chess_games={}

def chess_kb(gid):
    b=chess_games[gid]["board"];icons={"P":"♙","N":"♘","B":"♗","R":"♖","Q":"♕","K":"♔","p":"♟","n":"♞","b":"♝","r":"♜","q":"♛","k":"♚"}
    rows=[]
    for r in range(7,-1,-1):
        row=[]
        for f in range(8):
            sq=chess.square(f,r);p=b.piece_at(sq)
            row.append(InlineKeyboardButton(icons.get(p.symbol(),"·"),callback_data=f"chess:{gid}:{sq}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🏳️ Resign",callback_data=f"resign:{gid}"), InlineKeyboardButton("💬 Chat",callback_data=f"gchat:CHESS:{gid}")])
    rows.append([InlineKeyboardButton("🎮 Games",callback_data="cat:games"), InlineKeyboardButton("⌂ Home",callback_data="home")])
    return kb(rows)

async def chess_cmd(update,context):
    if chess is None:await update.message.reply_text("Chess package unavailable.");return
    gid=f"{update.effective_chat.id}-{random.randint(1000,9999)}"
    chess_games[gid]={"board":chess.Board(),"players":[update.effective_user.id],"selected":{}}
    await update.message.reply_text(
        f"╭━━━〔 ♟️ <b>CHESS ARENA</b> 〕━━━╮\n┃ Room: <code>{gid}</code>\n┃ White: {html.escape(update.effective_user.first_name)}\n┃ Black: waiting…\n╰━━━━━━━━━━━━━━━━━━━━╯\n\nUse <code>/chessjoin</code> to enter the room.",
        parse_mode="HTML",reply_markup=chess_kb(gid))

async def chessjoin(update,context):
    if not chess_games:await update.message.reply_text("No game. Use /chess.");return
    gid,g=next(reversed(chess_games.items()))
    if update.effective_user.id not in g["players"] and len(g["players"])<2:g["players"].append(update.effective_user.id)
    await update.message.reply_text("♟️ Black joined. Select a piece, then its destination.")

async def chess_cb(q,parts):
    gid=parts[1];g=chess_games.get(gid)
    if not g:return
    if parts[0]=="resign":
        await q.edit_message_text(f"🏳️ {q.from_user.first_name} resigned.");chess_games.pop(gid,None);return
    if len(g["players"])<2:await q.answer("Waiting for Black.",show_alert=True);return
    b=g["board"];uid=q.from_user.id
    turn_uid=g["players"][0 if b.turn else 1]
    if uid!=turn_uid:await q.answer("Not your turn.",show_alert=True);return
    sq=int(parts[2]);selected=g["selected"].get(uid)
    if selected is None:g["selected"][uid]=sq;await q.answer("Piece selected — choose destination.");return
    move=chess.Move(selected,sq)
    if move not in b.legal_moves:
        g["selected"].pop(uid,None);await q.answer("Illegal move.",show_alert=True);return
    b.push(move);g["selected"].pop(uid,None)
    if b.is_checkmate():
        await q.edit_message_text(f"♚ <b>CHECKMATE!</b> {q.from_user.first_name} wins.",parse_mode="HTML");chess_games.pop(gid,None);return
    await q.edit_message_reply_markup(reply_markup=chess_kb(gid));await q.answer("Move played.")
