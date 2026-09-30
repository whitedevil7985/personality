import html
import random
import time
import re

from telegram import Bot


class ProtectedBot(Bot):
    """Safe outgoing-message wrapper with premium custom-emoji rendering."""

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
        text = str(text or "")
        text = re.sub(
            r'(?is)(?:<|&lt;)tg-emoji\b[^>]*>(.*?)(?:</tg-emoji>|&lt;/tg-emoji&gt;)',
            r'\1',
            text,
        )
        text = re.sub(
            r'(?is)(?:<|&lt;)tg-emoji\b[^>]*(?:>|&gt;)',
            '',
            text,
        )
        text = re.sub(
            r'(?is)(?:</tg-emoji>|&lt;/tg-emoji&gt;)',
            '',
            text,
        )
        text = re.sub(
            r'''(?i)\bemoji[-_ ]?id\s*(?:=|:)\s*(?:"|&quot;|'|&apos;)?\d+(?:"|&quot;|'|&apos;)?''',
            '',
            text,
        )
        return text.strip()

    @classmethod
    async def _render_custom_emoji(cls, text, parse_mode=None):
        """Sanitize provider markup, then render configured premium emojis."""
        cleaned = cls._strip_emoji_markup(text)
        mapping = await cls._get_emoji_map()
        if not mapping:
            return cleaned, parse_mode

        escaped = html.escape(cleaned)
        placeholders = {}
        for index, alt in enumerate(sorted(mapping, key=len, reverse=True)):
            ids = mapping.get(alt) or []
            if not ids or alt not in cleaned:
                continue
            token = f"__VANYA_CE_{index}__"
            placeholders[token] = (alt, str(random.choice(ids)))
            escaped = escaped.replace(html.escape(alt), token)

        if not placeholders:
            return escaped, ("HTML" if parse_mode is None else parse_mode)

        for token, (alt, emoji_id) in placeholders.items():
            entity = (
                f'<tg-emoji emoji-id="{html.escape(emoji_id, quote=True)}">'
                f'{html.escape(alt)}</tg-emoji>'
            )
            escaped = escaped.replace(token, entity)

        return escaped, "HTML"

    @classmethod
    def _sanitize_reply_markup(cls, markup):
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
        if kwargs.get("text") is not None:
            kwargs["text"], kwargs["parse_mode"] = await type(self)._render_custom_emoji(
                kwargs["text"], kwargs.get("parse_mode")
            )
        return await super().edit_message_text(*args, **kwargs)

    async def edit_message_caption(self, *args, **kwargs):
        if kwargs.get("caption") is not None:
            kwargs["caption"], kwargs["parse_mode"] = await type(self)._render_custom_emoji(
                kwargs["caption"], kwargs.get("parse_mode")
            )
        return await super().edit_message_caption(*args, **kwargs)

    async def send_message(self, *args, **kwargs):
        return await super().send_message(*args, **await type(self)._prepare_message_kwargs(kwargs))

    async def send_photo(self, *args, **kwargs):
        return await super().send_photo(*args, **await type(self)._prepare_message_kwargs(kwargs, caption=True))

    async def send_video(self, *args, **kwargs):
        return await super().send_video(*args, **await type(self)._prepare_message_kwargs(kwargs, caption=True))

    async def send_animation(self, *args, **kwargs):
        return await super().send_animation(*args, **await type(self)._prepare_message_kwargs(kwargs, caption=True))

    async def send_audio(self, *args, **kwargs):
        return await super().send_audio(*args, **await type(self)._prepare_message_kwargs(kwargs, caption=True))

    async def send_document(self, *args, **kwargs):
        return await super().send_document(*args, **await type(self)._prepare_message_kwargs(kwargs, caption=True))

    async def send_voice(self, *args, **kwargs):
        return await super().send_voice(*args, **await type(self)._prepare_message_kwargs(kwargs, caption=True))

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
