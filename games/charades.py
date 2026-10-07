import html
import random
import time
import asyncio
from datetime import datetime, timezone

from db import ensure_user, add_coins, record_game_result, games

REWARD = 25
GAME_TIMEOUT = 90

# One active Charades round per chat.
CHARADES_GAMES = {}
_CHARADES_LOCKS = {}


# Prompt -> accepted answers.
# The prompt is sent privately to the actor; the group only sees who is acting.
PROMPTS = [
    ("brushing your teeth", ("brush teeth", "brushing teeth", "toothbrush")),
    ("drinking a cup of tea", ("tea", "drinking tea", "chai")),
    ("riding a bicycle", ("bicycle", "bike", "cycling")),
    ("playing cricket", ("cricket",)),
    ("taking a selfie", ("selfie", "taking selfie", "photo")),
    ("sleeping in class", ("sleeping", "sleeping in class", "asleep")),
    ("eating very spicy food", ("spicy food", "eating spicy", "spicy")),
    ("walking like a robot", ("robot", "robot walk", "walking robot")),
    ("opening an umbrella in rain", ("umbrella", "opening umbrella")),
    ("flying an airplane", ("airplane", "plane", "flying")),
    ("cooking noodles", ("noodles", "cooking noodles", "maggi")),
    ("playing the guitar", ("guitar", "playing guitar")),
    ("dancing at a party", ("dancing", "dance")),
    ("washing a car", ("washing car", "car wash")),
    ("fishing by a lake", ("fishing", "fish")),
    ("lifting a heavy box", ("lifting", "heavy box", "lifting box")),
    ("running late for class", ("late", "running late", "late for class")),
    ("taking a scary selfie", ("scary selfie", "selfie", "photo")),
    ("looking for your lost phone", ("lost phone", "looking for phone", "phone")),
    ("eating ice cream", ("ice cream", "eating ice cream")),
    ("watching a horror movie", ("horror movie", "scared", "horror")),
    ("pretending to be a superhero", ("superhero", "hero")),
    ("driving a car", ("driving", "car", "driving car")),
    ("playing football", ("football", "soccer")),
    ("catching a butterfly", ("butterfly", "catching butterfly")),
    ("opening a gift", ("gift", "opening gift", "present")),
    ("shivering in the cold", ("cold", "shivering")),
    ("walking a dog", ("dog", "walking dog")),
    ("taking a photo of food", ("food photo", "taking photo", "photo")),
    ("slipping on a banana peel", ("banana peel", "slipping", "slip")),
    ("trying to catch a mosquito", ("mosquito", "catching mosquito")),
    ("studying for an exam", ("studying", "exam", "study")),
    ("typing very fast", ("typing", "fast typing")),
    ("sleeping with a teddy bear", ("sleeping", "teddy", "teddy bear")),
    ("playing a video game", ("video game", "gaming", "game")),
]


def _lock(chat_id):
    chat_id = int(chat_id)
    lock = _CHARADES_LOCKS.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _CHARADES_LOCKS[chat_id] = lock
    return lock


async def _next_prompt():
    """Reserve a prompt so Charades does not immediately recycle old prompts."""
    state_id = "charades_pool"
    state = await games.find_one({"_id": state_id}) or {}
    used = {
        str(x).strip().casefold()
        for x in state.get("used_prompts", [])
        if str(x).strip()
    }
    available = [
        item for item in PROMPTS
        if item[0].casefold() not in used
    ]

    # Once the finite prompt bank is consumed, begin a fresh cycle. This keeps
    # Charades playable indefinitely while avoiding repeats within a cycle.
    new_cycle = not available
    if new_cycle:
        available = list(PROMPTS)

    prompt, answers = random.choice(available)
    update_doc = {
        "$set": {
            "updated_at": datetime.now(timezone.utc),
            "total_prompts": len(PROMPTS),
        }
    }
    if new_cycle:
        update_doc["$set"]["used_prompts"] = [prompt]
    else:
        update_doc["$addToSet"] = {"used_prompts": prompt}

    await games.update_one(
        {"_id": state_id},
        update_doc,
        upsert=True,
    )
    return prompt, answers


async def charades(update, context):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat = update.effective_chat
    chat_id = chat.id
    actor = update.effective_user

    async with _lock(chat_id):
        current = CHARADES_GAMES.get(chat_id)
        if current and time.monotonic() - current["started_at"] < GAME_TIMEOUT:
            await update.message.reply_text(
                "🎭 <b>Charades already running!</b>\n"
                f"🎬 <b>Actor:</b> {html.escape(current.get('actor_name', 'Player'))}\n"
                "💬 Guess the action by typing it.",
                parse_mode="HTML",
            )
            return

        if current:
            CHARADES_GAMES.pop(chat_id, None)

        prompt, answers = await _next_prompt()
        state = {
            "prompt": prompt,
            "answers": tuple(str(x).casefold() for x in answers),
            "actor_id": actor.id,
            "actor_name": actor.first_name or "Player",
            "started_at": time.monotonic(),
        }
        CHARADES_GAMES[chat_id] = state

        # In a group, keep the prompt secret from guessers.
        if chat.type in ("group", "supergroup"):
            try:
                await context.bot.send_message(
                    chat_id=actor.id,
                    text=(
                        "🎭 <b>DUMB CHARADES — YOUR TURN!</b>\n\n"
                        f"🎬 <b>Secret action:</b> {html.escape(prompt)}\n\n"
                        "🎥 Act it out for the group using a video, GIF, sticker, "
                        "or in a group call.\n"
                        "🚫 Do not type the secret answer in the group.\n"
                        "⏱️ You have 90 seconds."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                CHARADES_GAMES.pop(chat_id, None)
                await update.message.reply_html(
                    "⚠️ <b>Couldn't start Charades.</b>\n\n"
                    "Actor ko pehle Vanya ke private chat me <code>/start</code> karna hoga, "
                    "phir group me <code>/charades</code> use karo."
                )
                return

            await update.message.reply_html(
                "🎭 <b>DUMB CHARADES STARTED!</b>\n\n"
                f"🎬 <b>{html.escape(actor.first_name or 'Player')}</b> is the actor!\n"
                "🔐 The secret action is visible only to the actor in DM.\n\n"
                "🎥 <b>Actor:</b> act it out using your camera/video, "
                "GIF, sticker, or by acting in a group call — <b>do not type the answer</b>.\n"
                "💬 <b>Everyone else:</b> guess the action by typing it here.\n"
                f"💰 Reward: <b>+{REWARD} coins</b>\n"
                "⏱️ 90 seconds."
            )
            return

        # In a private chat there are no other guessers, but keep the command
        # useful for testing by showing the prompt directly.
        await update.message.reply_html(
            "🎭 <b>CHARADES</b>\n\n"
            f"🎬 Act this out: <b>{html.escape(prompt)}</b>\n\n"
            f"💰 Reward: <b>+{REWARD} coins</b>\n"
            "⏱️ 90 seconds."
        )


async def charades_answer(update, context):
    if not update.message or not update.message.text or not update.effective_chat:
        return False

    chat_id = update.effective_chat.id
    game = CHARADES_GAMES.get(chat_id)
    if not game:
        return False

    # Replies to another human are normal conversation, not Charades guesses.
    if (
        update.effective_chat.type in ("group", "supergroup")
        and update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.id != context.bot.id
    ):
        return False

    # The actor's own typed message should not accidentally consume the round.
    if update.effective_user and update.effective_user.id == int(game["actor_id"]):
        return False

    async with _lock(chat_id):
        game = CHARADES_GAMES.get(chat_id)
        if not game:
            return False

        if time.monotonic() - game["started_at"] >= GAME_TIMEOUT:
            CHARADES_GAMES.pop(chat_id, None)
            await update.message.reply_text(
                "⏰ <b>Charades expired!</b> Start again with /charades.",
                parse_mode="HTML",
            )
            return True

        guess = update.message.text.strip().casefold()
        if not guess:
            return True

        accepted = {
            str(x).strip().casefold()
            for x in game.get("answers", ())
        }
        if guess not in accepted:
            return False

        # Remove before awarding to prevent duplicate rewards from rapid updates.
        CHARADES_GAMES.pop(chat_id, None)

        user = update.effective_user
        await ensure_user(user)
        await add_coins(user.id, REWARD)
        await record_game_result(user.id, "CHARADES", REWARD, True, chat_id)

        await update.message.reply_html(
            "🎉 <b>CHARADES SOLVED!</b>\n\n"
            f"🎬 Actor: <b>{html.escape(game.get('actor_name', 'Player'))}</b>\n"
            f"👑 Guessed by: <b>{html.escape(user.first_name or 'Player')}</b>\n"
            f"💰 Reward: <b>+{REWARD} coins</b>\n"
            "✨ Start another round with /charades"
        )
        return True
