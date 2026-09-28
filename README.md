# ✦ ItzVanyaBot — Modular Ultimate

A refactored Telegram bot with the Vanya UI, 30-day memory, economy, moderation, AI chat, and a **separate file for every game**.

## Project structure

```text
ItzVanyaBot/
├── bot.py                 # Main Telegram app + UI + command routing
├── config.py              # ALL environment/config settings
├── db.py                  # MongoDB access
├── features.py            # New progression features
├── games/
│   ├── common.py
│   ├── rps.py
│   ├── dice.py
│   ├── coinflip.py
│   ├── slots.py
│   ├── card.py
│   ├── jumble.py
│   ├── tap.py
│   ├── bet.py
│   ├── uno.py
│   ├── mines.py
│   ├── ludo.py
│   ├── chess.py
│   ├── wordseek.py
│   ├── wordgrid.py
│   ├── crash.py
│   ├── charades.py
│   ├── wordchain.py
│   ├── wordscramble.py
│   ├── hack.py
│   └── scribble.py
├── .env.example
└── requirements.txt
```

## New features

- 🎡 **Daily Spin** — `/spin` gives a virtual-coin reward with a configurable cooldown.
- 🔥 **Activity Streak** — spin activity keeps a daily streak.
- 📜 **Daily Quest** — `/quest` tracks 3 conversational messages per day and gives a virtual-coin reward.
- 🏆 **Achievements** — `/achievements` gives a clean progression screen for milestones.
- 🧩 **Modular games** — each game has its own file, state, callbacks, and future upgrade path.
- ⚙️ **Central config** — settings now live in `config.py` instead of being duplicated inside `bot.py`.
- 🧠 **30-day memory** — existing MongoDB memory remains configurable through `MEMORY_DAYS=30`.
- 📢 **Owner/Sudo Broadcast** — `/broadcast <text>` sends text to users who started the bot and to known groups; reply to any message with `/broadcast` to copy that content (photo/video/document/sticker/etc.).

## Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python3 bot.py
```

For PM2:

```bash
pm2 start bot.py --name ItzVanyaBot --interpreter ./venv/bin/python
pm2 save
```

## Important configuration

Set these in `.env`:

- `BOT_TOKEN`
- `MONGO_URL`
- `OWNER_ID`
- `DEVELOPER_NAME` and `OWNER_PROFILE_URL` — control the Developer button and owner profile link.
  - The **Developer** button appears in the main/start/help/profile menus and opens the configured owner profile directly.
- `ELITE_LLM_API_KEY` — API key for Elite LLMs
- `ELITE_LLM_BASE_URL=https://elite-llms.vercel.app/v1`
- `ELITE_LLM_MODEL=gpt-4o-mini`
- `MEMORY_DAYS=30`

The bot uses **virtual coins only** for all economy and games. No real-money wagering is implemented.

## Game commands

`/uno`, `/unojoin`, `/mines`, `/rps`, `/wordseek`, `/wordgrid`, `/tap`, `/crash`, `/jumble`, `/charades`, `/wordchain`, `/wordscramble`, `/hack`, `/card`, `/chess`, `/chessjoin`, `/scribble`, `/bet`, `/ludo`, `/ludojoin`, `/dice`, `/coinflip`, `/slots`.

Each game's code is isolated, so you can change one game without editing the others.

## Vanya memory

- Per-user MongoDB memory.
- Conversation/fact retention defaults to 30 days and expired entries are pruned automatically.
- The AI backend uses the OpenAI-compatible Elite LLMs `/v1/chat/completions` endpoint.
- `/broadcast <text>` — Owner/Sudo only. Broadcast text to registered users and known groups.
- Reply to any message/media with `/broadcast` — Owner/Sudo only.
- `/memory` shows saved facts.
- `/remember <fact>` saves a fact.
- `/forgetme` clears saved memory/history.

## Logger setup
Set `LOGGER_CHAT_ID` in `.env` to the Telegram channel/group where owner logs should arrive.
The bot logs when Vanya is added to a group/supergroup and every `/start`, including user ID, username when available, chat ID, and optional start payload. The bot must be able to send messages in the logger chat.

## 🎲 Vanya Ludo Telegram Mini App

`/ludo` now opens a Telegram Mini App styled like the supplied Ludo screenshots. The web app includes a private-room lobby, color selection, bot opponents, dice, token movement, turn handling and a playable local match.

Railway variables:
- `BOT_TOKEN` — BotFather token
- `MONGO_URL` — MongoDB URI
- `MONGO_DB` — `ItzVanyaBot`
- `LUDO_WEBAPP_URL` — recommended; set to your public HTTPS Ludo URL, e.g. `https://new-production-21dd.up.railway.app/ludo`. The bot also normalizes a domain without `/ludo`.

The service also starts an HTTPS-facing web server on Railway's `PORT` and serves `/ludo`.

## UNO Telegram Mini App
Set `UNO_WEBAPP_URL` to the public HTTPS URL ending in `/uno`, for example:
`https://your-domain.up.railway.app/uno`

The same public web service also serves `/ludo`. UNO supports 2–4 real players, optional bot players, room codes, live turns, draw/play actions, wild color selection, and game chat over WebSocket.


### Chess Mini App
`/chess` opens a live Telegram Mini App with a room lobby, 2-player play, optional bot, legal chess moves, turns, check/checkmate, resign and chat. Set `CHESS_WEBAPP_URL` to your public HTTPS `/chess` URL; the bot also falls back to `RAILWAY_PUBLIC_DOMAIN`.


## Vanya AI personality
- Vanya is a fictional female-presenting AI character: 22, from Jaipur, studying design in Pune, with a natural Hinglish/chatting style.
- DM replies are direct and conversational; group replies are shorter and only trigger on mentions/replies/common greetings.
- Elite LLM connections reuse one async HTTP session and the bot does not add an artificial post-generation sleep.
- Explicit personal facts/preferences are stored per user and expire after `MEMORY_DAYS` (default 30).
- `AI_MAX_TOKENS`, `AI_TIMEOUT_SECONDS`, and `AI_TEMPERATURE` control response speed/length/style.

### Vanya World (3D)
Commands: `/city`, `/room`, `/pet` (aliases: `/vanyacity`, `/myroom`, `/mypet`).
The Mini App at `/vanya-city` contains three connected modules:
- Vanya City: upgradeable Arcade, Cafe and Market, daily/interval coin drops.
- Build Your Own Room: themes and unlockable 3D room items saved per user.
- Virtual Pet: animated 3D-style pet with hunger, happiness, energy, XP, leveling, feed/play/sleep/rename actions.
World state is stored in the user document under `world` when the app receives valid Telegram WebApp `initData`.
For group URL buttons, Telegram does not provide WebApp initData, so the app uses a browser-local guest profile unless opened as a Telegram Web App.

- 💬 **Safe group AI mode** — Vanya replies in groups when directly mentioned, when someone replies to Vanya, or on simple greetings like `hii`, `hello`, `hii vanya`; set `AI_GROUP_REPLY_ALL=true` only if you intentionally want all-message replies.
- 💕 **Improved couple system** — `/couple` uses actual active group participants; reply to a user with `/couple` to pair directly; `/topcouples` shows existing couples.
