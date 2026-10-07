"""Modular handler module for ItzVanyaBot Ultimate.

Loaded after bot.py has initialized its shared runtime namespace. This keeps
existing handler behavior while separating feature code into maintainable files.
"""
import sys as _sys
_core = _sys.modules.get("bot") or _sys.modules["__main__"]
globals().update({k: v for k, v in vars(_core).items() if not k.startswith("__")})
del _core, _sys

async def capture_owner_custom_emojis(update, context):
    """Automatically save real custom-emoji IDs from the Owner's messages."""
    user = update.effective_user
    message = update.effective_message
    if not user or user.id != OWNER_ID or not message:
        return

    pairs = []
    try:
        for entity, value in (message.parse_entities() or {}).items():
            if getattr(entity, "type", "") == "custom_emoji" and getattr(entity, "custom_emoji_id", None):
                pairs.append((str(entity.custom_emoji_id), str(value)))
    except Exception as exc:
        print(f"[CustomEmojiCapture] {type(exc).__name__}: {exc}")

    try:
        for entity, value in (message.parse_caption_entities() or {}).items():
            if getattr(entity, "type", "") == "custom_emoji" and getattr(entity, "custom_emoji_id", None):
                pairs.append((str(entity.custom_emoji_id), str(value)))
    except Exception:
        pass

    if not pairs:
        return

    seen = set()
    for eid, alternative in pairs:
        if eid in seen:
            continue
        seen.add(eid)
        await save_custom_emoji(eid, alternative, user.id)

    try:
        from protected_bot import ProtectedBot
        ProtectedBot._emoji_cache = {}
        ProtectedBot._emoji_cache_at = 0.0
    except Exception:
        pass


async def _typing_heartbeat(bot, chat_id, stop_event, interval=2.0):
    """Keep Telegram's 'typing…' indicator visible while AI is generating."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


async def chat(update,context):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("💬 Tell me something: /chat hello Vanya")
        return
    # Do not block the typing indicator or LLM call on a MongoDB write.
    # ai_reply() persists the user state in the background.
    typing_stop = asyncio.Event()
    typing_started_at = time.monotonic()
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )
    except Exception:
        pass
    typing_task = asyncio.create_task(
        _typing_heartbeat(context.bot, update.effective_chat.id, typing_stop)
    )
    try:
        answer = await ai_reply(update.effective_user, text, "private", chat_id=chat.id)
        # Telegram may not visibly render a typing action when the answer is
        # returned almost instantly (for quick replies). Keep it visible for
        # a tiny minimum so DM chat still feels natural.
        min_typing = max(0.0, float(os.getenv("AI_MIN_TYPING_SECONDS", "1.5")))
        remaining = min_typing - (time.monotonic() - typing_started_at)
        if remaining > 0:
            await asyncio.sleep(remaining)
        await send_vanya_reply(update, answer)
    finally:
        typing_stop.set()
        typing_task.cancel()

async def gchat(update,context):
    text=" ".join(context.args).strip()
    if not text:
        await update.message.reply_text("💬 Usage: /gchat <your message>")
        return
    await ensure_user(update.effective_user)
    name=html.escape(update.effective_user.first_name or "Player")
    await update.message.reply_html(f"💬 <b>{name}</b>  ›  {html.escape(text)}")

async def direct_game_answer(update, context):
    """Handle plain-text game answers without hijacking normal group conversation."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return

    # A reply to another human is member-to-member conversation, not a game guess.
    # Replies to Vanya's own game message remain eligible for guessing.
    if (
        update.effective_chat.type in ("group", "supergroup")
        and update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.id != context.bot.id
    ):
        return

    text_value = update.message.text.strip()

    # All current plain-text answer games use a single-token answer. Ignore
    # normal sentences such as "Hmmm sahi h" while any of these games is active.
    active_answer_game = (
        chat_id in context.application.bot_data.get("wordgrid_active", {})
        or chat_id in WORDSEEK_GAMES
        or chat_id in WORDCHAIN_GAMES
        or chat_id in WORDSCRAMBLE_GAMES
        or chat_id in JUMBLE_GAMES
        or chat_id in CHARADES_GAMES
        or chat_id in HACK_GAMES
    )
    if active_answer_game and " " in text_value and not context.args:
        return

    wordgrid_active = context.application.bot_data.get("wordgrid_active", {})
    if chat_id in wordgrid_active:
        await wordgrid_answer(update, context)
        return

    if chat_id in WORDSEEK_GAMES:
        await wordseek_answer(update, context)
        return

    if chat_id in WORDCHAIN_GAMES:
        handled = await wordchain_answer(update, context)
        if handled:
            return

    if chat_id in WORDSCRAMBLE_GAMES:
        handled = await wordscramble_answer(update, context)
        if handled:
            return

    if chat_id in JUMBLE_GAMES:
        handled = await jumble_answer(update, context)
        if handled:
            return

    if chat_id in CHARADES_GAMES:
        handled = await charades_answer(update, context)
        if handled:
            return

    if chat_id in HACK_GAMES:
        handled = await hack_answer(update, context)
        if handled:
            return


async def mention_chat(update,context):
    if not update.message:
        return

    # Quest tracking must never delay chat handling.
    chat = update.effective_chat
    if not chat:
        return

    text = (update.message.text or "").strip()
    if not text or len(text) > 1200:
        return

    if chat.type == "private":
        # DM chat is always enabled. A stale Railway AI_DM_MODE=false should
        # never silently make Vanya stop replying to private messages.
        if text.startswith("/"):
            return

        typing_stop = asyncio.Event()
        try:
            await context.bot.send_chat_action(
                chat_id=chat.id,
                action="typing",
            )
        except Exception:
            pass

        typing_task = asyncio.create_task(
            _typing_heartbeat(context.bot, chat.id, typing_stop)
        )

        try:
            reply_context = ""
            reply_to = update.message.reply_to_message
            if (
                reply_to is not None
                and reply_to.from_user is not None
                and reply_to.from_user.id == context.bot.id
            ):
                reply_context = (
                    getattr(reply_to, "text", None)
                    or getattr(reply_to, "caption", None)
                    or ""
                ).strip()[:1200]

            answer = await ai_reply(
                update.effective_user,
                text,
                "private",
                chat_id=chat.id,
                reply_context=reply_context,
            )

            if not answer:
                # ai_reply should already have a local failsafe, but keep a
                # final DM-only safety net so a provider/DB edge case can
                # never leave the user without a response.
                answer = random.choice([
                    "Haanji 😌 bolo na.",
                    "Sun rahi hu 👀 kya hua?",
                    "Batao yaar 😄",
                ])

            min_typing = max(
                0.0,
                float(os.getenv("AI_MIN_TYPING_SECONDS", "0.7")),
            )
            elapsed = 0.0
            if min_typing:
                await asyncio.sleep(min_typing)

            await send_vanya_reply(update, answer)

        except Exception as exc:
            print(f"[DMChat] {type(exc).__name__}: {exc}")
            try:
                await update.message.reply_text(
                    "Haanji 😌 main yahin hu, bolo."
                )
            except Exception as reply_exc:
                print(
                    f"[DMChat][Fallback] {type(reply_exc).__name__}: "
                    f"{reply_exc}"
                )
        finally:
            typing_stop.set()
            typing_task.cancel()

        return

    if not AI_GROUP_MODE:
        return

    # Never let the normal AI chat handler consume active word-game answers.
    wordgrid_active = context.application.bot_data.get("wordgrid_active", {})
    if (
        chat.id in wordgrid_active
        or chat.id in WORDSEEK_GAMES
        or chat.id in WORDCHAIN_GAMES
        or chat.id in WORDSCRAMBLE_GAMES
        or chat.id in JUMBLE_GAMES
        or chat.id in CHARADES_GAMES
        or chat.id in HACK_GAMES
    ):
        return

    if text.startswith("/"):
        return

    # Telegram can deliver an @mention as an entity rather than as plain text.
    # Only Vanya's own mentions should wake the AI. If someone is talking to
    # another tagged user, do not interrupt that conversation.
    bot_username = getattr(context.bot, "username", None)
    vanya_aliases = {"vanya", "itzvanya"}
    if bot_username:
        vanya_aliases.add(bot_username.lower().lstrip("@"))

    mentioned = bool(re.search(r"(?<!\w)(?:@?(?:vanya|itzvanya))(?!\w)", text, re.I))
    other_user_mentioned = False

    for entity in (update.message.entities or []):
        if getattr(entity, "type", "") == "mention":
            mention_text = text[entity.offset:entity.offset + entity.length].lstrip("@").lower()
            if mention_text in vanya_aliases:
                mentioned = True
            else:
                other_user_mentioned = True

    # Fallback for usernames when Telegram does not provide a usable entity.
    for username in re.findall(r"(?<!\w)@([A-Za-z0-9_]{3,32})", text):
        if username.lower() not in vanya_aliases:
            other_user_mentioned = True

    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    greeting = bool(re.fullmatch(
        r"(?:"
        r"(?:hi+|hello+|hey+)(?:\s+@?(?:vanya|itzvanya))?(?:\s+.*)?"
        r"|@?(?:vanya|itzvanya)\s+(?:hi+|hello+|hey+)(?:\s+.*)?"
        r"|(?:good\s+morning|good\s+night|goodnight)\s+@?(?:vanya|itzvanya)(?:\s+.*)?"
        r"|@?(?:vanya|itzvanya)\s+(?:good\s+morning|good\s+night|goodnight)(?:\s+.*)?"
        r")[\s!.?~]*",
        normalized,
        re.I,
    ))

    replied_to_bot = (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.id == context.bot.id
    )

    # If another user is explicitly tagged, keep Vanya out of that
    # direct conversation.
    if other_user_mentioned and not mentioned:
        return

    # A reply to another person's message is also a private conversation
    # between those users. Only replies to Vanya should trigger her.
    reply_to = update.message.reply_to_message
    if (
        reply_to is not None
        and reply_to.from_user is not None
        and reply_to.from_user.id != context.bot.id
        and not mentioned
    ):
        return

    # Respect the group reply mode. When AI_GROUP_REPLY_ALL is disabled,
    # Vanya only answers when addressed directly, replied to, or greeted.
    # This prevents her from interrupting ordinary member-to-member chat.
    should_reply = bool(
        AI_GROUP_REPLY_ALL
        or mentioned
        or replied_to_bot
        or greeting
    )
    if not should_reply:
        return

    # Do non-critical progression work in the background so it cannot add
    # MongoDB latency to the visible chat reply.
    asyncio.create_task(progress_quest(update.effective_user.id))
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass
    group_title = getattr(update.effective_chat, "title", "") or ""
    try:
        reply_context = ""
        reply_to = update.message.reply_to_message
        if (
            reply_to is not None
            and reply_to.from_user is not None
            and reply_to.from_user.id == context.bot.id
        ):
            reply_context = (
                getattr(reply_to, "text", None)
                or getattr(reply_to, "caption", None)
                or ""
            ).strip()[:1200]

        answer = await ai_reply(
            update.effective_user,
            text,
            "group",
            group_title,
            chat_id=chat.id,
            reply_context=reply_context,
        )

        # Group AI may intentionally decide that a general conversation is
        # not directed at Vanya. Never leak that internal decision to users.
        # Providers have returned both plain text and HTML-escaped variants.
        no_reply_text = html.unescape(str(answer or "")).strip()
        no_reply_patterns = (
            r"^\(?\s*no[ _-]?reply\s*\)?$",
            r"^\(?\s*no[ _-]?reply\s+needed(?:\b|[:.-]).*\)?$",
            r"^\(?\s*no[ _-]?reply\s+needed\s+as\s+this\s+is\s+a\s+general\s+group\s+message.*\)?$",
            r"^<!--\s*no\s+reply\s+needed\b.*?-->$",
            r"^<\!--\s*no\s+reply\s+needed\b.*?-->$",
        )
        if any(re.search(pattern, no_reply_text, re.I | re.S) for pattern in no_reply_patterns):
            print("[GroupChat] AI decided: no reply needed; internal decision suppressed.")
            return

        await send_vanya_reply(update, answer)
    except Exception as exc:
        print(f"[GroupChat] {type(exc).__name__}: {exc}")
        try:
            await update.message.reply_text("Haanji 😌 bolo na.")
        except Exception as reply_exc:
            print(f"[GroupChat][Fallback] {type(reply_exc).__name__}: {reply_exc}")
