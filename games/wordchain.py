import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from db import ensure_user, add_coins, record_game_result

WORDCHAIN_GAMES = {}
DEFAULT_WORDCHAIN_LIMIT = 10
MAX_WORDCHAIN_PLAYERS = 8


def _text(game):
    players = game["players"]
    names = ", ".join(html.escape(game["names"].get(pid, "Player")) for pid in players)
    if not game["started"]:
        return (
            "🔗 <b>WORDCHAIN LOBBY</b>\n\n"
            f"👥 Players: <b>{len(players)}/{MAX_WORDCHAIN_PLAYERS}</b>\n"
            f"📚 Target: <b>{game['limit']} words</b>\n"
            "✅ Minimum: <b>2 players</b>\n\n"
            f"Players: {names or 'None'}\n\n"
            "<i>Tap Join. Match auto-starts when 2+ players are ready.</i>"
        )
    turn_uid = players[game["turn"] % len(players)]
    turn_name = html.escape(game["names"].get(turn_uid, "Player"))
    required = game.get("required")
    target = f"<b>{required.upper()}</b>" if required else "<b>ANY</b>"
    return (
        "🔗 <b>WORDCHAIN</b>\n\n"
        f"👥 Players: <b>{len(players)}</b>\n"
        f"📚 Progress: <b>{game['count']}/{game['limit']}</b>\n"
        f"🎯 Starts with: {target}\n"
        f"🎮 Turn: <b>{turn_name}</b>\n\n"
        "Send exactly one word."
    )


def _join_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Join Wordchain", callback_data="wordchain:join")]])


async def wordchain(update, context):
    chat_id = update.effective_chat.id
    if chat_id in WORDCHAIN_GAMES:
        game = WORDCHAIN_GAMES[chat_id]
        await update.message.reply_html(_text(game), reply_markup=_join_kb() if not game["started"] else None)
        return
    try:
        limit = max(5, min(50, int(context.args[0]))) if context.args else DEFAULT_WORDCHAIN_LIMIT
    except (TypeError, ValueError):
        await update.message.reply_text("Usage: /wordchain [5-50]")
        return
    user = update.effective_user
    await ensure_user(user)
    WORDCHAIN_GAMES[chat_id] = {
        "players": [user.id],
        "names": {user.id: user.first_name or "Player"},
        "limit": limit,
        "count": 0,
        "turn": 0,
        "required": None,
        "used": set(),
        "started": False,
    }
    await update.message.reply_html(_text(WORDCHAIN_GAMES[chat_id]), reply_markup=_join_kb())


async def wordchain_join(update, context=None):
    q = getattr(update, "callback_query", None)
    if q:
        chat_id, user, send = q.message.chat.id, q.from_user, q.message.reply_html
    else:
        chat_id, user, send = update.effective_chat.id, update.effective_user, update.message.reply_html
    game = WORDCHAIN_GAMES.get(chat_id)
    if not game:
        await send("🔗 No Wordchain lobby. Use /wordchain [5-50].")
        return
    await ensure_user(user)
    if user.id in game["players"]:
        await send(_text(game), reply_markup=_join_kb() if not game["started"] else None)
        return
    if game["started"]:
        await send("❌ This match already started.")
        return
    if len(game["players"]) >= MAX_WORDCHAIN_PLAYERS:
        await send(f"❌ Lobby full. Max {MAX_WORDCHAIN_PLAYERS} players.")
        return
    game["players"].append(user.id)
    game["names"][user.id] = user.first_name or "Player"
    if len(game["players"]) >= 2:
        game["started"] = True
        game["turn"] = 0
        await send(
            "🚀 <b>WORDCHAIN STARTED!</b>\n\n"
            f"📚 Target: <b>{game['limit']} words</b>\n"
            + _text(game)
        )
    else:
        await send(_text(game), reply_markup=_join_kb())


async def wordchain_answer(update, context):
    if not update.message or not update.message.text:
        return False
    chat_id = update.effective_chat.id if update.effective_chat else None
    game = WORDCHAIN_GAMES.get(chat_id)
    if not game or not game["started"]:
        return False

    uid = update.effective_user.id
    if uid not in game["players"]:
        return True
    if uid != game["players"][game["turn"] % len(game["players"])]:
        return True

    parts = update.message.text.strip().split()
    word = parts[0].lower() if len(parts) == 1 else ""
    if not word.isalpha() or len(word) < 2:
        await update.message.reply_text("🔗 Send one word using letters only.")
        return True
    if word in game["used"]:
        await update.message.reply_text("♻️ That word was already used.")
        return True
    required = game.get("required")
    if required and not word.startswith(required):
        await update.message.reply_html(
            f"❌ Word must start with <b>{html.escape(required.upper())}</b>."
        )
        return True

    game["used"].add(word)
    game["count"] += 1
    reward = 20
    await add_coins(uid, reward)
    await record_game_result(uid, "WORDCHAIN", reward, True, chat_id)

    if game["count"] >= game["limit"]:
        bonus = 50
        await add_coins(uid, bonus)
        await record_game_result(uid, "WORDCHAIN", bonus, True, chat_id)
        winner = html.escape(game["names"].get(uid, "Player"))
        await update.message.reply_html(
            "🏆 <b>WORDCHAIN COMPLETE!</b>\n\n"
            f"🎉 <b>{winner}</b> played word #{game['count']} and finished the match!\n"
            f"📚 <b>{game['count']}/{game['limit']}</b> words completed.\n"
            f"💰 Final bonus: <b>+{bonus} coins</b>"
        )
        WORDCHAIN_GAMES.pop(chat_id, None)
        return True

    game["required"] = word[-1]
    game["turn"] = (game["turn"] + 1) % len(game["players"])
    next_uid = game["players"][game["turn"] % len(game["players"])]
    next_name = html.escape(game["names"].get(next_uid, "Player"))
    await update.message.reply_html(
        f"✅ <b>{html.escape(word.upper())}</b> accepted! +{reward} 🪙\n"
        f"📚 Progress: <b>{game['count']}/{game['limit']}</b>\n"
        f"➡️ <b>{next_name}</b> turn — start with <b>{game['required'].upper()}</b>."
    )
    return True


async def wordchain_cb(update, context):
    await wordchain_join(update, context)
