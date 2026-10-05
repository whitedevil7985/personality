import html
import random
import asyncio

from telegram import InlineKeyboardButton
from games.common import kb, safe_name
from db import ensure_user, get_user, add_coins, add_xp, users, record_game_result

rps_choices = ["rock", "paper", "scissors"]
RPS_GAMES = {}
_RPS_LOCK = asyncio.Lock()


def _choice_label(choice):
    return {
        "rock": "🪨 Rock",
        "paper": "📄 Paper",
        "scissors": "✂️ Scissors",
    }.get(choice, choice.title())


def _winner(a, b):
    if a == b:
        return 0
    if (
        (a == "rock" and b == "scissors")
        or (a == "paper" and b == "rock")
        or (a == "scissors" and b == "paper")
    ):
        return 1
    return 2


def _rps_keyboard(game_id):
    game = RPS_GAMES.get(game_id, {})
    players = game.get("players", [])
    if len(players) < 2:
        return kb([
            [InlineKeyboardButton("🎯 Join RPS", callback_data=f"rps:join:{game_id}")],
            [InlineKeyboardButton("⌂ Home", callback_data="home")],
        ])
    return kb([
        [
            InlineKeyboardButton("🪨 Rock", callback_data=f"rps:choice:{game_id}:rock"),
            InlineKeyboardButton("📄 Paper", callback_data=f"rps:choice:{game_id}:paper"),
        ],
        [
            InlineKeyboardButton("✂️ Scissors", callback_data=f"rps:choice:{game_id}:scissors"),
        ],
        [InlineKeyboardButton("⌂ Home", callback_data="home")],
    ])


async def rps(update, context):
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.message.reply_text("🪨 RPS group mein 2 players ke saath khelo.")
        return

    # Reuse the current room instead of silently creating multiple matches.
    existing_id = None
    for gid, game in RPS_GAMES.items():
        if game.get("chat_id") == chat.id:
            existing_id = gid
            break

    if existing_id:
        game = RPS_GAMES[existing_id]
        players = game.get("players", [])
        if update.effective_user.id not in players and len(players) < 2:
            players.append(update.effective_user.id)
            game["names"][update.effective_user.id] = update.effective_user.first_name
            await update.message.reply_html(
                f"✅ <b>{html.escape(update.effective_user.first_name or 'Player')}</b> joined RPS!\n\n"
                "Both players choose your move below.",
                reply_markup=_rps_keyboard(existing_id),
            )
        else:
            await update.message.reply_html(
                "🪨 <b>RPS is already active</b> in this group.\n\n"
                "Join the current room or wait for it to finish.",
                reply_markup=_rps_keyboard(existing_id),
            )
        return

    gid = f"{chat.id}-{random.randint(10000, 99999)}"
    uid = update.effective_user.id
    await ensure_user(update.effective_user)
    RPS_GAMES[gid] = {
        "chat_id": chat.id,
        "players": [uid],
        "names": {uid: update.effective_user.first_name},
        "choices": {},
        "message_id": None,
    }

    sent = await update.message.reply_html(
        "╭━━━〔 🪨 <b>RPS DUEL</b> 〕━━━╮\n"
        "┃ <i>2 Player Rock • Paper • Scissors</i> ✦\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👤 Player 1: <b>{html.escape(update.effective_user.first_name or 'Player')}</b>\n"
        "👤 Player 2: <i>Waiting to join…</i>\n\n"
        "🎯 Another player tap <b>Join RPS</b> (or use /rps), then both choose your move.",
        reply_markup=_rps_keyboard(gid),
    )
    RPS_GAMES[gid]["message_id"] = sent.message_id


async def rps_cb(q, parts):
    async with _RPS_LOCK:
        if len(parts) < 2:
            await q.answer("Invalid RPS game.", show_alert=True)
            return

        action = parts[1]

        if action == "join":
            if len(parts) < 3:
                await q.answer("Invalid RPS room.", show_alert=True)
                return
            gid = parts[2]
            game = RPS_GAMES.get(gid)
            if not game:
                await q.answer("RPS game is over.", show_alert=True)
                return

            uid = q.from_user.id
            if uid not in game["players"] and len(game["players"]) >= 2:
                await q.answer("This RPS duel already has 2 players.", show_alert=True)
                return

            if uid not in game["players"]:
                await ensure_user(q.from_user)
                game["players"].append(uid)
                game["names"][uid] = q.from_user.first_name
                await q.answer("Joined RPS! Choose your move.")
                await q.edit_message_text(
                    "╭━━━〔 🪨 <b>RPS DUEL</b> 〕━━━╮\n"
                    "┃ <i>2 Player Rock • Paper • Scissors</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    f"👤 Player 1: <b>{html.escape(game['names'][game['players'][0]])}</b>\n"
                    f"👤 Player 2: <b>{html.escape(game['names'][game['players'][1]])}</b>\n\n"
                    "🎯 Both players choose your move secretly.",
                    parse_mode="HTML",
                    reply_markup=_rps_keyboard(gid),
                )
                return

            await q.answer("You're already in this duel.", show_alert=True)
            return

        if action != "choice" or len(parts) < 4:
            await q.answer("Invalid RPS choice.", show_alert=True)
            return

        gid = parts[2]
        choice = parts[3].lower()
        game = RPS_GAMES.get(gid)
        if not game or choice not in rps_choices:
            await q.answer("RPS game is no longer active.", show_alert=True)
            return

        uid = q.from_user.id
        if uid not in game["players"]:
            await q.answer("Join the duel first.", show_alert=True)
            return

        game["choices"][uid] = choice
        await q.answer(f"Selected {_choice_label(choice)}.")

        names = game["names"]
        if len(game["choices"]) < 2:
            await q.edit_message_text(
                "╭━━━〔 🪨 <b>RPS DUEL</b> 〕━━━╮\n"
                "┃ <i>Waiting for both players…</i> ✦\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"👤 {html.escape(names[game['players'][0]])}: {'✅ Selected' if game['players'][0] in game['choices'] else '⏳ Choosing…'}\n"
                f"👤 {html.escape(names[game['players'][1]])}: {'✅ Selected' if game['players'][1] in game['choices'] else '⏳ Choosing…'}\n\n"
                "🤫 Choices are hidden until both players lock in.",
                parse_mode="HTML",
                reply_markup=_rps_keyboard(gid),
            )
            return

        p1, p2 = game["players"]
        c1, c2 = game["choices"][p1], game["choices"][p2]
        result = _winner(c1, c2)

        # Consume the room before awarding so duplicate callback deliveries
        # cannot pay the same result twice.
        RPS_GAMES.pop(gid, None)

        if result == 0:
            reward = 25
            await add_coins(p1, reward)
            await add_coins(p2, reward)
            await record_game_result(p1, "RPS", reward, False, game["chat_id"])
            await record_game_result(p2, "RPS", reward, False, game["chat_id"])
            result_text = (
                "🤝 <b>DRAW!</b>\n\n"
                f"👤 <b>{html.escape(names[p1])}</b> — {_choice_label(c1)}\n"
                f"👤 <b>{html.escape(names[p2])}</b> — {_choice_label(c2)}\n\n"
                f"💰 Both players: +{reward} coins • 🏆 +{reward} points"
            )
        else:
            winner_uid = p1 if result == 1 else p2
            loser_uid = p2 if result == 1 else p1
            await add_coins(winner_uid, 100)
            await record_game_result(winner_uid, "RPS", 100, True, game["chat_id"])
            await record_game_result(loser_uid, "RPS", 0, False, game["chat_id"])
            result_text = (
                "🏆🏆🏆 <b>WINNER</b> 🏆🏆🏆\n"
                f"👑 <b>{html.escape(names[winner_uid])}</b> <b>WINS!</b>\n\n"
                f"✅ Winning move: <b>{_choice_label(game['choices'][winner_uid])}</b>\n"
                f"❌ {html.escape(names[loser_uid])}: {_choice_label(game['choices'][loser_uid])}\n\n"
                "💰 <b>Winner reward: +100 coins</b>\n"
                "🏆 <b>Leaderboard: +100 points</b>"
            )

        await q.edit_message_text(
            "╭━━━〔 🪨 <b>RPS DUEL RESULT</b> 〕━━━╮\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯\n\n" + result_text,
            parse_mode="HTML",
        )
