import html
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db import add_coins, add_xp, record_game_result

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
    return f"{card[0]}{card[1]}"


def _find_room(group_id, waiting_only=False):
    rooms = reversed(list(CARD_ROOMS.items()))
    for room_id, room in rooms:
        if room["group_id"] != group_id:
            continue
        if waiting_only and room["started"]:
            continue
        return room_id, room
    return None, None


def _room_markup(room_id, room):
    rows = []
    if not room["started"]:
        if len(room["players"]) < MAX_PLAYERS:
            rows.append([
                InlineKeyboardButton(
                    f"➕ Join ({len(room['players'])}/{MAX_PLAYERS})",
                    callback_data=f"card:join:{room_id}",
                )
            ])
        if len(room["players"]) >= 2:
            rows.append([
                InlineKeyboardButton(
                    "▶️ Start 4 Rounds",
                    callback_data=f"card:start:{room_id}",
                )
            ])
        rows.append([
            InlineKeyboardButton(
                "❌ Cancel Room",
                callback_data=f"card:cancel:{room_id}",
            )
        ])
    return InlineKeyboardMarkup(rows) if rows else None


def _room_text(room):
    lines = [
        "╭━━━〔 🃏 <b>VANYA CARD MATCH</b> 〕━━━╮",
        "┃ <i>Private cards • Group gameplay</i> ✦",
        "╰━━━━━━━━━━━━━━━━━━━━╯",
        "",
        f"👥 Players: <b>{len(room['players'])}/{MAX_PLAYERS}</b>",
    ]
    for i, uid in enumerate(room["players"], 1):
        lines.append(f"{i}. {html.escape(room['names'].get(uid, 'Player'))}")

    lines += [
        "",
        "📩 Vanya cards ko <b>DM</b> mein degi.",
        "💬 Match aur results <b>group</b> mein honge.",
        "",
        "🎯 <b>Rules</b>",
        f"• {TOTAL_ROUNDS} rounds",
        f"• Har round {HAND_SIZE} private cards",
        "• Har player DM se 1 card secretly play karega",
        "• Same-rank cards match honge",
        "• Match = points + matched-card collection",
        "• 4 rounds ke baad sabse zyada points winner",
    ]
    return "\n".join(lines)


async def card(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        await update.message.reply_text(
            "🃏 /card group mein use karo — cards DM mein milenge aur game group mein chalega."
        )
        return

    old_id, old_room = _find_room(chat.id, waiting_only=True)
    if old_room:
        await update.message.reply_html(
            "🃏 <b>Ek Card Match room already open hai.</b>\n\n"
            "Use <code>/cardjoin</code> to join ya host <code>/cardstart</code> se start kare."
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

    room = CARD_ROOMS[room_id]
    msg = await update.message.reply_html(
        _room_text(room)
        + f"\n\n👑 Host: <b>{html.escape(user.first_name or 'Player')}</b>",
        reply_markup=_room_markup(room_id, room),
    )
    room["message_id"] = msg.message_id


async def cardjoin(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        await update.message.reply_text("🃏 /cardjoin group mein use karo.")
        return

    room_id, room = _find_room(chat.id, waiting_only=True)
    if not room:
        await update.message.reply_text("❌ Koi open Card Match room nahi hai. Pehle /card karo.")
        return

    if user.id in room["players"]:
        await update.message.reply_text("👀 Tum already room mein ho.")
        return

    if len(room["players"]) >= MAX_PLAYERS:
        await update.message.reply_text("❌ Room full hai — maximum 4 players.")
        return

    room["players"].append(user.id)
    room["names"][user.id] = user.first_name or "Player"
    room["scores"][user.id] = 0
    room["collections"][user.id] = []

    try:
        await context.bot.edit_message_text(
            chat_id=room["group_id"],
            message_id=room["message_id"],
            text=_room_text(room),
            parse_mode="HTML",
            reply_markup=_room_markup(room_id, room),
        )
    except Exception:
        pass

    await update.message.reply_html(
        f"✅ <b>{html.escape(user.first_name or 'Player')}</b> joined! "
        f"Players: <b>{len(room['players'])}/{MAX_PLAYERS}</b>"
    )


async def cardstart(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        await update.message.reply_text("🃏 /cardstart group mein use karo.")
        return

    room_id, room = _find_room(chat.id, waiting_only=True)
    if not room:
        await update.message.reply_text("❌ Koi waiting Card Match room nahi hai.")
        return

    if user.id != room["host"]:
        await update.message.reply_text("⛔ Sirf host game start kar sakta hai.")
        return

    if len(room["players"]) < 2:
        await update.message.reply_text("👥 Minimum 2 players chahiye.")
        return

    await _start_round(context.bot, room_id, room)


async def cardcancel(update, context):
    chat = update.effective_chat
    user = update.effective_user
    if not chat or chat.type == "private":
        await update.message.reply_text("🃏 /cardcancel group mein use karo.")
        return

    room_id, room = _find_room(chat.id, waiting_only=True)
    if not room:
        await update.message.reply_text("❌ Koi waiting Card Match room nahi hai.")
        return

    if user.id != room["host"]:
        await update.message.reply_text("⛔ Sirf host room cancel kar sakta hai.")
        return

    CARD_ROOMS.pop(room_id, None)
    await update.message.reply_text("🛑 Card Match room cancelled.")


async def _start_round(bot, room_id, room):
    room["started"] = True
    room["round"] += 1
    room["selected"] = {}

    deck = _new_deck()
    room["hands"] = {
        uid: [deck.pop() for _ in range(HAND_SIZE)]
        for uid in room["players"]
    }

    await bot.send_message(
        chat_id=room["group_id"],
        text=(
            f"🃏 <b>Round {room['round']}/{TOTAL_ROUNDS}</b> started!\n\n"
            "📩 Vanya ne cards sabke DM mein bhej diye hain.\n"
            "🔐 Apne DM se <b>1 card</b> choose karo.\n"
            "💬 Sab choose karenge to cards yahin group mein reveal honge."
        ),
        parse_mode="HTML",
    )

    failed = []
    for uid in list(room["players"]):
        hand = room["hands"][uid]
        buttons = [
            InlineKeyboardButton(
                _card_text(card),
                callback_data=f"card:play:{room_id}:{room['round']}:{index}",
            )
            for index, card in enumerate(hand)
        ]
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]

        try:
            await bot.send_message(
                chat_id=uid,
                text=(
                    f"🃏 <b>Vanya Card Match</b>\n"
                    f"Round <b>{room['round']}/{TOTAL_ROUNDS}</b>\n\n"
                    "Tumhare 5 private cards:\n"
                    "👇 Sirf <b>1 card</b> select karo.\n"
                    "Tumhari hand baaki players ko nahi dikhegi."
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        except Exception:
            failed.append(uid)

    if failed:
        for uid in failed:
            if uid in room["players"]:
                room["players"].remove(uid)
            room["names"].pop(uid, None)
            room["hands"].pop(uid, None)
            room["scores"].pop(uid, None)
            room["collections"].pop(uid, None)

        names = ", ".join(
            html.escape(str(x)) for x in
            [room["names"].get(uid, "Player") for uid in failed]
        ) or "Some players"

        await bot.send_message(
            chat_id=room["group_id"],
            text=(
                "⚠️ Kuch players ko DM nahi ho paaya. Unhe Vanya ke private chat mein "
                "<code>/start</code> karna hoga. Failed players ko room se hata diya gaya hai."
            ),
            parse_mode="HTML",
        )

    if len(room["players"]) < 2:
        CARD_ROOMS.pop(room_id, None)
        await bot.send_message(
            chat_id=room["group_id"],
            text="🛑 Card Match cancel ho gaya — kam se kam 2 players ko Vanya DM enable karna hoga.",
        )


async def card_cb(q, parts):
    if len(parts) < 3:
        return

    action = parts[1]
    room_id = parts[2]
    room = CARD_ROOMS.get(room_id)
    if not room:
        await q.answer("Game over.", show_alert=True)
        return

    uid = q.from_user.id

    if action == "join":
        if room["started"]:
            await q.answer("Game already started.", show_alert=True)
            return
        if uid in room["players"]:
            await q.answer("Already joined.", show_alert=True)
            return
        if len(room["players"]) >= MAX_PLAYERS:
            await q.answer("Room full.", show_alert=True)
            return

        room["players"].append(uid)
        room["names"][uid] = q.from_user.first_name or "Player"
        room["scores"][uid] = 0
        room["collections"][uid] = []

        try:
            await q.message.edit_text(
                _room_text(room),
                parse_mode="HTML",
                reply_markup=_room_markup(room_id, room),
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
        await _start_round(q.get_bot(), room_id, room)
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

    if action != "play":
        return

    if not room["started"]:
        await q.answer("Game hasn't started.", show_alert=True)
        return
    if uid not in room["players"]:
        await q.answer("You are not in this game.", show_alert=True)
        return
    if uid in room["selected"]:
        await q.answer("You already played this round.", show_alert=True)
        return

    try:
        round_no = int(parts[3])
        card_index = int(parts[4])
    except (ValueError, IndexError):
        await q.answer("Invalid card.", show_alert=True)
        return

    if round_no != room["round"]:
        await q.answer("That round is over.", show_alert=True)
        return

    hand = room["hands"].get(uid, [])
    if card_index < 0 or card_index >= len(hand):
        await q.answer("Card no longer available.", show_alert=True)
        return

    chosen = hand[card_index]
    room["selected"][uid] = chosen

    try:
        await q.edit_message_text(
            f"🃏 <b>Round {room['round']}/{TOTAL_ROUNDS}</b>\n\n"
            f"🔒 Selected: <b>{html.escape(_card_text(chosen))}</b>\n"
            "Wait for the other players…",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await q.answer("Card locked 🔒")

    await q.get_bot().send_message(
        chat_id=room["group_id"],
        text=(
            f"🔐 <b>{html.escape(room['names'].get(uid, 'Player'))}</b> "
            f"locked a card — {len(room['selected'])}/{len(room['players'])}"
        ),
        parse_mode="HTML",
    )

    if len(room["selected"]) == len(room["players"]):
        await _resolve_round(q.get_bot(), room_id)


async def _resolve_round(bot, room_id):
    room = CARD_ROOMS.get(room_id)
    if not room:
        return

    selected = room["selected"]
    by_rank = {}
    for uid, card in selected.items():
        by_rank.setdefault(card[0], []).append(uid)

    result = [
        f"🃏 <b>Round {room['round']}/{TOTAL_ROUNDS} Result</b>",
        "",
    ]

    for rank in RANKS:
        players = by_rank.get(rank)
        if not players:
            continue

        shown = ", ".join(
            f"{html.escape(room['names'].get(uid, 'Player'))} {_card_text(selected[uid])}"
            for uid in players
        )

        if len(players) >= 2:
            points = 10 * (len(players) - 1)
            for uid in players:
                room["scores"][uid] += points
                room["collections"][uid].append({
                    "rank": rank,
                    "cards": [_card_text(selected[x]) for x in players],
                    "points": points,
                })
            result.append(
                f"🎯 <b>{rank}</b> matched ×{len(players)} → "
                f"<b>+{points} each</b>\n{shown}"
            )
        else:
            result.append(f"• {shown} → no match")

    result += [
        "",
        "📊 <b>Current scores</b>",
    ]
    for uid in sorted(room["players"], key=lambda x: (-room["scores"][x], room["names"].get(x, ""))):
        result.append(
            f"• {html.escape(room['names'].get(uid, 'Player'))}: "
            f"<b>{room['scores'][uid]}</b> pts"
        )

    await bot.send_message(
        chat_id=room["group_id"],
        text="\n".join(result),
        parse_mode="HTML",
    )

    if room["round"] >= TOTAL_ROUNDS:
        top = max(room["scores"].values())
        winners = [uid for uid in room["players"] if room["scores"][uid] == top]

        for uid in room["players"]:
            won = uid in winners
            await record_game_result(
                uid, "CARD", room["scores"][uid], won, room["group_id"]
            )
            await add_xp(uid, 50 + (50 if won else 0))
            await add_coins(uid, 100 + (250 if won else 0))

        final = [
            "╭━━━〔 🏆 <b>CARD MATCH FINISHED</b> 〕━━━╮",
            "┃ <i>4 rounds completed</i> ✦",
            "╰━━━━━━━━━━━━━━━━━━━━╯",
            "",
        ]

        if len(winners) == 1:
            winner = winners[0]
            final.append(
                f"🏆 <b>{html.escape(room['names'][winner])}</b> wins with "
                f"<b>{top} points</b>!"
            )
        else:
            final.append(
                "🏆 <b>Joint winners!</b> "
                + ", ".join(html.escape(room["names"][uid]) for uid in winners)
                + f" — <b>{top} points</b>"
            )

        final.append("")
        final.append("📊 <b>Final Scores</b>")
        for uid in sorted(room["players"], key=lambda x: (-room["scores"][x], room["names"].get(x, ""))):
            final.append(
                f"• {html.escape(room['names'].get(uid, 'Player'))}: "
                f"<b>{room['scores'][uid]}</b> pts"
            )

        final += [
            "",
            "💰 Winner: +250 coins • ⭐ +100 XP",
            "💰 Others: +100 coins • ⭐ +50 XP",
        ]

        await bot.send_message(
            chat_id=room["group_id"],
            text="\n".join(final),
            parse_mode="HTML",
        )
        CARD_ROOMS.pop(room_id, None)
        return

    await _start_round(bot, room_id, room)
