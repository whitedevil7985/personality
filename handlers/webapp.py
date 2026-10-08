"""Modular handler module for ItzVanyaBot Ultimate.

The entrypoint owns shared runtime state; this module only owns the handlers
listed below. The bridge keeps the current runtime namespace shared during the
migration so existing behavior is preserved.
"""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

def get_uno_webapp_url():
    """Return one normalized HTTPS UNO Mini App URL."""
    webapp_url = os.getenv("UNO_WEBAPP_URL", "").strip()
    if not webapp_url:
        domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "avyranewup-production.up.railway.app").strip()
        webapp_url = "https://" + domain.strip("/") + "/uno"
    if not webapp_url:
        return ""
    if not webapp_url.startswith(("https://", "http://")):
        webapp_url = "https://" + webapp_url
    webapp_url = webapp_url.rstrip("/")
    if not webapp_url.lower().endswith("/uno"):
        webapp_url += "/uno"
    return webapp_url

def _room_url(base_url, code):
    base_url = (base_url or "").rstrip("/")
    return base_url + ("&" if "?" in base_url else "?") + "room=" + str(code).upper()[:12]


def _latest_group_web_room(group_id, prefix=None, code=None):
    """Find a Mini App room created from this Telegram group."""
    try:
        from webserver import ROOMS, CHESS_ROOMS
    except Exception:
        return None

    if code:
        wanted = str(code).upper().strip()
        candidates = []
        for key, room in list(ROOMS.items()):
            if key.upper() == f"{prefix}:{wanted}" or room.get("code") == wanted:
                candidates.append(room)
        if prefix == "C":
            room = CHESS_ROOMS.get(wanted)
            if room:
                candidates.append(room)
        return candidates[-1] if candidates else None

    if prefix == "C":
        rooms = list(CHESS_ROOMS.values())
    else:
        rooms = [
            room for key, room in list(ROOMS.items())
            if key.startswith(f"{prefix}:")
        ]

    for room in reversed(rooms):
        if room.get("group_id") == group_id and not room.get("ended") and not room.get("winner"):
            return room
    return None


async def _open_join_room(update, context, kind):
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.message.reply_text(
            f"🎮 /{kind.lower()}join group mein use karo, ya room link se Mini App open karo."
        )
        return

    code = (context.args[0].strip().upper() if context.args else "")
    configs = {
        "LUDO": ("L", get_ludo_webapp_url(), "🎲"),
        "UNO": ("U", get_uno_webapp_url(), "🃏"),
        "CHESS": ("C", get_chess_webapp_url(), "♟️"),
    }
    prefix, base_url, icon = configs[kind]

    room = _latest_group_web_room(chat.id, prefix, code or None)
    if not room:
        await update.message.reply_text(
            f"{icon} Koi active {kind.title()} Mini App room nahi mila. Pehle /{kind.lower()} se room banao."
        )
        return

    join_url = _room_url(base_url, room.get("code"))

    # Group HTTPS links do not carry Telegram WebApp initData. Chess uses a
    # short-lived signed token so the backend can bind this browser seat to
    # the exact Telegram user who pressed /chessjoin. This makes winner
    # rewards and leaderboard points land on the correct account.
    if kind == "CHESS":
        try:
            from webserver import create_chess_join_token
            token = create_chess_join_token(room.get("code"), update.effective_user.id)
            if not token:
                raise RuntimeError("Could not create Chess join token")
            join_url += "&token=" + token
        except Exception as exc:
            await update.message.reply_text(
                f"⚠️ Chess join link create nahi ho saka: {html.escape(str(exc))}",
                parse_mode="HTML",
            )
            return

    label = f"{icon} Join {kind.title()} Room"
    await update.message.reply_text(
        f"{icon} <b>{kind.title()} room {html.escape(str(room.get('code')))} ready hai.</b>\n\n"
        "👇 Tap karke same live room join karo.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(label, web_app=WebAppInfo(url=join_url))]
            if chat.type == "private"
            else [InlineKeyboardButton(label, url=join_url)]
        ]),
    )


async def unojoin(update, context):
    await _open_join_room(update, context, "UNO")


async def ludojoin(update, context):
    await _open_join_room(update, context, "LUDO")


async def chessjoin(update, context):
    await _open_join_room(update, context, "CHESS")


async def uno(update, context):
    """Open the Vanya UNO Telegram Mini App."""
    webapp_url = get_uno_webapp_url()
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        webapp_url += ("&" if "?" in webapp_url else "?") + "gc=" + str(update.effective_chat.id)
    if not webapp_url or not webapp_url.startswith("https://"):
        await update.message.reply_text(
            "🃏 UNO Web App is not configured yet. Set UNO_WEBAPP_URL to your public HTTPS /uno URL in Railway Variables."
        )
        return
    # Telegram web_app buttons are private-chat-only. In groups, use a normal
    # HTTPS URL button so /uno@ItzVanyaBot opens the game for everyone.
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🃏 Open UNO", url=webapp_url)],
            [InlineKeyboardButton("📖 How to play", callback_data="game:UNO")],
        ])
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🃏 Play UNO", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton("📖 How to play", callback_data="game:UNO")],
        ])
    await update.message.reply_text(
        "🃏 <b>Vanya UNO</b>\n\nCreate a room, invite 2–4 players, add a bot if you want, and play directly inside Telegram.",
        parse_mode="HTML", reply_markup=keyboard
    )

def get_chess_webapp_url():
    """Return one normalized HTTPS Chess Mini App URL."""
    webapp_url = os.getenv("CHESS_WEBAPP_URL", "").strip()
    if not webapp_url:
        domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "avyranewup-production.up.railway.app").strip()
        webapp_url = "https://" + domain.strip("/") + "/chess"
    if not webapp_url: return ""
    if not webapp_url.startswith(("https://", "http://")): webapp_url = "https://" + webapp_url
    webapp_url = webapp_url.rstrip("/")
    if not webapp_url.lower().endswith("/chess"): webapp_url += "/chess"
    return webapp_url

async def chess(update, context):
    """Open the Vanya Chess Telegram Mini App with secure group-seat binding."""
    webapp_url = get_chess_webapp_url()
    if not webapp_url or not webapp_url.startswith("https://"):
        await update.message.reply_text(
            "♟️ Chess Web App is not configured yet. Set CHESS_WEBAPP_URL to your public HTTPS /chess URL in Railway Variables."
        )
        return

    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        try:
            from webserver import create_chess_room_for_group, create_chess_join_token
            room_code = await create_chess_room_for_group(chat.id)
            token = create_chess_join_token(room_code, update.effective_user.id)
            if not room_code or not token:
                raise RuntimeError("Could not create Chess room")
            launch_url = _room_url(webapp_url, room_code) + "&token=" + token
        except Exception as exc:
            await update.message.reply_text(
                f"⚠️ Chess room create nahi ho saka: {html.escape(str(exc))}",
                parse_mode="HTML",
            )
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("♟️ Open Chess Room", url=launch_url)],
            [InlineKeyboardButton("👤 Join This Chess Room", url=launch_url)],
            [InlineKeyboardButton("📖 How to play", callback_data="game:CHESS")],
        ])
        await update.message.reply_text(
            "♟️ <b>Vanya Chess</b>\n\n"
            f"Room: <code>{html.escape(room_code)}</code>\n"
            "Tumhara seat Telegram account se securely linked hai.\n"
            "Dusra player <code>/chessjoin</code> kare.\n\n"
            "🏆 Winner: <b>+750 points +750 coins</b>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    # In a private Telegram Mini App, WebApp initData securely identifies the user.
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("♟️ Play Chess", web_app=WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton("📖 How to play", callback_data="game:CHESS")],
    ])
    await update.message.reply_text(
        "♟️ <b>Vanya Chess</b>\n\n"
        "Create a room, invite one player, or add a bot, then play directly inside Telegram.\n\n"
        "🏆 Winner: <b>+750 points +750 coins</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

def get_ludo_webapp_url():
    """Return one normalized HTTPS Ludo Mini App URL."""
    webapp_url = os.getenv("LUDO_WEBAPP_URL", "").strip()
    if not webapp_url:
        domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "avyranewup-production.up.railway.app").strip()
        webapp_url = "https://" + domain.strip("/") + "/ludo"
    if not webapp_url:
        return ""
    if not webapp_url.startswith(("https://", "http://")):
        webapp_url = "https://" + webapp_url
    webapp_url = webapp_url.rstrip("/")
    if not webapp_url.lower().endswith("/ludo"):
        webapp_url += "/ludo"
    return webapp_url


def get_world_webapp_url(tab=None):
    """Return the public Vanya World Mini App URL, honoring an explicit URL.

    The whole city/room/pet UI lives in one page; tabs select the view.
    Direct aliases (/city, /room, /pet, /world) are also served by the web server.
    """
    per_tab = {
        'city': os.getenv('CITY_WEBAPP_URL') or os.getenv('VANYA_CITY_WEBAPP_URL'),
        'room': os.getenv('ROOM_WEBAPP_URL'),
        'pet': os.getenv('PET_WEBAPP_URL'),
    }
    url = (per_tab.get(tab) or os.getenv('VANYA_WORLD_WEBAPP_URL') or '').strip()
    if not url:
        domain = (os.getenv('MINIAPP_DOMAIN') or os.getenv('RAILWAY_PUBLIC_DOMAIN') or 'avyranewup-production.up.railway.app').strip().strip('/')
        url = 'https://' + domain + '/vanya-city'
    if not url.startswith(('https://','http://')):
        url='https://' + url
    url=url.rstrip('/')
    # Normalize a bare domain or old route to the canonical world page.
    path = url.split('://',1)[1].split('/',1)[1] if '://' in url and '/' in url.split('://',1)[1] else ''
    if not path or path in ('world','vanya-world','city','room','pet'):
        base = url.split('://',1)[0] + '://' + url.split('://',1)[1].split('/',1)[0]
        url = base + '/vanya-city'
    elif not url.lower().endswith('/vanya-city'):
        # Preserve other explicit paths rather than silently appending /vanya-city.
        return url + (('&' if '?' in url else '?') + 'tab=' + tab if tab in ('city','room','pet') and 'tab=' not in url else '')
    if tab in ('city','room','pet'):
        url += ('&' if '?' in url else '?') + 'tab=' + tab
    return url


async def world_cmd(update, context, tab='city'):
    url = get_world_webapp_url(tab)
    labels = {'city': '🌆 Open Vanya City', 'room': '🏠 Open My Room', 'pet': '🐾 Open My Pet'}
    text = (
        "╭━━━〔 💜 <b>VANYA WORLD</b> 〕━━━╮\n"
        "┃ <i>Your 3D city • room • pet</i> ✦\n"
        "╰━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "Build your own little world, decorate your room and raise your 3D pet. ✨"
    )
    if update.effective_chat and update.effective_chat.type in ('group','supergroup'):
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(labels.get(tab,'🌌 Open Vanya World'), url=url)]])
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(labels.get(tab,'🌌 Open Vanya World'), web_app=WebAppInfo(url=url))]])
    await update.message.reply_html(text, reply_markup=markup)


async def city(update, context): await world_cmd(update, context, 'city')
async def room(update, context): await world_cmd(update, context, 'room')
async def pet(update, context): await world_cmd(update, context, 'pet')

async def ludo(update, context):
    """Open the Vanya Ludo Telegram Mini App."""
    webapp_url = get_ludo_webapp_url()
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        webapp_url += ("&" if "?" in webapp_url else "?") + "gc=" + str(update.effective_chat.id)
    if not webapp_url or not webapp_url.startswith("https://"):
        await update.message.reply_text(
            "🎲 Ludo Web App is not configured yet. Set LUDO_WEBAPP_URL to your public HTTPS /ludo URL in Railway Variables."
        )
        return
    # Telegram web_app buttons are private-chat-only. In groups, use a normal
    # HTTPS URL button so /ludo@ItzVanyaBot opens the game for everyone.
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Open Ludo", url=webapp_url)],
            [InlineKeyboardButton("📖 How to play", callback_data="game:LUDO")]
        ])
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Play Ludo", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton("📖 How to play", callback_data="game:LUDO")]
        ])
    await update.message.reply_text(
        "🎲 <b>Vanya Ludo</b>\n\nChoose your corner, invite 2–4 players, and play directly inside Telegram.",
        parse_mode="HTML", reply_markup=keyboard
    )
