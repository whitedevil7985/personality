"""Vanya help and game menu handlers."""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

CATEGORIES = {
    "chat": (
        "💬 <b>Chat</b>",
        [
            "/chat — Chat with Vanya",
            "/gchat — Send a group chat message",
            "/persona — Change your chat persona",
            "/memory — View saved memory",
            "/remember — Save a memory",
            "/forgetme — Clear saved memory",
        ],
    ),
    "economy": (
        "💰 <b>Economy</b>",
        [
            "/bal — Check your balance",
            "/daily — Claim daily coins and XP",
            "/work — Work for coins",
            "/give — Give coins to another user",
            "/toprich — Richest users",
            "/leaderboard — View leaderboard",
            "/rank — View your rank",
        ],
    ),
    "actions": (
        "🗡 <b>Actions</b>",
        [
            "/rob — Rob another player",
            "/protect — Buy protection",
            "/shield — Check protection",
            "/kill — Attack another player",
            "/revive — Revive yourself",
        ],
    ),
    "romance": (
        "💕 <b>Romance</b>",
        [
            "/propose — Propose to another user",
            "/accept — Accept a proposal",
            "/reject — Reject a proposal",
            "/divorce — End a marriage",
            "/marriage — View marriage status",
            "/couple — Pair group players",
            "/topcouples — View group couples",
        ],
    ),
    "admin": (
        "🔐 <b>Admin</b>",
        [
            "/owner — Open the owner panel",
            "/broadcast — Broadcast a message",
            "/stats — View bot statistics",
        ],
    ),
    "games": (
        "🎮 <b>Games</b>",
        [],
    ),
}

async def category(update, context, name):
    title, lines = CATEGORIES[name]
    body = title + "\n\n" + "\n".join(lines)
    await update.message.reply_html(body, reply_markup=category_kb(name))

def category_kb(name):
    if name == "games":
        return game_menu_kb()
    if name == "chat":
        return kb([
            [InlineKeyboardButton("💬 Start Chat", callback_data="chat:start")],
            [InlineKeyboardButton("👤 My Profile", callback_data="profile:view")],
            [InlineKeyboardButton("⬅️ Back to categories", callback_data="help")],
        ])
    return kb([[InlineKeyboardButton("⬅️ Back to categories", callback_data="help")]])

async def help_cmd(update, context):
    await ensure_user(update.effective_user)
    await update.message.reply_html(
        "✨ <b>Vanya help menu</b> ✨\n\n"
        "<i>Pick a category below to see my commands.</i> 💜\n\n"
        "💬 <b>or just DM me — or say \"Vanya\" in a group — to chat anytime!</b>",
        reply_markup=help_menu_kb()
    )

def help_menu_kb():
    return kb([
        [InlineKeyboardButton("💬 Chat with me", callback_data="cat:chat")],
        [InlineKeyboardButton("💰 Economy", callback_data="cat:economy"),
         InlineKeyboardButton("🗡 Actions", callback_data="cat:actions")],
        [InlineKeyboardButton("💕 Romance", callback_data="cat:romance"),
         InlineKeyboardButton("🎮 Games", callback_data="cat:games")],
        [developer_button()],
        [InlineKeyboardButton("⟵ Back to start", callback_data="startmenu")],
    ])



# ───────────────────── games menu ─────────────────────

GAME_ITEMS = [
    ("🃏 UNO","UNO"), ("💎 Mines","MINES"), ("🪨 RPS","RPS"), ("🔎 Wordseek","WORDSEEK"),
    ("🔤 Wordgrid","WORDGRID"), ("⚡ Tap","TAP"), ("💥 Crash","CRASH"), ("🐙 Jumble","JUMBLE"),
    ("🎭 Charades","CHARADES"), ("🔗 Wordchain","WORDCHAIN"), ("🔤 Wordscramble","WORDS"),
    ("💣 Hack","HACK"), ("🃏 Card","CARD"), ("♟ Chess","CHESS"), ("🖌 Scribble","SCRIBBLE"),
    ("🎰 Bet","BET"), ("🎲 Ludo","LUDO"), ("🎯 Dice","DICE"), ("🪙 Coinflip","COIN"), ("🎰 Slots","SLOTS"), ("🏰 Kingdom Wars","KINGDOMWARS"), ("🚇 Subway","SUBWAY"),
]

GAME_INFO = {
    "UNO": "/uno — Create an UNO room\n/unojoin — Join the latest room.",
    "MINES": "/mines — Start a 5×5 Mines room. Tap safe tiles and cash out.",
    "RPS": "/rps rock|paper|scissors — Challenge Vanya.",
    "WORDSEEK": "/wordseek — Find the hidden word.",
    "WORDGRID": "/wordgrid — Generate an 8×8 word grid.",
    "TAP": "/tap — Reaction-speed challenge.",
    "CRASH": "/crash &lt;amount&gt; — Virtual-coin multiplier game.",
    "JUMBLE": "/jumble — Unscramble the shown word.",
    "CHARADES": "/charades — Get a random charade prompt.",
    "WORDCHAIN": "/wordchain [5-50] — Start Wordchain; minimum 2 players. /wordchainjoin — Join.",
    "WORDS": "/wordscramble — Unscramble a word.",
    "HACK": "/hack — Fictional puzzle mini-game.",
    "CARD": "/card — Create a 2–4 player Card Match; cards are dealt by DM and played in the group for 4 rounds.",
    "CHESS": "/chess — Create a chess room\n/chessjoin — Join.",
    "SCRIBBLE": "/scribble — Open the social scribble room.",
    "BET": "/bet &lt;amount&gt; — Simple virtual-coin wager.",
    "LUDO": "/ludo — Create a Ludo room\n/ludojoin — Join.",
    "DICE": "/dice — Roll a dice.",
    "COIN": "/coinflip — Flip a coin.",
    "SLOTS": "/slots — Spin the slot machine.",
    "KINGDOMWARS": "/kingdomwars — Open a live 2–6 player strategy room. Build, recruit, fortify and conquer.",
    "STREETRUSH": "/subway — Open the live Subway endless runner. Switch lanes, jump, slide and collect coins.",
}

def game_menu_kb():
    rows=[]
    for i in range(0, len(GAME_ITEMS), 2):
        rows.append([InlineKeyboardButton(label, callback_data=f"game:{key}") for label,key in GAME_ITEMS[i:i+2]])
    rows.append([InlineKeyboardButton("⟵  Back to categories", callback_data="help")])
    return kb(rows)

async def street_rush_cmd(update, context):
    domain = (os.getenv("MINIAPP_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or "personality-production-6405.up.railway.app").strip().strip("/")
    webapp_url = (os.getenv("STREET_RUSH_WEBAPP_URL") or "").strip().strip('"').strip("'")
    if not webapp_url and domain:
        webapp_url = "https://" + domain + "/street-rush"
    if not webapp_url:
        await update.message.reply_text("🏃 Street Rush web app is not configured.")
        return
    if not webapp_url.startswith(("https://","http://")):
        webapp_url = "https://" + webapp_url
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏃 Play Street Rush", url=webapp_url)]])
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🏃 Play Street Rush", web_app=WebAppInfo(url=webapp_url))]])
    await update.message.reply_html(
        "🏃 <b>Vanya Street Rush</b>\n\nRun, dodge, jump, slide and collect coins.",
        reply_markup=markup
    )

async def games_cmd(update, context):
    await update.message.reply_html(
        "🎮 <b>Vanya Game Arena</b> 🎮\n\n"
        "<i>Pick a game. Every game is now maintained as its own module.</i> ✨",
        reply_markup=game_menu_kb()
    )

async def game_info(update, context, key):
    text = GAME_INFO.get(key, "Game coming soon.")
    body = f"🎯 <b>How to play</b>\n{text}\n\n💬 <b>Game Chat</b> is available from the arena screen."
    msg, markup = game_room_ui(key, body)
    await update.message.reply_html(msg, reply_markup=markup)

# ───────────────────── economy ─────────────────────
