"""Modular handler module for ItzVanyaBot Ultimate.

Loaded after bot.py has initialized its shared runtime namespace. This keeps
existing handler behavior while separating feature code into maintainable files.
"""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

async def callback(update,context):
    q=update.callback_query;data=q.data

    if data.startswith("cj:"):
        room_code = data.split(":", 1)[1].strip().upper()
        if not re.fullmatch(r"[A-HJ-NP-Z2-9]{6}", room_code):
            await q.answer("Invalid Chess room.", show_alert=True)
            return
        try:
            from webserver import CHESS_ROOMS, create_chess_join_token
            room = CHESS_ROOMS.get(room_code)
            if not room or room.get("ended"):
                await q.answer("This Chess room has expired. Start a fresh /chess room.", show_alert=True)
                return
            if update.effective_chat and room.get("group_id") not in (None, update.effective_chat.id):
                await q.answer("This Chess room belongs to another group.", show_alert=True)
                return
            token = create_chess_join_token(room_code, q.from_user.id)
            join_url = get_chess_webapp_url().rstrip("/") + "?room=" + room_code + "&token=" + token
            try:
                await context.bot.send_message(
                    chat_id=q.from_user.id,
                    text="♟️ <b>Vanya Chess</b>\n\nYour private seat link is ready. Tap below to join this room.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("♟️ Join Chess Room", url=join_url)]])
                )
                await q.answer("✅ Private Chess link sent to your DM.", show_alert=False)
            except Exception:
                await q.answer("Start Vanya in DM first, then tap Join again.", show_alert=True)
        except Exception as exc:
            print(f"[ChessJoin] {type(exc).__name__}: {exc}")
            await q.answer("Could not create your Chess seat. Try again.", show_alert=True)
        return

    if data.startswith("dailygame:"):
        await random_game_callback(update, context)
        return

    if data.startswith("kingdom:join:"):
        parts=data.split(":")
        if len(parts)!=3:
            await q.answer("Invalid Kingdom Wars room.", show_alert=True)
            return
        room_code=parts[2].strip().upper()
        if not re.fullmatch(r"[A-HJ-NP-Z2-9]{6}", room_code):
            await q.answer("Invalid room code.", show_alert=True)
            return
        try:
            from webserver import create_kingdom_join_token
            token=create_kingdom_join_token(room_code, q.from_user.id)
            base=(os.getenv("KINGDOM_WARS_WEBAPP_URL") or "").strip().strip('"').strip("'")
            if not base:
                domain=(os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().strip("/")
                if domain:
                    base="https://"+domain+"/kingdom-wars"
            if base and not base.startswith(("https://","http://")):
                base="https://"+base
            room_url=base.rstrip("/")+"?room="+room_code+"&token="+token
            try:
                await context.bot.send_message(
                    chat_id=q.from_user.id,
                    text=(
                        "🏰 <b>Kingdom Wars</b>\n\n"
                        "✅ Telegram account verified.\n"
                        "Your ruler seat is tied to your Telegram ID. "
                        "Use the button below to enter the battle."
                    ),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏰 Enter Verified Kingdom", web_app=WebAppInfo(url=room_url))
                    ]]),
                    disable_web_page_preview=True,
                )
                await q.answer("✅ Verified link sent to your DM.", show_alert=False)
            except Exception:
                bot_username=(getattr(context.bot,"username",None) or os.getenv("BOT_USERNAME","ItzVanyaBot")).lstrip("@")
                await q.answer(
                    f"Start @{bot_username} in DM first, then click Join again.",
                    show_alert=True,
                )
        except Exception as exc:
            print(f"[KingdomVerify] {type(exc).__name__}: {exc}")
            await q.answer("Could not create your verified join link. Try again.", show_alert=True)
        return

    if data.startswith("proposal:"):
        parts=data.split(":")
        if len(parts) == 4:
            action=parts[1]
            try:
                target_id=int(parts[2])
                proposer_id=int(parts[3])
            except (TypeError, ValueError):
                await q.answer("Invalid proposal.", show_alert=True)
                return
            await _complete_proposal_callback(
                q, context, action, target_id, proposer_id
            )
            return

    # Games that answer their own callback query must be routed before the
    # generic q.answer(), otherwise Telegram receives two callback answers.
    if data.startswith("tap:"):
        await tap_cb(q, data.split(":"))
        return
    if data.startswith("mine:"):
        await mines_cb(q, data.split(":"))
        return
    if data.startswith("crash:"):
        await crash_cb(q, data.split(":"))
        return

    if data.startswith("rps:"):
        await rps_cb(q, data.split(":"))
        return
    if data.startswith("card:"):
        await card_cb(q, data.split(":"))
        return
    if data.startswith("uno:"):
        await uno_cb(q, data.split(":"))
        return
    if data.startswith("ludo:"):
        await ludo_cb(q, data.split(":")[1])
        return
    if data.startswith("chess:") or data.startswith("resign:"):
        await chess_cb(q, data.split(":"))
        return

    await q.answer()

    if data == "wordgrid:new":
        await send_wordgrid(q.message, context, getattr(q.from_user, "id", None))
        return
    if data.startswith("wordchain:"):
        if data == "wordchain:join":
            await wordchain_join(update, context)
            return

    if data.startswith("lb|"):
        parts = data.split("|")
        action = parts[1] if len(parts) > 1 else "v"
        period = parts[2] if len(parts) > 2 else "today"
        scope = parts[3] if len(parts) > 3 else "global"
        game = parts[4].upper() if len(parts) > 4 else "ALL"
        if action == "menu":
            await q.edit_message_text(
                "🎮 <b>Select game</b>\n\nChoose which game's points and wins you want to see:",
                parse_mode="HTML",
                reply_markup=leaderboard_kb(period, scope, game, picker=True)
            )
            return
        await _render_leaderboard(q, context, period, scope, game)
        return
    if data.startswith("world:"):
        tab=data.split(":",1)[1]
        url=get_world_webapp_url(tab if tab in ("city","room","pet") else "city")
        if update.effective_chat and update.effective_chat.type in ("group","supergroup"):
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Open Vanya World", url=url)]])
        else:
            markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Open Vanya World", web_app=WebAppInfo(url=url))]])
        await q.message.reply_html("🌌 <b>Vanya World</b>\n\nBuild your 3D city, decorate your room and raise your pet. ✨", reply_markup=markup)
        return
    if data.startswith("owner:"):
        if not await is_owner_or_sudo(update):
            await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
            return
        action = data.split(":", 1)[1]
        if action == "close":
            await q.edit_message_text("🔒 <b>Owner panel closed.</b>", parse_mode="HTML")
            return
        if action == "monitor":
            await q.edit_message_text(
                "╭━━〔 📡 <b>MONITORING</b> 〕━━╮\n"
                "│ Keep an eye on Vanya's activity\n"
                "│ AI usage, bot reach and saved logs\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯",
                parse_mode="HTML",
                reply_markup=owner_monitor_kb(),
            )
            return
        if action == "manage":
            await q.edit_message_text(
                "╭━━〔 🛠 <b>MANAGEMENT</b> 〕━━╮\n"
                "│ Broadcast, group access and sudo controls\n"
                "│ Owner-only controls stay hidden from Sudo\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯",
                parse_mode="HTML",
                reply_markup=owner_manage_kb(update.effective_user.id == OWNER_ID),
            )
            return
        if action == "economy":
            await q.edit_message_text(
                "╭━━〔 💰 <b>ECONOMY</b> 〕━━╮\n"
                "│ Manage virtual coin balances\n"
                "│ Commands remain Owner/Sudo restricted\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯",
                parse_mode="HTML",
                reply_markup=owner_economy_kb(),
            )
            return
        if action == "games":
            await q.edit_message_text(
                "╭━━〔 🎮 <b>GAME TOOLS</b> 〕━━╮\n"
                "│ Private answer-reveal tools\n"
                "│ Normal players never see the answers\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯",
                parse_mode="HTML",
                reply_markup=owner_games_kb(),
            )
            return
        if action == "users":
            await q.edit_message_text(
                "╭━━〔 👑 <b>USER ACCESS</b> 〕━━╮\n"
                "│ Sudo, authorized groups and owner tools\n"
                "│ Sensitive controls are Owner-only\n"
                "╰━━━━━━━━━━━━━━━━━━━━╯",
                parse_mode="HTML",
                reply_markup=owner_users_kb(update.effective_user.id == OWNER_ID),
            )
            return
        if action == "aistats":
            await aistats(update, context)
            return
        if action == "log":
            await log(update, context)
            return
        if action == "stats":
            try:
                total_users = await users.count_documents({})
                started_users = await users.count_documents({"started": True})
                total_groups = await groups.count_documents({})
                active_groups = await groups.count_documents({"active": {"$ne": False}})
                sudo_db = await users.count_documents({"is_sudo": True})
                sudo_total = max(sudo_db, len(SUDO_IDS))
                await q.edit_message_text(
                    "╭━━━〔 📊 <b>VANYA BOT STATS</b> 〕━━━╮\n"
                    "┃ 🔒 <i>Owner/Sudo only</i>\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    f"👥 <b>Groups where bot is recorded:</b> {active_groups:,}\n"
                    f"🗂️ <b>Total known groups:</b> {total_groups:,}\n"
                    f"👤 <b>Total known users:</b> {total_users:,}\n"
                    f"🚀 <b>Started users:</b> {started_users:,}\n"
                    f"👑 <b>Sudo users:</b> {sudo_total:,}",
                    parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
                )
            except Exception as e:
                await q.edit_message_text(f"⚠️ Stats error: {html.escape(str(e))}", parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]]))
            return
        if action == "commands":
            if not await is_owner_or_sudo(update):
                await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
                return

            lines = [
                "👑 <b>Owner/Sudo Commands</b>",
                "",
            ]
            for command, description in STAFF_COMMANDS.items():
                if command in {"owner", "ownerpanel", "panel", "devpanel"}:
                    continue
                if update.effective_user.id != OWNER_ID and command in OWNER_ONLY_COMMANDS:
                    continue
                lines.append(
                    f"• <code>/{command}</code> — {html.escape(description)}"
                )

            await q.edit_message_text(
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "revealgrid":
            if not await is_owner_or_sudo(update):
                await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
                return
            await q.edit_message_text(
                "🔐 <b>Wordgrid Answer Reveal</b>\n\n"
                "Use <code>/revealgrid</code> inside the group where an active Wordgrid game is running.\n\n"
                "The answer will be sent to your private chat and will not be shown to group members.\n"
                "🔒 <i>Owner/Sudo only.</i>",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "revealwordseek":
            if not await is_owner_or_sudo(update):
                await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
                return
            await q.edit_message_text(
                "🔎 <b>Wordseek Answer Reveal</b>\n\n"
                "Use <code>/revealwordseek</code> inside the group where an active Wordseek game is running.\n\n"
                "The answer will be sent to your private chat and will not be shown to group members.\n"
                "👑 <i>Owner/Sudo only.</i>",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "revealjumble":
            if not await is_owner_or_sudo(update):
                await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML")
                return
            await q.edit_message_text(
                "🔤 <b>Jumble Answer Reveal</b>\n\n"
                "Use <code>/revealjumble</code> inside the group where an active Jumble round is running.\n\n"
                "The answer will be sent to your private chat and will not be shown to group members.\n"
                "👑 <i>Owner/Sudo only.</i>",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "blacklist":
            await q.edit_message_text(
                "🚫 <b>Blacklist</b>\n\n"
                "Use <code>/blacklist</code> by replying to a user's message, "
                "or use <code>/blacklist USER_ID</code>.\n\n"
                "Remove with <code>/unblacklist</code>.\n"
                "🔒 <i>Owner only.</i>",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ User Access", callback_data="owner:users")]]),
            )
            return
        if action == "addsudo":
            await q.edit_message_text(
                "➕ <b>Add Sudo</b>\n\n"
                "Reply to a user's message and send <code>/addsudo</code>."
                "\nOnly the Owner can add sudo users.",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "delsudo":
            await q.edit_message_text(
                "➖ <b>Remove Sudo</b>\n\n"
                "Reply to a sudo user's message and send <code>/delsudo</code>."
                "\nOnly the Owner can remove sudo users.",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "addemoji":
            await q.edit_message_text(
                "🎨 <b>Premium Emoji</b>\n\n"
                "Send your Premium/custom emoji to Vanya, then reply to that emoji message with <code>/addemoji</code>."
                "\nOnly the Owner can save emoji IDs.",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "coins":
            await q.edit_message_text(
                "💰 <b>Coin Control</b>\n\n"
                "Only Owner/Sudo can use these commands:\n\n"
                "<code>/addcoins USER_ID AMOUNT</code>\n"
                "<code>/removecoins USER_ID AMOUNT</code>\n\n"
                "Example:\n"
                "<code>/addcoins 123456789 5000</code>\n"
                "<code>/removecoins 123456789 1000</code>\n\n"
                "These commands are hidden from normal users and public command menus.",
                parse_mode="HTML",
                reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "broadcast":
            await q.edit_message_text(
                "📢 <b>Broadcast Center</b>\n\n"
                "Choose where the broadcast should go:\n\n"
                "👤 <b>Users Only</b> — private users who started Vanya\n"
                "💬 <b>Groups Only</b> — groups known to Vanya\n"
                "🌐 <b>Users + Groups</b> — send to both\n\n"
                "After choosing, send <code>/broadcast Your message</code> "
                "or reply to any message/media with <code>/broadcast</code>.\n\n"
                "🔒 <i>Owner/Sudo only.</i>",
                parse_mode="HTML", reply_markup=await broadcast_target_kb()
            )
            return
        if action.startswith("broadcastmode:"):
            mode = action.split(":", 1)[1]
            if mode not in {"users", "groups", "both"}:
                await q.answer("Invalid broadcast mode.", show_alert=True)
                return
            modes = {
                "users": "👤 Users Only",
                "groups": "💬 Groups Only",
                "both": "🌐 Users + Groups",
            }
            broadcast_modes = context.application.bot_data.setdefault("broadcast_modes", {})
            broadcast_modes[q.from_user.id] = mode
            await q.edit_message_text(
                "📢 <b>Broadcast Target Selected</b>\n\n"
                f"🎯 <b>{modes[mode]}</b>\n\n"
                "Now send <code>/broadcast Your message</code>\n"
                "or reply to any message/media with <code>/broadcast</code>.\n\n"
                "The broadcast will use the selected target and show a completion report.",
                parse_mode="HTML",
                reply_markup=kb([
                    [InlineKeyboardButton("🔁 Change Target", callback_data="owner:broadcast")],
                    [InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")],
                ])
            )
            return
        if action == "sudo":
            rows=[]
            async for su in users.find({"is_sudo": True}, {"_id": 1, "name": 1, "username": 1}):
                label=html.escape(su.get("name", "User"))
                if su.get("username"):
                    label += f" (@{html.escape(su['username'])})"
                rows.append(f"• {label} — <code>{su['_id']}</code>")
            body="\n".join(rows) or "None"
            await q.edit_message_text(
                "👑 <b>Sudo Users</b>\n\n"+body+
                "\n\n<i>/addsudo and /delsudo are Owner-only.</i>",
                parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "auth":
            rows=[]
            async for g in groups.find({"authorized": True}, {"_id": 1, "title": 1}):
                rows.append(f"• {html.escape(g.get('title','Group'))} — <code>{g['_id']}</code>")
            body="\n".join(rows) or "None"
            await q.edit_message_text(
                "🔐 <b>Authorized Groups</b>\n\n"+body+
                "\n\nUse <code>/auth</code> or <code>/unauth</code> in the target group.",
                parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Owner Panel", callback_data="owner:home")]])
            )
            return
        if action == "home":
            owner_only = q.from_user.id == OWNER_ID
            role = "OWNER" if owner_only else "SUDO"
            await q.edit_message_text(
                "╭━━━〔 👑 <b>VANYA CONTROL CENTER</b> 〕━━━╮\n"
                f"┃ 🔒 Access: <b>{role}</b>\n"
                "┃ ⚡ Quick controls & monitoring\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                "📡 <b>Monitor</b>\n"
                "AI usage • bot stats • persistent logger\n\n"
                "🛠 <b>Manage</b>\n"
                "Broadcast • sudo • auth • economy\n\n"
                "🎮 <b>Game Tools</b>\n"
                "Private answer-reveal controls for active games\n\n"
                "👇 <b>Select a control below</b>",
                parse_mode="HTML",
                reply_markup=owner_panel_kb(
                    owner_only=owner_only,
                    staff_access=await is_owner_or_sudo(update),
                )
            )
            return
    if data=="chat:start":
        await q.edit_message_text(
            "💬 <b>Chat With Vanya</b> 💜\n\n"
            "Send me a message in this chat, or use <code>/chat your message</code>.\n\n"
            "✨ I can remember recent conversation context when memory is enabled.",
            parse_mode="HTML",
            reply_markup=kb([
                [InlineKeyboardButton("⌨️ Use /chat", callback_data="chat:usage")],
                [InlineKeyboardButton("⬅️ Back", callback_data="cat:chat"), InlineKeyboardButton("⌂ Home", callback_data="home")]
            ])
        )
        return
    if data=="chat:usage":
        await q.edit_message_text(
            "💬 <b>Chat usage</b>\n\n<code>/chat hello Vanya</code>\n<code>/chat how are you?</code>\n\nOr simply DM me and send your message.",
            parse_mode="HTML",
            reply_markup=kb([[InlineKeyboardButton("⬅️ Back", callback_data="chat:start")]])
        )
        return
    if data=="profile:view":
        u=await get_user(update.effective_user.id)
        await q.edit_message_text(
            f"╭━━━〔 👤 <b>PROFILE</b> 〕━━━╮\n"
            f"┃ <b>{html.escape(u.get('name','User'))}</b>\n"
            f"┃ 💰 Coins: <b>{u.get('coins',0):,}</b>\n"
            f"┃ ⭐ XP: <b>{u.get('xp',0):,}</b>\n"
            f"┃ 🏆 Level: <b>{u.get('level',1)}</b>\n"
            f"╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode="HTML",
            reply_markup=kb([[InlineKeyboardButton("💬 Chat", callback_data="chat:start")], [InlineKeyboardButton("⬅️ Back", callback_data="cat:chat")]])
        )
        return

    if data=="home":
        await q.edit_message_text(
            "✨ <b>Vanya help menu</b> ✨\n\n<i>Pick a category below to see my commands.</i> 💜\n\n💬 <b>or just DM me — or say \"Vanya\" in a group — to chat anytime!</b>",
            parse_mode="HTML", reply_markup=help_menu_kb())
        return
    if data=="startmenu":
        await q.edit_message_text(
            "✨ <b>Hey, I'm Vanya 💜</b>\n\n"
            "<i>Not your average bot — I actually feel like a real one. 😏</i>\n\n"
            "🫧 <b>I remember you</b> — our chats, your vibe, where we left off.\n"
            "💬 <b>I talk like a person</b>, never a script — sweet when you're sweet, savage when you're not.\n"
            "🔔 <b>I check in too</b> — go quiet on me and I might text first. 😈\n\n"
            "Oh, and I run the fun around here:\n"
            "🎮 <b>20+ games</b> • 💰 <b>a living economy</b>\n"
            "💕 <b>ship, marry & drama</b>\n\n"
            "Tap <b>Help & Commands</b> to see it all, or add me to your group 👇",
            parse_mode="HTML", reply_markup=start_menu())
        return
    if data=="help":
        await q.edit_message_text(
            "✨ <b>Vanya help menu</b> ✨\n\n<i>Pick a category below to see my commands.</i> 💜\n\n💬 <b>or just DM me — or say \"Vanya\" in a group — to chat anytime!</b>",
            parse_mode="HTML", reply_markup=help_menu_kb())
        return
    if data.startswith("cat:"):
        name=data.split(":")[1]
        if name == "admin" and not await is_owner_or_sudo(update):
            await q.edit_message_text("⛔ <b>Owner/Sudo only.</b>", parse_mode="HTML", reply_markup=kb([[InlineKeyboardButton("⟵ Back", callback_data="help")]]))
            return
        if name=="games":
            await q.edit_message_text("🎮 <b>Game commands</b> 🎮\n\n<i>Choose a game below to see how to play and its commands!</i> 👇",parse_mode="HTML",reply_markup=game_menu_kb())
        else:
            title,lines=CATEGORIES[name]
            safe_lines = [safe_html(line) for line in lines]
            await q.edit_message_text(title+"\n\n"+"\n".join(safe_lines),parse_mode="HTML",reply_markup=back())
        return
    if data.startswith("game:"):
        key=data.split(":")[1]
        if key.upper() == "UNO":
            webapp_url = get_uno_webapp_url()
            if webapp_url and webapp_url.startswith("https://"):
                msg = (
                    "╭━━━〔 🃏 <b>VANYA UNO</b> 〕━━━╮\n"
                    "┃ <i>Live Multiplayer Arena</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🎯 Create or join a room and play with 2–4 real players.\n"
                    "🤖 Add a bot only if you want one."
                )
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    markup = kb([
                        [InlineKeyboardButton("🃏 Play UNO", url=webapp_url)],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                else:
                    markup = kb([
                        [InlineKeyboardButton("🃏 Play UNO", web_app=WebAppInfo(url=webapp_url))],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg, parse_mode="HTML", reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🃏 <b>UNO Web App is not configured.</b>\n\nSet <code>UNO_WEBAPP_URL</code> to your public HTTPS /uno URL in Railway Variables.",
                    parse_mode="HTML", reply_markup=back()
                )
            return
        if key.upper() == "LUDO":
            webapp_url = get_ludo_webapp_url()
            if webapp_url and webapp_url.startswith("https://"):
                msg = (
                    "╭━━━〔 🎲 <b>VANYA LUDO</b> 〕━━━╮\n"
                    "┃ <i>Live Multiplayer Arena</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🎯 Create or join a room and play with 2–4 real players.\n"
                    "🤖 Add a bot only if you want one."
                )
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    markup = kb([
                        [InlineKeyboardButton("🎲 Play Ludo", url=webapp_url)],
                        [InlineKeyboardButton("💬 Game Chat", callback_data="gchat:LUDO:telegram")],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                else:
                    markup = kb([
                        [InlineKeyboardButton("🎲 Play Ludo", web_app=WebAppInfo(url=webapp_url))],
                        [InlineKeyboardButton("💬 Game Chat", callback_data="gchat:LUDO:telegram")],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg, parse_mode="HTML", reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🎲 <b>Ludo Web App is not configured.</b>\n\nSet <code>LUDO_WEBAPP_URL</code> to your public HTTPS /ludo URL in Railway Variables.",
                    parse_mode="HTML",
                    reply_markup=back()
                )
            return
        if key.upper() == "SCRIBBLE":
            webapp_url = (os.getenv("SCRIBBLE_WEBAPP_URL") or "").strip()
            if not webapp_url:
                domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().strip("/")
                if domain:
                    webapp_url = "https://" + domain + "/scribble"
            if webapp_url and not webapp_url.startswith(("https://", "http://")):
                webapp_url = "https://" + webapp_url
            if webapp_url:
                msg = (
                    "╭━━━〔 🖌️ <b>VANYA SCRIBBLE</b> 〕━━━╮\n"
                    "┃ <i>Real-time drawing room</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🎨 Create or join a live drawing room.\n"
                    "💬 Draw and chat together in real time."
                )
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    markup = kb([
                        [InlineKeyboardButton("🖌️ Open Scribble", url=webapp_url)],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                else:
                    markup = kb([
                        [InlineKeyboardButton("🖌️ Open Scribble", web_app=WebAppInfo(url=webapp_url))],
                        [InlineKeyboardButton("⟵ Back to Games", callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg, parse_mode="HTML", reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🖌️ <b>Scribble Web App is not configured.</b>\n\nSet <code>SCRIBBLE_WEBAPP_URL</code> to your public HTTPS /scribble URL in Railway Variables.",
                    parse_mode="HTML",
                    reply_markup=back()
                )
            return
        if key.upper() == "KINGDOMWARS":
            webapp_url = (os.getenv("KINGDOM_WARS_WEBAPP_URL") or "").strip().strip('"').strip("'")
            if not webapp_url:
                domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().strip("/")
                if domain:
                    webapp_url = "https://" + domain + "/kingdom-wars"
            if webapp_url and not webapp_url.startswith(("https://", "http://")):
                webapp_url = "https://" + webapp_url
            if webapp_url:
                room_url = webapp_url.rstrip("/") + "?room=" + str(getattr(update, "_kingdom_room_code", "") or "")
                # Create a room for the callback chat so the button opens a ready lobby.
                try:
                    from webserver import create_kingdom_room_for_group
                    room_code = await create_kingdom_room_for_group(
                        update.effective_chat.id if update.effective_chat and update.effective_chat.type != "private" else None
                    )
                    room_url = webapp_url.rstrip("/") + "?room=" + room_code
                except Exception:
                    pass
                msg = (
                    "╭━━━〔 🏰 <b>KINGDOM WARS</b> 〕━━━╮\n"
                    "┃ <i>Live Grand Strategy Arena</i> ✦\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "👑 Build your kingdom, gather resources, recruit an army and conquer land.\n"
                    "⚔️ <b>2–6 rulers</b> • live turns • real-time war map\n"
                    "🏆 Reach <b>70 land</b> to claim the crown.\n\n"
                    "💰 Winner: <b>+500 coins +100 XP</b>\n"
                    "🎁 Participants: <b>+100 coins +25 XP</b>"
                )
                if update.effective_chat and update.effective_chat.type in ("group","supergroup"):
                    markup=kb([
                        [InlineKeyboardButton("🔐 Join as Telegram",callback_data=f"kingdom:join:{room_code}")],
                        [InlineKeyboardButton("⟵ Back to Games",callback_data="cat:games")]
                    ])
                else:
                    markup=kb([
                        [InlineKeyboardButton("🏰 Open Kingdom Wars",web_app=WebAppInfo(url=room_url))],
                        [InlineKeyboardButton("⟵ Back to Games",callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg,parse_mode="HTML",reply_markup=markup)
            else:
                await q.edit_message_text(
                    "🏰 <b>Kingdom Wars Web App is not configured.</b>\n\n"
                    "Set <code>KINGDOM_WARS_WEBAPP_URL</code> or <code>MINIAPP_DOMAIN</code> in Railway Variables.",
                    parse_mode="HTML",reply_markup=back()
                )
            return
        if key.upper() == "CHESS":
            webapp_url=get_chess_webapp_url()
            if webapp_url and webapp_url.startswith("https://"):
                msg=("╭━━━〔 ♟️ <b>VANYA CHESS</b> 〕━━━╮\n"
                     "┃ <i>Live Multiplayer Arena</i> ✦\n"
                     "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
                     "♟️ Create a room, invite one player, or add a bot.\n"
                     "⏱️ Live board, turns, moves and chat.\n"
                     "🏆 Winner: <b>+750 points +750 coins</b>")
                if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
                    try:
                        from webserver import create_chess_room_for_group
                        room_code = await create_chess_room_for_group(update.effective_chat.id)
                        markup=kb([
                            [InlineKeyboardButton("♟️ Join Chess Securely",callback_data=f"cj:{room_code}")],
                            [InlineKeyboardButton("⟵ Back to Games",callback_data="cat:games")]
                        ])
                    except Exception as exc:
                        await q.edit_message_text(
                            f"⚠️ Chess room create nahi ho saka: {html.escape(str(exc))}",
                            parse_mode="HTML", reply_markup=back()
                        )
                        return
                else:
                    markup=kb([
                        [InlineKeyboardButton("♟️ Play Chess",web_app=WebAppInfo(url=webapp_url))],
                        [InlineKeyboardButton("⟵ Back to Games",callback_data="cat:games")]
                    ])
                await q.edit_message_text(msg,parse_mode="HTML",reply_markup=markup)
            else:
                await q.edit_message_text("♟️ <b>Chess Web App is not configured.</b>\n\nSet <code>CHESS_WEBAPP_URL</code> to your public HTTPS /chess URL in Railway Variables.",parse_mode="HTML",reply_markup=back())
            return
        body=f"🎯 <b>How to play</b>\n{safe_html(GAME_INFO.get(key,'Coming soon.'))}\n\n💬 <b>Game Chat</b> — talk with players without leaving the arena."
        msg, markup=game_room_ui(key, body)
        await q.edit_message_text(msg,parse_mode="HTML",reply_markup=markup);return
    if data.startswith("gchat:"):
        parts=data.split(":",2)
        key=parts[1] if len(parts)>1 else "ARCADE"
        room=parts[2] if len(parts)>2 else "current chat"
        await q.answer("Game chat opened", show_alert=False)
        await q.edit_message_text(
            f"💬 <b>{html.escape(key)} GAME CHAT</b>\n\n"
            f"Room: <code>{html.escape(room)}</code>\n\n"
            "Send your message with:\n<code>/gchat your message</code>\n\n"
            "Messages are posted into the current game chat.",
            parse_mode="HTML",
            reply_markup=kb([[InlineKeyboardButton("🎮 Back to Arena",callback_data=f"game:{key}" if key!="ARCADE" else "cat:games")], [InlineKeyboardButton("⌂ Home",callback_data="home")]]))
        return
