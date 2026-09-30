import time
import re

from telegram import Bot


class ProtectedBot(Bot):
    """Safe outgoing-message wrapper for Vanya.

    All outgoing text/captions are sanitized so Telegram custom-emoji
    markup/IDs can never leak into normal bot messages.
    """

    @classmethod
    def _strip_emoji_markup(cls, text):
        text = str(text or "")

        # Keep the visible text inside real or escaped tg-emoji tags.
        text = re.sub(
            r'(?is)(?:<|&lt;)tg-emoji\b[^>]*>(.*?)(?:</tg-emoji>|&lt;/tg-emoji&gt;)',
            r'\1',
            text,
        )

        # Remove malformed/open/close tg-emoji tags.
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

        # Remove leaked Telegram custom emoji IDs.
        text = re.sub(
            r'''(?i)\bemoji[-_ ]?id\s*(?:=|:)\s*(?:"|&quot;|'|&apos;)?\d+(?:"|&quot;|'|&apos;)?''',
            '',
            text,
        )

        # Remove leftover XML-like fragments and normalize whitespace.
        text = re.sub(r'(?is)(?:<|&lt;)tg-emoji[^>]*(?:>|&gt;)?', '', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        return text.strip()

    @classmethod
    async def _render_custom_emoji(cls, text, parse_mode=None):
        """Sanitize text only; never generate custom emoji IDs."""
        cleaned = cls._strip_emoji_markup(text)
        return cleaned, parse_mode

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
            kwargs["reply_markup"] = cls._sanitize_reply_markup(
                kwargs["reply_markup"]
            )

        key = "caption" if caption else "text"
        if kwargs.get(key) is not None:
            kwargs[key], kwargs["parse_mode"] = await cls._render_custom_emoji(
                kwargs[key],
                kwargs.get("parse_mode"),
            )

        return kwargs

    async def edit_message_text(self, *args, **kwargs):
        if kwargs.get("text") is not None:
            kwargs["text"], kwargs["parse_mode"] = await type(self)._render_custom_emoji(
                kwargs["text"],
                kwargs.get("parse_mode"),
            )
        return await super().edit_message_text(*args, **kwargs)

    async def edit_message_caption(self, *args, **kwargs):
        if kwargs.get("caption") is not None:
            kwargs["caption"], kwargs["parse_mode"] = await type(self)._render_custom_emoji(
                kwargs["caption"],
                kwargs.get("parse_mode"),
            )
        return await super().edit_message_caption(*args, **kwargs)

    async def send_message(self, *args, **kwargs):
        return await super().send_message(
            *args,
            **await type(self)._prepare_message_kwargs(kwargs),
        )

    async def send_photo(self, *args, **kwargs):
        return await super().send_photo(
            *args,
            **await type(self)._prepare_message_kwargs(kwargs, caption=True),
        )

    async def send_video(self, *args, **kwargs):
        return await super().send_video(
            *args,
            **await type(self)._prepare_message_kwargs(kwargs, caption=True),
        )

    async def send_animation(self, *args, **kwargs):
        return await super().send_animation(
            *args,
            **await type(self)._prepare_message_kwargs(kwargs, caption=True),
        )

    async def send_audio(self, *args, **kwargs):
        return await super().send_audio(
            *args,
            **await type(self)._prepare_message_kwargs(kwargs, caption=True),
        )

    async def send_document(self, *args, **kwargs):
        return await super().send_document(
            *args,
            **await type(self)._prepare_message_kwargs(kwargs, caption=True),
        )

    async def send_voice(self, *args, **kwargs):
        return await super().send_voice(
            *args,
            **await type(self)._prepare_message_kwargs(kwargs, caption=True),
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
