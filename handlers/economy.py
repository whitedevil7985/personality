"""Modular handler module for ItzVanyaBot Ultimate.

The entrypoint owns shared runtime state; this module only owns the handlers
listed below. The bridge keeps the current runtime namespace shared during the
migration so existing behavior is preserved.
"""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

async def toprich(update, context):
    """Show the richest users by current coin balance."""
    await ensure_user(update.effective_user)
    rows = []
    cursor = users.find({}, {"_id": 1, "name": 1, "coins": 1}).sort("coins", -1).limit(10)
    async for u in cursor:
        rows.append(u)

    medals = ["🥇", "🥈", "🥉"]
    lines = [
        "╭━━━〔 💰 <b>TOP RICH</b> 〕━━━╮",
        "┃ <i>Richest Vanya players</i>",
        "╰━━━━━━━━━━━━━━━━━━━━╯",
        "",
    ]

    if not rows:
        lines.append("💸 No players found yet.")
    else:
        for index, user in enumerate(rows, 1):
            medal = medals[index - 1] if index <= 3 else f"<b>{index}.</b>"
            name = html.escape(str(user.get("name") or "User"))
            coins = int(user.get("coins", 0) or 0)
            lines.append(f"{medal} <b>{name}</b> — 💰 <b>{coins:,}</b> coins")

    lines.extend(["", "💎 All game winnings and other Vanya coin rewards are included in this balance."])
    await update.message.reply_html("\n".join(lines))

async def balance(update, context):
    target = await target_user(update) if update.message and update.message.reply_to_message else None
    target = target or update.effective_user
    if not target:
        return
    await ensure_user(target)
    u = await get_user(target.id)
    name = html.escape(u.get("name") or target.first_name or "User")
    status = "💀 Dead" if u.get("dead") else "🟢 Alive"
    await update.message.reply_html(
        f"👤 <b>{name}</b>\n"
        f"💰 Coins: <b>{u.get('coins',0):,}</b>\n"
        f"⭐ XP: <b>{u.get('xp',0):,}</b>\n"
        f"🏆 Level: <b>{u.get('level',1)}</b>\n"
        f"❤️ Status: <b>{status}</b>"
    )

async def daily(update, context):
    await ensure_user(update.effective_user)
    u=await get_user(update.effective_user.id)
    now=datetime.now(timezone.utc)
    last=u.get("daily")
    if last:
        try:
            if now-datetime.fromisoformat(last)<timedelta(hours=24):
                await update.message.reply_text("⏳ Daily already claimed. Come back later.")
                return
        except: pass
    reward=random.randint(250,750)
    await add_coins(update.effective_user.id,reward); await add_xp(update.effective_user.id,50)
    await users.update_one({"_id":update.effective_user.id},{"$set":{"daily":now.isoformat()}})
    await update.message.reply_text(f"🎁 Daily reward: +{reward:,} coins\n⭐ +50 XP")

async def work(update, context):
    await ensure_user(update.effective_user)
    reward=random.randint(80,300)
    jobs=["debugged a bot","delivered a pizza","won a coding gig","found a lucky coin","finished a quest"]
    await add_coins(update.effective_user.id,reward);await add_xp(update.effective_user.id,20)
    await update.message.reply_text(f"💼 You {random.choice(jobs)}.\n💰 +{reward} coins • ⭐ +20 XP")

LEADERBOARD_GAMES = [
    ("All games", "ALL"), ("UNO", "UNO"), ("Ludo", "LUDO"), ("Chess", "CHESS"),
    ("RPS", "RPS"), ("Mines", "MINES"), ("Slots", "SLOTS"), ("Bet", "BET"),
    ("Tap", "TAP"), ("Wordgrid", "WORDGRID"), ("Wordseek", "WORDSEEK"),
    ("Dice", "DICE"), ("Coinflip", "COINFLIP"), ("Card", "CARD"),
    ("Jumble", "JUMBLE"), ("Wordchain", "WORDCHAIN"), ("Wordscramble", "WORDS"),
    ("Crash", "CRASH"), ("Charades", "CHARADES"), ("Hack", "HACK"), ("Scribble", "SCRIBBLE"), ("Kingdom Wars", "KINGDOMWARS"),
]

def _leaderboard_since(period):
    now = datetime.now(timezone.utc)
    p = str(period).lower()
    if p == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if p == "week":
        return now - timedelta(days=7)
    return now - timedelta(days=30)

def _leaderboard_label(options, key, fallback):
    return next((label for label, value in options if value == key), fallback)

def leaderboard_kb(period="today", scope="global", game="ALL", picker=False):
    period = period if period in ("today", "week", "month") else "today"
    scope = scope if scope in ("global", "group") else "global"
    game = game.upper()
    if picker:
        rows = []
        for i in range(0, len(LEADERBOARD_GAMES), 2):
            pair = LEADERBOARD_GAMES[i:i+2]
            rows.append([
                InlineKeyboardButton(
                    ("✅ " if value == game else "") + label,
                    callback_data=f"lb|g|{period}|{scope}|{value}"
                )
                for label, value in pair
            ])
        rows.append([InlineKeyboardButton("⟵ Back", callback_data=f"lb|v|{period}|{scope}|{game}")])
        return kb(rows)
    return kb([
        [
            InlineKeyboardButton("☀️ Today" + (" ✓" if period == "today" else ""), callback_data=f"lb|p|today|{scope}|{game}"),
            InlineKeyboardButton("🗓 Week" + (" ✓" if period == "week" else ""), callback_data=f"lb|p|week|{scope}|{game}"),
            InlineKeyboardButton("🌙 Month" + (" ✓" if period == "month" else ""), callback_data=f"lb|p|month|{scope}|{game}"),
        ],
        [
            InlineKeyboardButton("🌍 Global" + (" ✓" if scope == "global" else ""), callback_data=f"lb|s|{period}|global|{game}"),
            InlineKeyboardButton("🏠 Group" + (" ✓" if scope == "group" else ""), callback_data=f"lb|s|{period}|group|{game}"),
        ],
        [InlineKeyboardButton(f"🎮 Game: {_leaderboard_label(LEADERBOARD_GAMES, game, 'All games')} ▼", callback_data=f"lb|menu|{period}|{scope}|{game}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"lb|v|{period}|{scope}|{game}")],
        [InlineKeyboardButton("⌂ Home", callback_data="home")],
    ])

async def _render_leaderboard(update_or_query, context, period="today", scope="global", game="ALL"):
    is_query = hasattr(update_or_query, "edit_message_text")
    query = update_or_query if is_query else None
    update = None if is_query else update_or_query
    chat = query.message.chat if query and query.message else update.effective_chat
    chat_id = chat.id if chat else None
    if scope == "group" and (not chat or chat.type == "private"):
        message = "🏠 <b>Group leaderboard</b> group chat ke andar open karo."
        markup = leaderboard_kb(period, "global", game)
        if query:
            await query.edit_message_text(message, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_html(message, reply_markup=markup)
        return

    rows = await get_game_leaderboard(
        game=game,
        scope=scope,
        chat_id=chat_id if scope == "group" else None,
        since=_leaderboard_since(period),
        limit=10,
    )
    title = "🏆 <b>Vanya Games Leaderboard</b>"
    group_name = html.escape(getattr(chat, "title", "") or "This group") if scope == "group" else "Global"
    period_name = {"today": "Today", "week": "Week", "month": "Month"}[period]
    game_name = _leaderboard_label(LEADERBOARD_GAMES, game, "All games")
    lines = [
        title,
        f"<i>Scope: {group_name}  |  Period: {period_name}</i>",
        "",
    ]
    if rows:
        for i, row in enumerate(rows, 1):
            lines.append(
                f"{i}. {html.escape(str(row['name']))} - "
                f"{row['points']:,} Points ({row['wins']} Wins)"
            )
    else:
        lines.append("🎮 No completed results for this filter yet.")
    lines.extend(["", f"🎮 <b>Game: {html.escape(game_name)}</b>"])
    text_value = "\n".join(lines)
    markup = leaderboard_kb(period, scope, game)
    if query:
        await query.edit_message_text(text_value, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_html(text_value, reply_markup=markup)

async def leaderboard(update, context):
    await _render_leaderboard(update, context, "today", "global", "ALL")

async def give(update, context):
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user: /give 100")
        return
    try: amount=int(context.args[0])
    except: await update.message.reply_text("Usage: /give &lt;amount&gt;");return
    if amount<=0: return
    sender=await get_user(update.effective_user.id); receiver=update.message.reply_to_message.from_user
    if sender.get("coins",0)<amount: await update.message.reply_text("❌ Not enough coins.");return
    await add_coins(update.effective_user.id,-amount);await add_coins(receiver.id,amount)
    await update.message.reply_text(f"💸 Sent {amount:,} coins to {receiver.first_name}.")

# ───────────────────── action/romance ─────────────────────

async def target_user(update):
    if update.message.reply_to_message: return update.message.reply_to_message.from_user
    return None

def _protection_until(user_doc):
    value = user_doc.get("protected_until") if user_doc else None
    if not value:
        return None
    try:
        until = datetime.fromisoformat(str(value))
        if until <= datetime.now(timezone.utc):
            return None
        return until
    except Exception:
        return None


def _is_dead(user_doc):
    return bool(user_doc and user_doc.get("dead"))


async def rob(update,context):
    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to someone: /rob [amount]")
        return

    thief = await get_user(update.effective_user.id)
    victim = await get_user(target.id)
    if not thief:
        await ensure_user(update.effective_user)
        thief = await get_user(update.effective_user.id)
    if not victim:
        await ensure_user(target)
        victim = await get_user(target.id)

    if _is_dead(thief):
        await update.message.reply_text("💀 You're dead. Use /revive first.")
        return

    protected_until = _protection_until(victim)
    if protected_until:
        await update.message.reply_text("🛡️ Target is protected. You can't rob them right now.")
        return

    if _is_dead(victim):
        await update.message.reply_text("💀 Target is dead. You can't rob them until they revive.")
        return

    if thief.get("coins", 0) < 100:
        await update.message.reply_text("❌ You need at least 100 coins to rob.")
        return

    victim_coins = max(0, int(victim.get("coins", 0)))
    if victim_coins <= 0:
        await update.message.reply_text("💸 Target has no coins to rob.")
        return

    # /rob [amount] lets the robber choose an amount, capped at the target's
    # current balance. Without an amount, rob half of the target's balance.
    try:
        amount = int(context.args[0]) if context.args else max(1, victim_coins // 2)
    except Exception:
        await update.message.reply_text("Usage: /rob [amount]")
        return
    amount = min(max(1, amount), victim_coins)

    if random.random() < 0.45:
        await add_coins(target.id, -amount)
        await add_coins(update.effective_user.id, amount)
        await update.message.reply_text(f"🕵️ Rob successful! +{amount:,} coins.")
    else:
        fine = min(100, int(thief.get("coins", 0)))
        await add_coins(update.effective_user.id, -fine)
        await update.message.reply_text(f"🚨 Caught! You lost {fine:,} coins.")


async def protect(update,context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)
    now = datetime.now(timezone.utc)
    existing = _protection_until(u)
    if existing:
        remaining = existing - now
        hours = max(1, int(remaining.total_seconds() // 3600))
        mins = int((remaining.total_seconds() % 3600) // 60)
        await update.message.reply_text(
            f"🛡️ Protection already active for {hours}h {mins}m. Use /shield to check it."
        )
        return

    duration_arg = (context.args[0].lower().strip() if context.args else "")
    plans = {
        "1d": (timedelta(days=1), 500),
        "2d": (timedelta(days=2), 900),
        "1day": (timedelta(days=1), 500),
        "2days": (timedelta(days=2), 900),
    }
    duration, price = plans.get(duration_arg, (None, None))
    if duration is None:
        await update.message.reply_text(
            "🛡️ <b>Protection Plans</b>\n\n"
            "• <code>/protect 1d</code> — 1 day • 💰 500 coins\n"
            "• <code>/protect 2d</code> — 2 days • 💰 900 coins\n\n"
            "Use /shield to see remaining protection time.",
            parse_mode="HTML",
        )
        return

    if int(u.get("coins", 0)) < price:
        await update.message.reply_text(
            f"❌ You need {price:,} coins for {duration_arg} protection."
        )
        return

    until = now + duration
    await add_coins(update.effective_user.id, -price)
    await users.update_one(
        {"_id": update.effective_user.id},
        {"$set": {"protected_until": until.isoformat()}},
    )
    await update.message.reply_text(
        f"🛡️ <b>Protection activated!</b>\n"
        f"⏱️ Duration: <b>{duration_arg}</b>\n"
        f"💰 Cost: <b>{price:,} coins</b>\n"
        "🔒 You cannot be robbed while it is active.\n"
        "Use /shield anytime to check the timer.",
        parse_mode="HTML",
    )


async def shield(update,context):
    await ensure_user(update.effective_user)
    u = await get_user(update.effective_user.id)
    until = _protection_until(u)
    if not until:
        if u.get("protected_until"):
            await users.update_one(
                {"_id": update.effective_user.id},
                {"$set": {"protected_until": None}},
            )
        await update.message.reply_text("🛡️ Protection inactive. You are not protected right now.")
        return

    remaining = until - datetime.now(timezone.utc)
    total_seconds = max(0, int(remaining.total_seconds()))
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")

    await update.message.reply_html(
        "🛡️ <b>Protection Status</b>\n\n"
        "🔒 Status: <b>ACTIVE</b>\n"
        f"⏳ Remaining: <b>{' '.join(parts)}</b>\n"
        f"🕒 Expires: <b>{until.strftime('%d %b %Y, %I:%M %p UTC')}</b>\n\n"
        "🕵️ Rob attempts on you will be blocked until expiry."
    )


async def propose(update,context):
    target=await target_user(update)
    if not target:
        await update.message.reply_text("Reply to someone with /propose 💌")
        return
    if not update.effective_user:
        return

    await ensure_user(target)
    await ensure_user(update.effective_user)
    me=await get_user(update.effective_user.id)
    target_user_doc=await get_user(target.id)

    if target.id == update.effective_user.id:
        await update.message.reply_text("😅 Khud ko propose nahi kar sakte!")
        return
    if getattr(target, "is_bot", False):
        await update.message.reply_text("🤖 Bots ko proposal nahi bhej sakte.")
        return
    if me.get("partner"):
        await update.message.reply_text("💕 You're already married.")
        return
    if target_user_doc and target_user_doc.get("partner"):
        await update.message.reply_text(
            f"💕 {html.escape(target.first_name or 'They')} is already in a relationship."
        )
        return
    if target_user_doc and target_user_doc.get("pending_proposal"):
        await update.message.reply_text(
            f"💌 {html.escape(target.first_name or 'They')} already has a pending proposal."
        )
        return

    proposer_name = html.escape(update.effective_user.first_name or "Someone")
    target_name = html.escape(target.first_name or "there")
    await users.update_one(
        {"_id":target.id},
        {"$set":{"pending_proposal":update.effective_user.id}},
    )

    await update.message.reply_html(
        "╭━━━〔 💌 <b>LOVE PROPOSAL</b> 〕━━━╮\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f'💖 <a href="tg://user?id={update.effective_user.id}"><b>{proposer_name}</b></a> '
        f'has a special question for <a href="tg://user?id={target.id}"><b>{target_name}</b></a>…\n\n'
        "💍 <b>Will you be my partner?</b>\n"
        "✨ One little choice could change your status here forever.\n\n"
        "👇 <b>Choose your answer:</b>",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💖 Accept", callback_data=f"proposal:accept:{target.id}:{update.effective_user.id}"),
                InlineKeyboardButton("💔 Reject", callback_data=f"proposal:reject:{target.id}:{update.effective_user.id}"),
            ]
        ]),
    )

async def _complete_proposal_callback(q, context, action, target_id, proposer_id):
    if q.from_user.id != target_id:
        await q.answer("This proposal is only for the recipient. 💌", show_alert=True)
        return

    target_doc=await get_user(target_id)
    if not target_doc or int(target_doc.get("pending_proposal") or 0) != proposer_id:
        await q.answer("This proposal is no longer active.", show_alert=True)
        return

    proposer_doc=await get_user(proposer_id)
    if action == "accept":
        if target_doc.get("partner") or (proposer_doc and proposer_doc.get("partner")):
            await users.update_one({"_id":target_id},{"$unset":{"pending_proposal":""}})
            await q.edit_message_text(
                "💔 <b>Proposal expired</b>\n\nOne of you is already partnered.",
                parse_mode="HTML",
            )
            return

        await users.update_one(
            {"_id":target_id},
            {"$set":{"partner":proposer_id},"$unset":{"pending_proposal":""}},
        )
        await users.update_one(
            {"_id":proposer_id},
            {"$set":{"partner":target_id}},
        )

        target_name=html.escape(target_doc.get("name") or "Player")
        proposer_name=html.escape((proposer_doc or {}).get("name") or "Player")
        await q.edit_message_text(
            "╭━━━〔 💞 <b>PROPOSAL ACCEPTED</b> 〕━━━╮\n"
            "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"💍 <b>{proposer_name}</b> ❤️ <b>{target_name}</b>\n\n"
            "🎉 Congratulations! You're officially partners now.\n"
            "✨ Wishing you both lots of happy moments!",
            parse_mode="HTML",
        )
        try:
            await context.bot.send_message(
                chat_id=proposer_id,
                text=(
                    f"💞 <b>{target_name}</b> accepted your proposal!\n\n"
                    f"🎉 You and <b>{target_name}</b> are now partners."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        await q.answer("Proposal accepted! 💞")
        return

    await users.update_one({"_id":target_id},{"$unset":{"pending_proposal":""}})
    target_name=html.escape(target_doc.get("name") or "Player")
    proposer_name=html.escape((proposer_doc or {}).get("name") or "Player")
    await q.edit_message_text(
        "╭━━━〔 💔 <b>PROPOSAL DECLINED</b> 〕━━━╮\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"<b>{target_name}</b> has declined <b>{proposer_name}</b>'s proposal.\n\n"
        "🌷 No hard feelings — maybe next time!",
        parse_mode="HTML",
    )
    try:
        await context.bot.send_message(
            chat_id=proposer_id,
            text=(
                f"💔 <b>{target_name}</b> declined your proposal.\n\n"
                "🌷 No hard feelings."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
    await q.answer("Proposal declined 💔")

async def accept(update,context):
    u=await get_user(update.effective_user.id)
    proposer=u.get("pending_proposal") if u else None
    if not proposer:
        await update.message.reply_text("No pending proposal.")
        return
    await users.update_one({"_id":update.effective_user.id},{"$set":{"partner":proposer},"$unset":{"pending_proposal":""}})
    await users.update_one({"_id":proposer},{"$set":{"partner":update.effective_user.id}})
    await update.message.reply_text("💞 Married! Congratulations!")

async def divorce(update,context):
    u=await get_user(update.effective_user.id);p=u.get("partner")
    if not p: await update.message.reply_text("You're single.");return
    await users.update_one({"_id":update.effective_user.id},{"$set":{"partner":None}})
    await users.update_one({"_id":p},{"$set":{"partner":None}})
    await update.message.reply_text("💔 Divorce completed.")

async def couple(update, context):
    """Pair actual group participants, not just administrators.

    Participants are collected whenever the bot sees a user's group message.
    Replying to a user with /couple pairs the requester with that user.
    """
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.message.reply_text("💕 /couple works inside a group. Add Vanya to a group first.")
        return

    me = update.effective_user
    if not me:
        return
    await ensure_user(me)

    # Best UX: /couple as a reply pairs the two participants directly.
    replied = await target_user(update)
    if replied and not replied.is_bot and replied.id != me.id:
        await ensure_user(replied)
        a, b = me, replied
    else:
        # Prefer users who have actually spoken in this group.
        docs = users.find({
            "group_ids": chat.id,
            "_id": {"$ne": me.id},
            "is_bot": {"$ne": True},
        }).limit(100)
        candidates = []
        async for u in docs:
            candidates.append({
                "id": u["_id"],
                "first_name": u.get("name") or "Player",
                "username": u.get("username"),
            })

        if not candidates:
            await update.message.reply_text(
                "💕 Abhi enough active players nahi mile. Group me thodi der baat hone do, phir /couple try karo."
            )
            return

        # Make each /couple call produce a NEW pairing for the requester
        # until every available participant has been paired once. Then the
        # cycle starts over. Pair history is stored per group.
        group_doc = await groups.find_one({"_id": chat.id}) or {}
        history = group_doc.get("couple_pairs", []) or []
        used_for_me = set()
        for item in history:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                x, y = int(item[0]), int(item[1])
                if x == me.id:
                    used_for_me.add(y)
                elif y == me.id:
                    used_for_me.add(x)

        fresh = [c for c in candidates if c["id"] not in used_for_me]
        if not fresh:
            # Start a new pairing cycle for this requester once all current
            # participants have been used. Keep history bounded.
            fresh = candidates
            history = [item for item in history if not (isinstance(item, (list, tuple)) and me.id in item)]

        other = random.choice(fresh)
        a = me
        b = type("UserLite", (), other)()

        pair = sorted([int(a.id), int(b.id)])
        await groups.update_one(
            {"_id": chat.id},
            {"$set": {"couple_pairs": (history + [pair])[-500:]},
             "$setOnInsert": {"title": chat.title or "Group", "type": chat.type}},
            upsert=True,
        )

    percent = random.randint(40, 100)
    hearts = "💗" * max(1, min(5, (percent + 19) // 20))
    logo = random.choice(["💞", "💘", "💝", "💟", "💗", "💖", "💕", "❤️‍🔥"])
    await update.message.reply_html(
        f"{logo} <b>{html.escape(a.first_name or 'Player')} × {html.escape(b.first_name or 'Player')}</b> {logo}\n"
        f"{hearts} <b>Compatibility: {percent}%</b>\n\n"
        "✨ Want to make it official? Reply with <code>/propose</code> to your match!"
    )

async def topcouples(update, context):
    """Show a small list of existing couples in the current group."""
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.message.reply_text("💕 /topcouples works inside a group.")
        return
    seen = set()
    rows = []
    async for u in users.find({"group_ids": chat.id, "partner": {"$exists": True, "$ne": None}}).limit(200):
        uid = u.get("_id")
        pid = u.get("partner")
        if not pid or uid in seen or pid in seen or pid == uid:
            continue
        p = await get_user(pid)
        if not p:
            continue
        seen.add(uid); seen.add(pid)
        rows.append((u.get("name") or "Player", p.get("name") or "Player"))
        if len(rows) >= 10:
            break
    if not rows:
        await update.message.reply_text("💕 No couples yet. Try replying to someone with /propose first!")
        return
    text = "🏆 <b>Top Couples</b>\n\n" + "\n".join(
        f"{i}. 💞 {html.escape(a)} × {html.escape(b)}" for i, (a, b) in enumerate(rows, 1)
    )
    await update.message.reply_html(text)
