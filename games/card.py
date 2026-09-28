import html
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import ensure_user, get_user, add_coins, add_xp, record_game_result


RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["♠️", "♥️", "♦️", "♣️"]
MAX_PLAYERS = 4
TOTAL_ROUNDS = 4
HAND_SIZE = 5

CARD_ROOMS = {}


def _new_deck():
    deck = [(rank, suit) for rank in RANKS for suit in SUITS]
    random.shuffle(deck)
    return deck


def _card_text(card):
    rank, suit = card
    return f"{rank}{suit}"


def _room_buttons(room_id, room):
    rows = []
    if len(room["players"]) < MAX_PLAYERS and not room["started"]:
        rows.append([InlineKeyboardButton(
            f"➕ Join ({len(room['players'])}/{MAX_PLAYERS})",
            callback_data=f"card:join:{room_id}",
        )])
    if not room["started"] and len(room["players"]) >= 2:
        rows.append([InlineKeyboardButton(
            "▶️ Start 4 Rounds",
            callback_data=f"card:start:{room_id}",
        )])
    if not room["started"]:
        rows.append([InlineKeyboardButton(
            "❌ Cancel Room",
            callback_data=f"card:cancel:{room_id}",
        )])
    return InlineKeyboardMarkup(rows) if rows else None


def _room_text(room):
    players = room["players"]
    names = room["names"]
    lines = [
        "╭━━━〔 🃏 <b>VANYA CARD MATCH</b> 〕━━━╮",
        "┃ <i>Private cards • Group gameplay</i> ✦",
        "╰━━━━━━━━━━━━━━━━━━━━╯",
        "",
        f"👥 Players: <b>{len(players)}/{MAX_PLAYERS}</b>",
    ]
    for i, uid in enumerate(players, 1):
        lines.append(f"{i}. {html.escape(names.get(uid, 'Player'))}")
    lines += [
        "",
        "📩 Cards will be sent privately by Vanya.",
        "💬 Plays and round results happen here in the group.",
        "",
        "🎯 <b>How it works</b>",
        f"• {TOTAL_ROUNDS} rounds",
        f"• {HAND_SIZE} private cards per round",
        "• Each player secretly picks 1 card",
        "• Same-rank cards match and give points",
        "• Most points after round 4 wins",
    ]
    return "
".join(lines)


async def card(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        await update.message.reply_text(
            "🃏 /card ko group mein use karo — game group mein chalega aur cards mujhe DM mein milenge."
        )
        return

    room_id = f"{chat.id}-{random.randint(10000, 99999)}"
    uid = user.id
    CARD_ROOMS[room_id] = {
        "group_id": chat.id,
        "host": uid,
        "players": [uid],
        "names": {uid: user.first_name or "Player"},
        "hands": {},
        "selected": {},
        "scores": {uid: 0},
        "collections": {uid: []},
        "round": 0,
        "started": False,
        "message_id": None,
    }

    markup = _room_buttons(room_id, CARD_ROOMS[room_id])
    msg = await update.message.reply_html(
        _room_text(CARD_ROOMS[room_id])
        + f"\n\n👑 Host: <b>{html.escape(user.first_name or 'Player')}</b>",
        reply_markup=markup,
    )
    CARD_ROOMS[room_id]["message_id"] = msg.message_id


async def cardjoin(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        await update.message.reply_text("🃏 /cardjoin group mein use karo.")
        return

    room = next(
        (r for r in reversed(list(CARD_ROOMS.values()))
         if r["group_id"] == chat.id and not r["started"] and len(r["players"]) < MAX_PLAYERS),
        None,
    )
    if not room:
        await update.message.reply_text("❌ Koi open Card room nahi hai. Pehle /card karo.")
        return

    uid = user.id
    if uid in room["players"]:
        await update.message.reply_text("👀 Tum already room mein ho.")
        return

    room["players"].append(uid)
    room["names"][uid] = user.first_name or "Player"
    room["scores"][uid] = 0
    room["collections"][uid] = []

    try:
        await context.bot.edit_message_text(
            chat_id=room["group_id"],
            message_id=room["message_id"],
            text=_room_text(room),
            parse_mode="HTML",
            reply_markup=_room_buttons(next(k for k, v in CARD_ROOMS.items() if v is room), room),
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ <b>{html.escape(user.first_name or 'Player')}</b> joined the Card Match. "
        f"{len(room['players'])}/{MAX_PLAYERS} players.",
        parse_mode="HTML",
    )


async def cardstart(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        await update.message.reply_text("🃏 /cardstart group mein use karo.")
        return

    room_id, room = next(
        ((k, r) for k, r in reversed(list(CARD_ROOMS.items()))
         if r["group_id"] == chat.id and not r["started"]),
        (None, None),
    )
    if not room:
        await update.message.reply_text("❌ Koi waiting Card room nahi hai.")
        return
    if user.id != room["host"]:
        await update.message.reply_text("⛔ Sirf room host game start kar sakta hai.")
        return
    if len(room["players"]) < 2:
        await update.message.reply_text("👥 Minimum 2 players chahiye.")
        return

    await _start_round(update, context, room_id, room)


async def cardcancel(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        return
    room_id, room = next(
        ((k, r) for k, r in reversed(list(CARD_ROOMS.items()))
         if r["group_id"] == chat.id and not r["started"]),
        (None, None),
    )
    if not room:
        await update.message.reply_text("❌ Koi waiting Card room nahi hai.")
        return
    if user.id != room["host"]:
        await update.message.reply_text("⛔ Sirf host room cancel kar sakta hai.")
        return
    CARD_ROOMS.pop(room_id, None)
    await update.message.reply_text("🛑 Card Match room cancelled.")


async def _start_round(update, context, room_id, room):
    room["started"] = True
    room["round"] += 1
    room["selected"] = {}
    deck = _new_deck()
    room["hands"] = {uid: [deck.pop() for _ in range(HAND_SIZE)] for uid in room["players"]}

    await context.bot.send_message(
        chat_id=room["group_id"],
        text=(
            f"🃏 <b>Round {room['round']}/{TOTAL_ROUNDS}</b> started!\n\n"
            "📩 Vanya tumhare 5 cards DM kar rahi hai.\n"
            "🔐 Apne DM mein <b>sirf 1 card</b> choose karo.\n"
            "💬 Sabke select karte hi group mein cards reveal honge."
        ),
        parse_mode="HTML",
    )

    failed = []
    failed = []
    for uid in room["players"]:
        hand = room["hands"][uid]
        buttons = [
            InlineKeyboardButton(
                _card_text(card),
                callback_data=f"card:play:{room_id}:{room['round']}:{i}",
            )
            for i, card in enumerate(hand)
        ]
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"🃏 <b>Vanya Card Match</b>\n"
                    f"Round <b>{room['round']}/{TOTAL_ROUNDS}</b>\n\n"
                    "Tumhare private cards:\n"
                    "Ek card choose karo — baaki cards is round mein discard ho jayenge. 🔐"
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        except Exception:
            failed.append(uid)

    if failed:
        names = ", ".join(html.escape(room["names"].get(uid, "Player")) for uid in failed)
        await context.bot.send_message(
            chat_id=room["group_id"],
            text=(
                "⚠️ In players ko cards DM nahi ho paaye: "
                f"<b>{names}</b>.\n"
                "Please unhe Vanya ke private chat mein /start karne ko bolo."
            ),
            parse_mode="HTML",
        )


async def card_cb(q, parts):
    if len(parts) < 3:
        return
    action = parts[1]
    room_id = parts[2]
    room = CARD_ROOMS.get(room_id)
    if not room:
        await q.answer("This Card room is over.", show_alert=True)
        return

    uid = q.from_user.id

    if action == "join":
        if room["started"]:
            await q.answer("Game already started.", show_alert=True)
            return
        if uid in room["players"]:
            await q.answer("You're already in.", show_alert=True)
            return
        if len(room["players"]) >= MAX_PLAYERS:
            await q.answer("Room is full.", show_alert=True)
            return
        room["players"].append(uid)
        room["names"][uid] = q.from_user.first_name or "Player"
        room["scores"][uid] = 0
        room["collections"][uid] = []
        try:
            await q.message.edit_text(
                _room_text(room),
                parse_mode="HTML",
                reply_markup=_room_buttons(room_id, room),
            )
        except Exception:
            pass
        await q.answer("Joined! 🃏")
        return

    if action == "start":
        if room["started"]:
            await q.answer("Already started.", show_alert=True)
            return
        if uid != room["host"]:
            await q.answer("Only the host can start.", show_alert=True)
            return
        if len(room["players"]) < 2:
            await q.answer("Need at least 2 players.", show_alert=True)
            return
        await q.answer("Starting… 🃏")
        await _start_round(q.message, q.get_bot(), room_id, room)
        return

    if action == "cancel":
        if room["started"]:
            await q.answer("Game already started.", show_alert=True)
            return
        if uid != room["host"]:
            await q.answer("Only the host can cancel.", show_alert=True)
            return
        CARD_ROOMS.pop(room_id, None)
        try:
            await q.message.edit_text("🛑 <b>Card Match room cancelled.</b>", parse_mode="HTML")
        except Exception:
            pass
        await q.answer("Cancelled.")
        return

    if action == "play":
        if not room["started"]:
            await q.answer("Game hasn't started.", show_alert=True)
            return
        if uid not in room["players"]:
            await q.answer("Join the room first.", show_alert=True)
            return
        try:
            round_no = int(parts[3])
            index = int(parts[4])
        except (ValueError, IndexError):
            await q.answer("Invalid card.", show_alert=True)
            return
        if round_no != room["round"]:
            await q.answer("That round is already over.", show_alert=True)
            return
        if uid in room["selected"]:
            await q.answer("You already played this round.", show_alert=True)
            return
        hand = room["hands"].get(uid, [])
        if index < 0 or index >= len(hand):
            await q.answer("Card no longer available.", show_alert=True)
            return

        chosen = hand[index]
        room["selected"][uid] = chosen
        await q.answer(f"Locked { _card_text(chosen) } 🔒", show_alert=False)

        try:
            await q.edit_message_text(
                f"🃏 <b>Round {room['round']}/{TOTAL_ROUNDS}</b>\\n\\n"
                f"🔒 Selected: <b>{html.escape(_card_text(chosen))}</b>\\n"
                "Wait for the other players…",
                parse_mode="HTML",
            )
        except Exception:
            pass

        count = len(room["selected"])
        total = len(room["players"])
        await context_bot_send(q, room["group_id"],
            f"🔐 {html.escape(room['names'].get(uid, 'Player'))} has locked a card "
            f"(<b>{count}/{total}</b>)."
        )

        if count == total:
            await _resolve_round(q, room_id)
        return


async def context_bot_send(q, chat_id, text):
    try:
        await q.get_bot().send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception:
        pass


async def _resolve_round(q, room_id):
    room = CARD_ROOMS.get(room_id)
    if not room:
        return
    selected = room["selected"]
    groups = {}
    for uid, chosen in selected.items():
        rank = chosen[0]
        groups.setdefault(rank, []).append(uid)

    result_lines = [
        f"🃏 <b>Round {room['round']}/{TOTAL_ROUNDS} Result</b>",
        "",
    ]

    for rank, players in sorted(groups.items(), key=lambda item: RANKS.index(item[0])):
        cards = ", ".join(
            f"{html.escape(room['names'].get(uid, 'Player'))} {_card_text(selected[uid])}"
            for uid in players
        )
        if len(players) >= 2:
            per_player = 10 * (len(players) - 1)
            for uid in players:
                room["scores"][uid] += per_player
                room["collections"][uid].append({
                    "rank": rank,
                    "cards": [_card_text(selected[x]) for x in players],
                    "points": per_player,
                })
            result_lines.append(
                f"🎯 <b>{rank}</b> matched x{len(players)} → "
                f"+{per_player} each\\n{cards}"
            )
        else:
            result_lines.append(f"• {cards} → 0 match points")

    result_lines += [
        "",
        "📊 <b>Scores</b>",
    ]
    for uid in sorted(room["players"], key=lambda x: (-room["scores"][x], x)):
        result_lines.append(
            f"• {html.escape(room['names'].get(uid, 'Player'))}: "
            f"<b>{room['scores'][uid]}</b> pts"
        )

    await q.get_bot().send_message(
        chat_id=room["group_id"],
        text="\n".join(result_lines),
        parse_mode="HTML",
    )

    if room["round"] >= TOTAL_ROUNDS:
        ranked = sorted(
            room["players"],
            key=lambda x: (-room["scores"][x], room["names"].get(x, "Player"))
        )
        top_score = room["scores"][ranked[0]]
        winners = [uid for uid in ranked if room["scores"][uid] == top_score]

        for uid in room["players"]:
            is_winner = uid in winners
            points = room["scores"][uid]
            await record_game_result(
                uid, "CARD", points, is_winner, room["group_id"]
            )
            await add_xp(uid, 50 + (50 if is_winner else 0))
            await add_coins(uid, 100 + (250 if is_winner else 0))

        if len(winners) == 1:
            winner_text = (
                f"🏆 <b>Winner: {html.escape(room['names'][winners[0]])}</b>\\n"
                f"👑 {top_score} points"
            )
        else:
            winner_text = (
                "🏆 <b>Joint winners!</b>\\n"
                + ", ".join(html.escape(room["names"][uid]) for uid in winners)
                + f"\\n👑 {top_score} points each"
            )

        final_lines = [
            "╭━━━〔 🏆 <b>CARD MATCH FINISHED</b> 〕━━━╮",
            "┃ <i>4 rounds completed</i> ✦",
            "╰━━━━━━━━━━━━━━━━━━━━╯",
            "",
            winner_text,
            "",
            "📊 <b>Final Scores</b>",
        ]
        for uid in ranked:
            final_lines.append(
                f"• {html.escape(room['names'].get(uid, 'Player'))}: "
                f"<b>{room['scores'][uid]}</b> pts"
            )
        final_lines += [
            "",
            "💰 Winner reward: +250 coins • ⭐ +50 XP",
            "💰 Participation reward: +100 coins • ⭐ +50 XP",
        ]
        await q.get_bot().send_message(
            chat_id=room["group_id"],
            text="\n".join(final_lines),
            parse_mode="HTML",
        )
        CARD_ROOMS.pop(room_id, None)
        return

    room["round"] += 1
    room["selected"] = {}
    # Start the next round after a short pause.
    await _start_round(q.message, q.get_bot(), room_id, room)
