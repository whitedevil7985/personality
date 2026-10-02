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
        answer = await ai_reply(update.effective_user, text, "private")
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
    """Treat plain text as an answer while a word game is active in the chat."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
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
        # Natural DM replies without requiring /chat.
        if not AI_DM_MODE:
            return
        if text.startswith("/"):
            return
        typing_stop = asyncio.Event()
        typing_started_at = time.monotonic()
        try:
            await context.bot.send_chat_action(chat_id=chat.id, action="typing")
        except Exception:
            pass
        typing_task = asyncio.create_task(
            _typing_heartbeat(context.bot, chat.id, typing_stop)
        )

        stream_state = {"message": None, "last_text": "", "last_edit": 0.0}

        async def stream_to_telegram(current_text):
            clean = re.sub(r"<[^>]+>", "", str(current_text or "")).strip()
            if not clean:
                return
            rendered = html.escape(clean)
            now = time.monotonic()
            message = stream_state.get("message")

            try:
                if message is None:
                    message = await update.message.reply_text(
                        rendered,
                        parse_mode="HTML",
                    )
                    stream_state["message"] = message
                    stream_state["last_text"] = clean
                    stream_state["last_edit"] = now
                    return

                if clean == stream_state.get("last_text"):
                    return
                if now - float(stream_state.get("last_edit", 0.0)) < 0.30:
                    return

                await context.bot.edit_message_text(
                    chat_id=chat.id,
                    message_id=message.message_id,
                    text=rendered,
                    parse_mode="HTML",
                )
                stream_state["last_text"] = clean
                stream_state["last_edit"] = now
            except Exception as exc:
                print(f"[AI][STREAM] Telegram update skipped: {type(exc).__name__}: {exc}")

        try:
            answer = await ai_reply(
                update.effective_user,
                text,
                "private",
                stream_callback=stream_to_telegram,
            )

            min_typing = max(0.0, float(os.getenv("AI_MIN_TYPING_SECONDS", "0.7")))
            remaining = min_typing - (time.monotonic() - typing_started_at)
            if remaining > 0:
                await asyncio.sleep(remaining)

            # If streaming already created the message, only make sure the
            # final text is present. Otherwise use the normal reply path.
            if stream_state.get("message") is None:
                await send_vanya_reply(update, answer)
            elif answer:
                final_clean = re.sub(r"<[^>]+>", "", str(answer)).strip()
                final_rendered = html.escape(final_clean)
                if final_clean and final_clean != stream_state.get("last_text"):
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat.id,
                            message_id=stream_state["message"].message_id,
                            text=final_rendered,
                            parse_mode="HTML",
                        )
                    except Exception as exc:
                        print(f"[AI][STREAM] final edit skipped: {type(exc).__name__}: {exc}")
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

    # Group AI mode: reply to ordinary messages too, even without a mention,
    # greeting, or reply-to-Vanya. Commands and active game answers are
    # excluded above.
    should_reply = True

    # Do non-critical progression work in the background so it cannot add
    # MongoDB latency to the visible chat reply.
    asyncio.create_task(progress_quest(update.effective_user.id))
    try:
        await update.effective_chat.send_action("typing")
    except Exception:
        pass
    group_title = getattr(update.effective_chat, "title", "") or ""
    try:
        answer = await ai_reply(update.effective_user, text, "group", group_title)
        await send_vanya_reply(update, answer)
    except Exception as exc:
        print(f"[GroupChat] {type(exc).__name__}: {exc}")
        try:
            await update.message.reply_text("Haanji 😌 bolo na.")
        except Exception as reply_exc:
            print(f"[GroupChat][Fallback] {type(reply_exc).__name__}: {reply_exc}")
