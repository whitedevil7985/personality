"""Modular handler module for ItzVanyaBot Ultimate.

The entrypoint owns shared runtime state; this module only owns the handlers
listed below. The bridge keeps the current runtime namespace shared during the
migration so existing behavior is preserved.
"""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

# Staff command visibility is owned by this module so the entrypoint
# only needs to register handlers and build public/private command menus.
STAFF_COMMANDS = {
    "owner": "Open owner panel",
    "ownerpanel": "Open owner panel",
    "panel": "Open owner panel",
    "devpanel": "Open owner panel",
    "broadcast": "Broadcast to users, groups, or both (Owner/Sudo)",
    "addcoins": "Add coins by user ID (Owner/Sudo)",
    "removecoins": "Remove coins by user ID (Owner/Sudo)",
    "addemoji": "Save premium custom emoji (Owner only)",
    "addsudo": "Add a sudo user",
    "delsudo": "Remove a sudo user",
    "sudolist": "List sudo users",
    "auth": "Authorize this group",
    "unauth": "Unauthorize this group",
    "authlist": "List authorized groups",
    "stats": "View bot group and user statistics (Owner/Sudo only)",
    "blacklist": "Blacklist a user (Owner only)",
    "unblacklist": "Remove a user from blacklist (Owner only)",
    "log": "View recent logger events (Owner only)",
    "aistats": "View today's AI API request usage by provider (Owner only)",
    "revealgrid": "Reveal the Wordgrid answer (Owner/Sudo)",
    "revealwordseek": "Reveal the Wordseek answer (Owner/Sudo)",
}
OWNER_ONLY_COMMANDS = {
    "owner", "ownerpanel", "panel", "devpanel",
    "addemoji", "addsudo", "delsudo", "sudolist",
    "auth", "unauth", "authlist", "blacklist", "unblacklist",
    "revealgrid", "revealwordseek", "log", "aistats",
}

def staff_command_objects(owner=False):
    items = []
    for command, description in STAFF_COMMANDS.items():
        if not owner and command in OWNER_ONLY_COMMANDS:
            continue
        items.append(BotCommand(command, description))
    return items



async def aistats(update, context):
    """Owner-only daily AI provider usage report."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        await update.effective_message.reply_text("⛔ Owner only.")
        return

    try:
        limit = int((context.args or ["15"])[0])
    except (TypeError, ValueError):
        limit = 15
    limit = max(1, min(limit, 30))

    india_tz = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(india_tz).strftime("%Y-%m-%d")
    providers = ("dedicated", "elite", "chatgp", "cloudflare", "ollama")
    labels = {
        "dedicated": "Dedicated LLMs",
        "elite": "Elite LLM",
        "chatgp": "ChatGP",
        "cloudflare": "Cloudflare Workers AI",
        "ollama": "Ollama Cloud",
    }

    try:
        totals = {}
        pipeline = [
            {"$match": {"date_key": today}},
            {"$group": {"_id": "$provider", "count": {"$sum": 1}}},
        ]
        async for row in ai_usage.aggregate(pipeline):
            totals[str(row.get("_id") or "")] = int(row.get("count", 0))

        user_pipeline = [
            {"$match": {"date_key": today}},
            {"$group": {
                "_id": {"provider": "$provider", "user_id": "$user_id"},
                "count": {"$sum": 1},
                "name": {"$first": "$user_name"},
                "username": {"$first": "$username"},
            }},
            {"$sort": {"count": -1, "_id.provider": 1, "_id.user_id": 1}},
        ]
        users_by_provider = {provider: [] for provider in providers}
        async for row in ai_usage.aggregate(user_pipeline):
            provider = str((row.get("_id") or {}).get("provider") or "")
            if provider not in users_by_provider:
                users_by_provider[provider] = []
            users_by_provider[provider].append(row)

        total = sum(totals.values())
        lines = [
            "╭━━━〔 📊 <b>AI API STATS</b> 〕━━━╮",
            f"┃ 📅 <b>Today:</b> {html.escape(today)} (IST)",
            "╰━━━━━━━━━━━━━━━━━━━━╯",
            "",
        ]

        for provider in providers:
            count = totals.get(provider, 0)
            lines.append(f"🔹 <b>{html.escape(labels[provider])}</b>: <b>{count}</b> API requests")
            rows = users_by_provider.get(provider, [])[:limit]
            if rows:
                lines.append("   👤 <b>Used for:</b>")
                for row in rows:
                    uid = (row.get("_id") or {}).get("user_id")
                    name = str(row.get("name") or f"User {uid}")
                    username = str(row.get("username") or "").strip()
                    display = f"@{username}" if username else name
                    lines.append(
                        f"   • {html.escape(display)[:60]} "
                        f"<code>{int(uid or 0)}</code> × <b>{int(row.get('count', 0))}</b>"
                    )
                hidden = max(0, len(users_by_provider.get(provider, [])) - len(rows))
                if hidden:
                    lines.append(f"   … +{hidden} more users (use /aistats 30)")
            else:
                lines.append("   👤 Used for: <i>none</i>")
            lines.append("")

        lines.append(f"╭━━━〔 🧮 <b>TOTAL</b> 〕━━━╮")
        lines.append(f"┃ 💬 AI API requests today: <b>{total}</b>")
        lines.append("╰━━━━━━━━━━━━━━━━━━━━╯")
        output = "\n".join(lines)

        if len(output) > 3900:
            # Keep the summary reliable even with many recipient rows.
            output = (
                "╭━━━〔 📊 <b>AI API STATS</b> 〕━━━╮\n"
                f"┃ 📅 <b>Today:</b> {html.escape(today)} (IST)\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                + "\n".join(
                    f"🔹 <b>{html.escape(labels[p])}</b>: <b>{totals.get(p, 0)}</b> API requests"
                    for p in providers
                )
                + f"\n\n🧮 <b>Total:</b> {total} AI API requests today"
            )

        await update.effective_message.reply_html(output)
    except Exception as exc:
        print(f"[OwnerAIStats] {type(exc).__name__}: {exc}")
        await update.effective_message.reply_text("❌ AI stats database read failed.")


async def log(update, context):
    """Owner-only viewer for recent events saved by the logger."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        await update.effective_message.reply_text("⛔ Owner only.")
        return

    try:
        limit = int((context.args or ["10"])[0])
    except (TypeError, ValueError):
        limit = 10

    limit = max(1, min(limit, 20))
    rows = []
    try:
        cursor = logs.find(
            {},
            {"_id": 0, "text": 1, "created_at": 1},
        ).sort("created_at", -1).limit(limit)
        async for item in cursor:
            timestamp = item.get("created_at")
            if timestamp:
                try:
                    stamp = timestamp.astimezone(timezone.utc).strftime("%d-%m-%Y %H:%M:%S UTC")
                except Exception:
                    stamp = str(timestamp)
            else:
                stamp = "Unknown time"
            body = str(item.get("text", "")).strip()
            if body:
                rows.append(f"🕒 <b>{html.escape(stamp)}</b>\n{body}")

    except Exception as exc:
        print(f"[OwnerLog] {type(exc).__name__}: {exc}")
        await update.effective_message.reply_text("❌ Logger database read failed.")
        return

    if not rows:
        await update.effective_message.reply_text(
            "📋 Logger empty. Abhi koi saved event nahi hai."
        )
        return

    # Telegram messages have a 4096-character limit. Keep the newest entries
    # and trim each entry so /log remains reliable even for large events.
    output = "╭━━━〔 📋 LOGGER LOGS 〕━━━╮\n╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
    for row in rows:
        chunk = row[:900]
        candidate = output + chunk + "\n\n"
        if len(candidate) > 3900:
            break
        output = candidate

    output += f"\nShowing latest <b>{min(limit, len(rows))}</b> events."
    try:
        await update.effective_message.reply_html(output)
    except Exception as exc:
        print(f"[OwnerLogRender] {type(exc).__name__}: {exc}")
        await update.effective_message.reply_text(
            "📋 Logs mil gaye, lekin Telegram message render nahi kar saka."
        )

async def is_owner_or_sudo(update):
    uid = update.effective_user.id if update.effective_user else 0
    if uid == OWNER_ID or uid in SUDO_IDS:
        return True
    u = await get_user(uid)
    return bool(u and u.get("is_sudo"))


async def broadcast_target_kb():
    return kb([
        [InlineKeyboardButton("👤 Users Only", callback_data="owner:broadcastmode:users")],
        [InlineKeyboardButton("💬 Groups Only", callback_data="owner:broadcastmode:groups")],
        [InlineKeyboardButton("🌐 Users + Groups", callback_data="owner:broadcastmode:both")],
        [InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")],
    ])


def owner_panel_kb(owner_only=False, staff_access=False):
    """Polished dashboard and category menus for Owner/Sudo controls."""
    return kb([
        [
            InlineKeyboardButton("📡 Monitoring", callback_data="owner:monitor"),
            InlineKeyboardButton("🛠 Management", callback_data="owner:manage"),
        ],
        [
            InlineKeyboardButton("💰 Economy", callback_data="owner:economy"),
            InlineKeyboardButton("🎮 Game Tools", callback_data="owner:games"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="owner:broadcast"),
            InlineKeyboardButton("🧾 Commands", callback_data="owner:commands"),
        ],
        [InlineKeyboardButton("👑 User Access", callback_data="owner:users")],
        [InlineKeyboardButton("❌ Close Panel", callback_data="owner:close")],
    ])


def owner_monitor_kb():
    return kb([
        [
            InlineKeyboardButton("📊 AI API Stats", callback_data="owner:aistats"),
            InlineKeyboardButton("📈 Bot Stats", callback_data="owner:stats"),
        ],
        [InlineKeyboardButton("📋 Logger", callback_data="owner:log")],
        [InlineKeyboardButton("⟵ Dashboard", callback_data="owner:home")],
    ])


def owner_manage_kb(owner_only=False):
    rows = [
        [InlineKeyboardButton("📢 Broadcast Center", callback_data="owner:broadcast")],
        [
            InlineKeyboardButton("🔐 Auth Groups", callback_data="owner:auth"),
            InlineKeyboardButton("👑 Sudo Users", callback_data="owner:sudo"),
        ],
        [InlineKeyboardButton("⟵ Dashboard", callback_data="owner:home")],
    ]
    if owner_only:
        rows.insert(1, [
            InlineKeyboardButton("➕ Add Sudo", callback_data="owner:addsudo"),
            InlineKeyboardButton("➖ Del Sudo", callback_data="owner:delsudo"),
        ])
    return kb(rows)


def owner_economy_kb():
    return kb([
        [InlineKeyboardButton("💰 Coin Control", callback_data="owner:coins")],
        [InlineKeyboardButton("⟵ Dashboard", callback_data="owner:home")],
    ])


def owner_games_kb():
    return kb([
        [
            InlineKeyboardButton("🔐 Wordgrid Answer", callback_data="owner:revealgrid"),
            InlineKeyboardButton("🔎 Wordseek Answer", callback_data="owner:revealwordseek"),
        ],
        [InlineKeyboardButton("⟵ Dashboard", callback_data="owner:home")],
    ])


def owner_users_kb(owner_only=False):
    rows = [
        [
            InlineKeyboardButton("👑 Sudo Users", callback_data="owner:sudo"),
            InlineKeyboardButton("🔐 Auth Groups", callback_data="owner:auth"),
        ],
        [InlineKeyboardButton("⟵ Dashboard", callback_data="owner:home")],
    ]
    if owner_only:
        rows.insert(0, [
            InlineKeyboardButton("🚫 Blacklist", callback_data="owner:blacklist"),
            InlineKeyboardButton("🎨 Premium Emoji", callback_data="owner:addemoji"),
        ])
    return kb(rows)


async def owner_panel(update, context):
    """Private dashboard-style Owner/Sudo control center."""
    if not update.effective_user:
        return
    if not await is_owner_or_sudo(update):
        await update.effective_message.reply_text("⛔ Owner/Sudo only.")
        return

    owner_only = update.effective_user.id == OWNER_ID
    role = "OWNER" if owner_only else "SUDO"
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
    try:
        total_users = await users.count_documents({})
        total_groups = await groups.count_documents({})
        active_groups = await groups.count_documents({"active": {"$ne": False}})
        today_ai = await ai_usage.count_documents({"date_key": today})
    except Exception as exc:
        print(f"[OwnerDashboardStats] {type(exc).__name__}: {exc}")
        total_users = total_groups = active_groups = today_ai = 0

    panel_text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "│ 👑 <b>VANYA CONTROL CENTER</b>\n"
        "│ 🔒 Access: <b>" + role + "</b>\n"
        "│ 🟢 Status: <b>ONLINE</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "┌─ <b>LIVE OVERVIEW</b> ─┐\n"
        f"│ 👤 Users: <b>{total_users:,}</b>\n"
        f"│ 💬 Active Groups: <b>{active_groups:,}</b>\n"
        f"│ 🗂 Known Groups: <b>{total_groups:,}</b>\n"
        f"│ 🤖 AI API Requests Today: <b>{today_ai:,}</b>\n"
        "└─────────────────────────┘\n\n"
        "📡 <b>Monitor</b> · health, stats & logs\n"
        "🛠 <b>Manage</b> · broadcast & access controls\n"
        "💰 <b>Economy</b> · coins & balance tools\n"
        "🎮 <b>Game Tools</b> · private answer controls\n\n"
        "👇 <b>Select a section</b>"
    )

    try:
        await update.effective_message.reply_html(
            panel_text,
            reply_markup=owner_panel_kb(
                owner_only=owner_only,
                staff_access=True,
            ),
        )
    except Exception as exc:
        print(f"[OwnerPanelRender] {type(exc).__name__}: {exc}")
        await update.effective_message.reply_html(panel_text)


async def owner_panel_command(update, context):
    """Dedicated Owner/Sudo entrypoint for /owner, /panel and aliases."""
    if not update.effective_message or not update.effective_user:
        return
    try:
        allowed = await is_owner_or_sudo(update)
    except Exception as exc:
        print(f"[OwnerPanelCommand] auth error: {type(exc).__name__}: {exc}")
        allowed = False

    if not allowed:
        await update.effective_message.reply_text(
            "⛔ Owner/Sudo only."
        )
        return

    try:
        # Call the renderer after the permission check. Keeping this separate
        # from the command registration makes /owner robust against any stale
        # handler references after a deployment.
        await owner_panel(update, context)
    except Exception as exc:
        print(f"[OwnerPanelCommand] render error: {type(exc).__name__}: {exc}")
        await update.effective_message.reply_html(
            "👑 <b>Vanya Owner Panel</b>\n\n"
            "✅ Access confirmed.\n"
            "Use /broadcast, /addcoins, /removecoins, /revealgrid or /revealwordseek."
        )


async def _coin_admin_target(update, context, remove=False):
    """Owner/Sudo utility for adjusting any user's virtual coin balance by ID."""
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return

    command = "removecoins" if remove else "addcoins"
    if len(context.args) < 2:
        await update.message.reply_html(
            f"Usage: <code>/{command} &lt;user_id&gt; &lt;amount&gt;</code>\n"
            f"Example: <code>/{command} 123456789 500</code>"
        )
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (TypeError, ValueError):
        await update.message.reply_text("⚠️ User ID aur amount number mein do.")
        return

    if target_id <= 0 or amount <= 0:
        await update.message.reply_text("⚠️ User ID aur amount 0 se zyada hona chahiye.")
        return

    target = await get_user(target_id)
    if not target:
        await users.update_one(
            {"_id": target_id},
            {"$setOnInsert": {
                "name": f"User {target_id}",
                "coins": 0,
                "xp": 0,
                "level": 1,
                "warnings": 0,
                "partner": None,
                "pending_proposal": None,
                "chat_history": [],
                "memory": [],
                "memories": [],
                "is_sudo": False,
            }},
            upsert=True,
        )
        target = await get_user(target_id)

    current = int((target or {}).get("coins", 0) or 0)

    if remove:
        actual = min(amount, max(0, current))
        if actual <= 0:
            await update.message.reply_text(
                f"💰 User <code>{target_id}</code> ke paas remove karne ke liye coins nahi hain.",
                parse_mode="HTML",
            )
            return
        await add_coins(target_id, -actual)
        new_balance = current - actual
        action_text = f"removed <b>{actual:,}</b> coins"
    else:
        actual = amount
        await add_coins(target_id, actual)
        new_balance = current + actual
        action_text = f"added <b>{actual:,}</b> coins"

    name = html.escape(str((target or {}).get("name") or f"User {target_id}"))
    await update.message.reply_html(
        "╭━━━〔 💰 <b>COIN CONTROL</b> 〕━━━╮\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👤 <b>{name}</b>\n"
        f"🆔 <code>{target_id}</code>\n"
        f"✅ {action_text}\n"
        f"💰 New balance: <b>{new_balance:,}</b> coins"
    )


async def addcoins_admin(update, context):
    await _coin_admin_target(update, context, remove=False)


async def removecoins_admin(update, context):
    await _coin_admin_target(update, context, remove=True)


async def broadcast(update, context):
    """Broadcast a text/media message to users, groups, or both. Owner/Sudo only."""
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return

    user_id = update.effective_user.id if update.effective_user else 0
    app_data = context.application.bot_data if context.application else {}
    broadcast_modes = app_data.setdefault("broadcast_modes", {})

    source = update.message.reply_to_message
    args = list(context.args or [])
    mode = None

    # Optional direct mode:
    # /broadcast users Your message
    # /broadcast groups Your message
    # /broadcast both Your message
    if args and str(args[0]).lower() in {"users", "user", "groups", "group", "chats", "chat", "both"}:
        raw_mode = str(args.pop(0)).lower()
        mode = "users" if raw_mode in {"users", "user"} else "groups" if raw_mode in {"groups", "group", "chats", "chat"} else "both"
        broadcast_modes[user_id] = mode
    else:
        mode = broadcast_modes.get(user_id)

    text = " ".join(args).strip()

    if not source and not text:
        await update.message.reply_html(
            "📢 <b>Broadcast Center</b>\n\n"
            "Choose the target first:\n\n"
            "👤 <b>Users Only</b> — private users who started Vanya\n"
            "💬 <b>Groups Only</b> — groups known to Vanya\n"
            "🌐 <b>Users + Groups</b> — both\n\n"
            "You can also use directly:\n"
            "<code>/broadcast users Your message</code>\n"
            "<code>/broadcast groups Your message</code>\n"
            "<code>/broadcast both Your message</code>\n\n"
            "For media, choose a target and then reply to the media with <code>/broadcast</code>."
            ,
            reply_markup=broadcast_target_kb(),
        )
        return

    if mode not in {"users", "groups", "both"}:
        await update.message.reply_html(
            "📢 <b>Select a broadcast target first.</b>\n\n"
            "👤 Users Only\n"
            "💬 Groups Only\n"
            "🌐 Users + Groups",
            reply_markup=broadcast_target_kb(),
        )
        return

    targets = []
    user_count = 0
    group_count = 0

    if mode in {"users", "both"}:
        async for u in users.find({"started": True}, {"_id": 1}):
            targets.append(u["_id"])
            user_count += 1

    if mode in {"groups", "both"}:
        # Only target groups that are currently marked active. Old database
        # entries can remain after the bot is removed from a group.
        async for g in groups.find(
            {"$or": [{"active": True}, {"active": {"$exists": False}}]},
            {"_id": 1},
        ):
            targets.append(g["_id"])
            group_count += 1

    # De-duplicate while preserving order.
    targets = list(dict.fromkeys(targets))
    # The selected mode is consumed after a real broadcast starts so the next
    # broadcast requires an explicit target again unless the command includes one.
    broadcast_modes.pop(user_id, None)

    if not targets:
        await update.message.reply_text(
            f"📢 No targets found for the selected broadcast mode: {mode}."
        )
        return

    mode_label = {
        "users": "👤 Users Only",
        "groups": "💬 Groups Only",
        "both": "🌐 Users + Groups",
    }[mode]

    status = await update.message.reply_text(
        f"📢 <b>Broadcast started</b>\n\n"
        f"🎯 Target: <b>{mode_label}</b>\n"
        f"👤 Users: <b>{user_count:,}</b>\n"
        f"💬 Groups: <b>{group_count:,}</b>\n"
        f"📨 Total targets: <b>{len(targets):,}</b>",
        parse_mode="HTML",
    )

    sent = failed = 0
    skipped = 0
    failure_reasons = {}

    for chat_id in targets:
        delivered = False
        last_error = None

        # Telegram can temporarily return 429 during a larger broadcast.
        # Retry that target instead of counting it as a permanent failure.
        for attempt in range(3):
            try:
                if source:
                    await context.bot.copy_message(
                        chat_id=chat_id,
                        from_chat_id=source.chat_id,
                        message_id=source.message_id,
                    )
                else:
                    await context.bot.send_message(chat_id=chat_id, text=text)
                delivered = True
                break
            except Exception as exc:
                last_error = exc

                # python-telegram-bot RetryAfter exposes retry_after.
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is not None and attempt < 2:
                    try:
                        delay = max(1.0, min(float(retry_after), 30.0))
                    except (TypeError, ValueError):
                        delay = 2.0
                    await asyncio.sleep(delay)
                    continue

                break

        if delivered:
            sent += 1
            await asyncio.sleep(0.08)
        else:
            failed += 1
            reason = str(last_error or "Unknown error")
            reason_lower = reason.lower()

            # These generally mean the bot can no longer deliver to this
            # group. Mark it inactive so future broadcasts skip it.
            permanent_group_error = (
                chat_id < 0 and (
                    "forbidden" in reason_lower
                    or "bot was kicked" in reason_lower
                    or "bot is not a member" in reason_lower
                    or "chat not found" in reason_lower
                    or "kicked" in reason_lower
                )
            )
            if permanent_group_error:
                try:
                    await groups.update_one(
                        {"_id": chat_id},
                        {"$set": {
                            "active": False,
                            "broadcast_failed_at": datetime.now(timezone.utc),
                            "broadcast_failure": reason[:500],
                        }},
                    )
                except Exception as db_exc:
                    print(f"[Broadcast] failed to mark inactive {chat_id}: {db_exc}")

            # Keep a compact reason summary for the owner.
            reason_key = (
                "Bot removed/blocked"
                if permanent_group_error else
                "Rate limit"
                if getattr(last_error, "retry_after", None) is not None else
                type(last_error).__name__ if last_error else "Unknown"
            )
            failure_reasons[reason_key] = failure_reasons.get(reason_key, 0) + 1

        if (sent + failed) % 25 == 0:
            try:
                reason_text = ""
                if failure_reasons:
                    reason_text = "\n\n⚠️ " + " • ".join(
                        f"{html.escape(str(k))}: {v}"
                        for k, v in failure_reasons.items()
                    )
                await status.edit_text(
                    f"📢 <b>Broadcasting…</b>\n\n"
                    f"🎯 Target: <b>{mode_label}</b>\n"
                    f"📨 Sent: <b>{sent:,}</b>\n"
                    f"⚠️ Failed: <b>{failed:,}</b>\n"
                    f"📊 Progress: <b>{sent + failed:,}/{len(targets):,}</b>"
                    f"{reason_text}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    try:
        reason_text = ""
        if failure_reasons:
            reason_text = "\n\n<b>Failure reasons</b>\n" + "\n".join(
                f"• {html.escape(str(k))}: <b>{v}</b>"
                for k, v in failure_reasons.items()
            )
        await status.edit_text(
            f"✅ <b>Broadcast Completed</b>\n\n"
            f"🎯 Target: <b>{mode_label}</b>\n"
            f"👤 Users targeted: <b>{user_count:,}</b>\n"
            f"💬 Groups targeted: <b>{group_count:,}</b>\n"
            f"📨 Sent: <b>{sent:,}</b>\n"
            f"⚠️ Failed: <b>{failed:,}</b>\n"
            f"👥 Total targets: <b>{len(targets):,}</b>"
            f"{reason_text}",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def addemoji(update, context):
    """Owner-only helper: save custom emoji IDs from a replied Telegram message."""
    if not update.effective_user or update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Owner only.")
        return

    target = update.message.reply_to_message
    if not target:
        await update.message.reply_text(
            "Reply to a message containing your premium/custom emoji, then send /addemoji."
        )
        return

    entities = list(target.entities or []) + list(target.caption_entities or [])
    custom = [e for e in entities if getattr(e, "type", "") == "custom_emoji" and getattr(e, "custom_emoji_id", None)]
    if not custom:
        await update.message.reply_text(
            "❌ Is message mein custom/premium emoji entity nahi mila. Telegram se premium emoji send karke us message ko reply karo."
        )
        return

    saved = 0
    seen = set()
    for entity in custom:
        eid = str(entity.custom_emoji_id)
        if eid in seen:
            continue
        seen.add(eid)
        alt = "✨"
        try:
            stickers = await context.bot.get_custom_emoji_stickers([eid])
            if stickers and getattr(stickers[0], "emoji", None):
                alt = stickers[0].emoji
        except Exception:
            pass
        await save_custom_emoji(eid, alt, update.effective_user.id)
        saved += 1

    global _CUSTOM_EMOJI_CACHE, _CUSTOM_EMOJI_CACHE_AT
    _CUSTOM_EMOJI_CACHE = {}
    _CUSTOM_EMOJI_CACHE_AT = 0.0
    await update.message.reply_text(
        f"✅ Saved {saved} premium/custom emoji for Vanya chat replies.\n"
        "Ab Vanya normal emoji ko automatically custom animated emoji mein use kar sakti hai."
    )


async def addsudo(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Owner only.")
        return
    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to a user: /addsudo")
        return
    await users.update_one({"_id": target.id}, {"$set": {"is_sudo": True}}, upsert=True)
    try:
        # A newly added sudo immediately receives the complete Sudo command set.
        current_public = [c for c in await context.bot.get_my_commands(scope=BotCommandScopeDefault()) if c.command not in STAFF_COMMANDS]
        await context.bot.set_my_commands(
            current_public + staff_command_objects(owner=False),
            scope=BotCommandScopeChat(chat_id=target.id),
        )
    except Exception:
        pass
    await update.message.reply_text(f"👑 {target.first_name} added as sudo.")

async def delsudo(update, context):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Owner only.")
        return
    target = await target_user(update)
    if not target:
        await update.message.reply_text("Reply to a user: /delsudo")
        return
    await users.update_one({"_id": target.id}, {"$set": {"is_sudo": False}})
    try:
        await context.bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=target.id))
    except Exception:
        pass
    await update.message.reply_text(f"Removed {target.first_name} from sudo.")

async def sudolist(update, context):
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return
    rows = []
    async for u in users.find({"is_sudo": True}):
        rows.append(f"• {html.escape(u.get('name','User'))} (<code>{u['_id']}</code>)")
    await update.message.reply_html("👑 <b>Sudo users</b>\n\n" + ("\n".join(rows) or "None"))

async def auth(update, context):
    if not (await is_owner_or_sudo(update) or await is_admin(update)):
        await update.message.reply_text("⛔ Owner/Sudo or group admins only.")
        return
    chat = update.effective_chat
    await groups.update_one({"_id": chat.id}, {"$set": {"authorized": True, "title": chat.title}}, upsert=True)
    await update.message.reply_text("✅ This group is authorized for Vanya features.")

async def unauth(update, context):
    if not (await is_owner_or_sudo(update) or await is_admin(update)):
        await update.message.reply_text("⛔ Owner/Sudo or group admins only.")
        return
    await groups.update_one({"_id": update.effective_chat.id}, {"$set": {"authorized": False}})
    await update.message.reply_text("🔒 Vanya features are now unauthorized here.")

async def authlist(update, context):
    if not await is_owner_or_sudo(update):
        await update.message.reply_text("⛔ Owner/Sudo only.")
        return
    rows = []
    async for g in groups.find({"authorized": True}):
        rows.append(f"• {html.escape(g.get('title','Group'))} — <code>{g['_id']}</code>")
    await update.message.reply_html("🔐 <b>Authorized groups</b>\n\n" + ("\n".join(rows) or "None"))

async def memory(update, context):
    await ensure_user(update.effective_user)
    # ai_service is imported after owner.py during bot startup, so resolve
    # the memory helper at call time rather than during module import.
    from services.ai_service import _prune_and_get_memories
    facts = await _prune_and_get_memories(update.effective_user.id)
    if not facts:
        await update.message.reply_text("🧠 I don't have any saved facts about you yet.")
        return
    lines = "\n".join(f"• {html.escape(str(x.get('text', '')))}" for x in facts[-MAX_MEMORY:])
    await update.message.reply_html("🧠 <b>What Vanya remembers</b>\n\n" + lines + f"\n\n<i>Memory is kept for {MEMORY_DAYS} days.</i>")

async def remember_cmd(update, context):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Usage: /remember I like cricket")
        return
    await ensure_user(update.effective_user)
    await remember_facts(update.effective_user.id, text)
    await update.message.reply_text("🧠 Got it — I'll remember that for our future chats.")

async def forgetme(update, context):
    await users.update_one({"_id": update.effective_user.id}, {"$set": {"memory": [], "chat_history": []}})
    await update.message.reply_text("🧹 Done. I cleared your saved memory and conversation history.")
