import html
import random
import re
import time

from telegram import Bot


class ProtectedBot(Bot):
    """Global outgoing-message protection + custom/premium emoji renderer.

    Telegram Bot API 9.4+ allows bots to use custom emoji in messages sent to
    private, group and supergroup chats when the bot owner has Telegram
    Premium. The actual custom-emoji IDs still have to come from Telegram
    custom-emoji message entities; this class converts every matching normal
    emoji into those IDs automatically once they have been learned/saved.
    """

    _emoji_cache = {}
    _emoji_cache_at = 0.0

    @classmethod
    async def _get_emoji_map(cls):
        now = time.monotonic()
        if now - cls._emoji_cache_at < 300:
            return cls._emoji_cache
        try:
            # Lazy import avoids a module-import cycle with bot.py.
            from db import get_custom_emoji_map
            cls._emoji_cache = await get_custom_emoji_map()
            cls._emoji_cache_at = now
        except Exception:
            pass
        return cls._emoji_cache

    @staticmethod
    def _emoji_codepoint(ch):
        cp = ord(ch)
        return (
            0x1F000 <= cp <= 0x1FAFF or
            0x2600 <= cp <= 0x27BF or
            0x2300 <= cp <= 0x23FF or
            cp in {0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299}
        )

    @classmethod
    def _strip_plain_emoji(cls, value):
        out = []
        i = 0
        value = str(value or "")
        while i < len(value):
            ch = value[i]
            if cls._emoji_codepoint(ch):
                i += 1
                while i < len(value):
                    cp = ord(value[i])
                    if cp in (0xFE0E, 0xFE0F, 0x200D) or 0x1F3FB <= cp <= 0x1F3FF or 0x20E3 <= cp <= 0x20FF:
                        i += 1
                        continue
                    if cls._emoji_codepoint(value[i]):
                        i += 1
                        continue
                    break
                continue
            if ord(ch) in (0xFE0E, 0xFE0F):
                i += 1
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    @classmethod
    async def _render_custom_emoji(cls, text, parse_mode=None):
        text = str(text or "")
        if not text or "<tg-emoji" in text:
            return text, parse_mode

        mapping = await cls._get_emoji_map()

        # Replace saved alternatives first.
        placeholders = {}
        cleaned = text
        for index, alt in enumerate(sorted(mapping, key=len, reverse=True)):
            ids = mapping.get(alt) or []
            if not ids or alt not in cleaned:
                continue
            token = f"__VANYA_CE_{index}__"
            placeholders[token] = (alt, random.choice(ids))
            cleaned = cleaned.replace(alt, token)

        # Any remaining Unicode emoji are removed. This guarantees the bot
        # never falls back to ordinary Unicode emoji once the global renderer
        # handles the outgoing message.
        cleaned = cls._strip_plain_emoji(cleaned)

        if parse_mode and str(parse_mode).upper() != "HTML":
            # Preserve Markdown/etc. rather than corrupting its syntax.
            # When there are known premium emoji, use HTML only for messages
            # that do not rely on another parse mode.
            if not placeholders:
                return cleaned, parse_mode
            return cleaned, parse_mode

        rendered = html.escape(cleaned) if parse_mode != "HTML" else cleaned
        for token, (alt, eid) in placeholders.items():
            entity = f'<tg-emoji emoji-id="{html.escape(str(eid), quote=True)}">{html.escape(alt)}</tg-emoji>'
            rendered = rendered.replace(html.escape(token), entity)
        return rendered, ("HTML" if placeholders and parse_mode is None else parse_mode)

    @classmethod
    async def _prepare_markup(cls, markup):
        if markup is None or not hasattr(markup, "inline_keyboard"):
            return markup

        mapping = await cls._get_emoji_map()

        # InlineKeyboardButton now supports icon_custom_emoji_id. For each
        # button, move the first learned premium emoji into the button icon
        # slot and remove ordinary Unicode emoji from its visible label.
        try:
            for row in markup.inline_keyboard:
                for button in row:
                    label = getattr(button, "text", None)
                    if not label:
                        continue
                    selected_id = None
                    new_label = label
                    for alt in sorted(mapping, key=len, reverse=True):
                        ids = mapping.get(alt) or []
                        if ids and alt in new_label:
                            selected_id = selected_id or random.choice(ids)
                            new_label = new_label.replace(alt, "")
                    new_label = cls._strip_plain_emoji(new_label)
                    if new_label != label:
                        try:
                            button.text = re.sub(r"\s{2,}", " ", new_label).strip() or label
                        except Exception:
                            pass
                    if selected_id:
                        try:
                            button.icon_custom_emoji_id = str(selected_id)
                        except Exception:
                            # Older python-telegram-bot builds simply ignore
                            # the premium icon field; message text is still safe.
                            pass
        except Exception:
            pass
        return markup

    @classmethod
    async def _protect_and_render(cls, kwargs, text_key="text", caption_key=None, markup_key="reply_markup"):
        kwargs.setdefault("protect_content", True)

        if text_key in kwargs and kwargs.get(text_key) is not None:
            kwargs[text_key], kwargs["parse_mode"] = await cls._render_custom_emoji(
                kwargs[text_key], kwargs.get("parse_mode")
            )
        if caption_key and caption_key in kwargs and kwargs.get(caption_key) is not None:
            kwargs[caption_key], kwargs["parse_mode"] = await cls._render_custom_emoji(
                kwargs[caption_key], kwargs.get("parse_mode")
            )
        if markup_key in kwargs and kwargs.get(markup_key) is not None:
            kwargs[markup_key] = await cls._prepare_markup(kwargs[markup_key])
        return kwargs

    async def edit_message_text(self, *args, **kwargs):
        return await super().edit_message_text(*args, **await self._protect_and_render(kwargs))

    async def edit_message_caption(self, *args, **kwargs):
        return await super().edit_message_caption(*args, **await self._protect_and_render(kwargs, text_key="caption"))

    async def answer_callback_query(self, *args, **kwargs):
        # Callback popups are also outgoing bot text; convert their emoji.
        if kwargs.get("text") is not None:
            kwargs["text"], _ = await self._render_custom_emoji(kwargs["text"], None)
        return await super().answer_callback_query(*args, **self._protected(kwargs))

    async def send_message(self, *args, **kwargs):
        return await super().send_message(*args, **await self._protect_and_render(kwargs))

    async def send_photo(self, *args, **kwargs):
        return await super().send_photo(*args, **await self._protect_and_render(kwargs, caption_key="caption"))

    async def send_video(self, *args, **kwargs):
        return await super().send_video(*args, **await self._protect_and_render(kwargs, caption_key="caption"))

    async def send_animation(self, *args, **kwargs):
        return await super().send_animation(*args, **await self._protect_and_render(kwargs, caption_key="caption"))

    async def send_audio(self, *args, **kwargs):
        return await super().send_audio(*args, **await self._protect_and_render(kwargs, caption_key="caption"))

    async def send_document(self, *args, **kwargs):
        return await super().send_document(*args, **await self._protect_and_render(kwargs, caption_key="caption"))

    async def send_sticker(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_sticker(*args, **kwargs)

    async def send_video_note(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_video_note(*args, **kwargs)

    async def send_voice(self, *args, **kwargs):
        return await super().send_voice(*args, **await self._protect_and_render(kwargs))

    async def send_location(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_location(*args, **kwargs)

    async def send_venue(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_venue(*args, **kwargs)

    async def send_contact(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_contact(*args, **kwargs)

    async def send_poll(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_poll(*args, **kwargs)

    async def send_dice(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_dice(*args, **kwargs)

    async def send_invoice(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_invoice(*args, **kwargs)

    async def send_game(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_game(*args, **kwargs)

    async def send_media_group(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_media_group(*args, **kwargs)

    async def copy_message(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().copy_message(*args, **kwargs)

    async def forward_message(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().forward_message(*args, **kwargs)

    async def forward_messages(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().forward_messages(*args, **kwargs)
