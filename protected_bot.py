import html
import random
import time
import re

from telegram import Bot


class ProtectedBot(Bot):
    """Safe outgoing-message wrapper for Vanya.

    protect_content is applied only to Bot API methods that actually support
    that parameter. Callback-query and message-edit methods are intentionally
    left untouched so inline buttons continue to work normally.
    """

    _emoji_cache = {}
    _emoji_cache_at = 0.0

    @classmethod
    async def _get_emoji_map(cls):
        now = time.monotonic()
        if now - cls._emoji_cache_at < 300:
            return cls._emoji_cache
        try:
            from db import get_custom_emoji_map
            cls._emoji_cache = await get_custom_emoji_map()
            cls._emoji_cache_at = now
        except Exception:
            pass
        cls._emoji_cache_at = now
        return cls._emoji_cache

    @classmethod
    def _strip_emoji_markup(cls, text):
        """Remove Telegram custom-emoji markup and emoji IDs from outgoing text."""
        text = str(text or "")
        text = re.sub(r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>", r"\\1", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<tg-emoji\b[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"</tg-emoji>", "", text, flags=re.IGNORECASE)
        text = re.sub(r'emoji[-_ ]?id\s*=\s*["\']?[^\s>"\']+["\']?', "", text, flags=re.IGNORECASE)
        text = re.sub(r"emoji[-_ ]?id\s*[:=]\s*\d+", "", text, flags=re.IGNORECASE)
        return text

    @classmethod
    async def _render_custom_emoji(cls, text, parse_mode=None):
        """Sanitize incoming markup, then render configured premium emojis."""
        text = cls._strip_emoji_markup(text)
        if not text:
            return text, parse_mode

        mapping = await cls._get_emoji_map()
        if not mapping:
            return text, parse_mode

        placeholders = {}
        cleaned = text
        for index, alt in enumerate(sorted(mapping, key=len, reverse=True)):
            ids = mapping.get(alt) or []
            if not ids or alt not in cleaned:
                continue
            token = f"__VANYA_CE_{index}__"
            placeholders[token] = (alt, random.choice(ids))
            cleaned = cleaned.replace(alt, token)

        if not placeholders:
            return text, parse_mode

        if parse_mode and str(parse_mode).upper() != "HTML":
            return text, parse_mode

        rendered = html.escape(cleaned) if parse_mode != "HTML" else cleaned
        for token, (alt, eid) in placeholders.items():
            entity = (
                f'<tg-emoji emoji-id="{html.escape(str(eid), quote=True)}">'
                f'{html.escape(alt)}</tg-emoji>'
            )
            rendered = rendered.replace(html.escape(token), entity)

        return rendered, ("HTML" if parse_mode is None else parse_mode)

    @classmethod
    def _sanitize_reply_markup(cls, markup):
        """Telegram inline-keyboard text does not support HTML tg-emoji tags."""
        if markup is None:
            return markup
        try:
            for row in getattr(markup, "inline_keyboard", []) or []:
                for button in row:
                    if getattr(button, "text", None):
                        button.text = cls._strip_emoji_markup(button.text)
        except Exception:
            pass
        return markup

    @classmethod
    async def _prepare_message_kwargs(cls, kwargs, caption=False):
        kwargs.setdefault("protect_content", True)
        if kwargs.get("reply_markup") is not None:
            kwargs["reply_markup"] = cls._sanitize_reply_markup(kwargs["reply_markup"])
        key = "caption" if caption else "text"
        if kwargs.get(key) is not None:
            kwargs[key], kwargs["parse_mode"] = await cls._render_custom_emoji(
                kwargs[key], kwargs.get("parse_mode")
            )
        return kwargs

    async def edit_message_text(self, *args, **kwargs):
        # Editing messages must NOT receive protect_content; that parameter is
        # not accepted by editMessageText. Only custom-emoji rendering is done.
        if kwargs.get("text") is not None:
            kwargs["text"], kwargs["parse_mode"] = await self._render_custom_emoji(
                kwargs["text"], kwargs.get("parse_mode")
            )
        return await super().edit_message_text(*args, **kwargs)

    async def edit_message_caption(self, *args, **kwargs):
        if kwargs.get("caption") is not None:
            kwargs["caption"], kwargs["parse_mode"] = await self._render_custom_emoji(
                kwargs["caption"], kwargs.get("parse_mode")
            )
        return await super().edit_message_caption(*args, **kwargs)

    async def send_message(self, *args, **kwargs):
        return await super().send_message(
            *args, **await self._prepare_message_kwargs(kwargs)
        )

    async def send_photo(self, *args, **kwargs):
        return await super().send_photo(
            *args, **await self._prepare_message_kwargs(kwargs, caption=True)
        )

    async def send_video(self, *args, **kwargs):
        return await super().send_video(
            *args, **await self._prepare_message_kwargs(kwargs, caption=True)
        )

    async def send_animation(self, *args, **kwargs):
        return await super().send_animation(
            *args, **await self._prepare_message_kwargs(kwargs, caption=True)
        )

    async def send_audio(self, *args, **kwargs):
        return await super().send_audio(
            *args, **await self._prepare_message_kwargs(kwargs, caption=True)
        )

    async def send_document(self, *args, **kwargs):
        return await super().send_document(
            *args, **await self._prepare_message_kwargs(kwargs, caption=True)
        )

    async def send_voice(self, *args, **kwargs):
        return await super().send_voice(
            *args, **await self._prepare_message_kwargs(kwargs, caption=True)
        )

    async def send_sticker(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_sticker(*args, **kwargs)

    async def send_video_note(self, *args, **kwargs):
        kwargs.setdefault("protect_content", True)
        return await super().send_video_note(*args, **kwargs)

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
