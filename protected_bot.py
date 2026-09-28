from telegram import Bot


class ProtectedBot(Bot):
    """Bot subclass that enables Telegram protected-content mode by default.

    Telegram's protect_content flag prevents forwarding and saving of messages
    sent by the bot. It does not replace Telegram's group-level "Restrict
    Saving Content" setting, which must still be enabled by a group admin if
    screenshot/copy restrictions are required for the whole group.
    """

    @staticmethod
    def _protected(kwargs):
        kwargs.setdefault("protect_content", True)
        return kwargs

    async def send_message(self, *args, **kwargs):
        return await super().send_message(*args, **self._protected(kwargs))

    async def send_photo(self, *args, **kwargs):
        return await super().send_photo(*args, **self._protected(kwargs))

    async def send_video(self, *args, **kwargs):
        return await super().send_video(*args, **self._protected(kwargs))

    async def send_animation(self, *args, **kwargs):
        return await super().send_animation(*args, **self._protected(kwargs))

    async def send_audio(self, *args, **kwargs):
        return await super().send_audio(*args, **self._protected(kwargs))

    async def send_document(self, *args, **kwargs):
        return await super().send_document(*args, **self._protected(kwargs))

    async def send_sticker(self, *args, **kwargs):
        return await super().send_sticker(*args, **self._protected(kwargs))

    async def send_video_note(self, *args, **kwargs):
        return await super().send_video_note(*args, **self._protected(kwargs))

    async def send_voice(self, *args, **kwargs):
        return await super().send_voice(*args, **self._protected(kwargs))

    async def send_location(self, *args, **kwargs):
        return await super().send_location(*args, **self._protected(kwargs))

    async def send_venue(self, *args, **kwargs):
        return await super().send_venue(*args, **self._protected(kwargs))

    async def send_contact(self, *args, **kwargs):
        return await super().send_contact(*args, **self._protected(kwargs))

    async def send_poll(self, *args, **kwargs):
        return await super().send_poll(*args, **self._protected(kwargs))

    async def send_dice(self, *args, **kwargs):
        return await super().send_dice(*args, **self._protected(kwargs))

    async def send_invoice(self, *args, **kwargs):
        return await super().send_invoice(*args, **self._protected(kwargs))

    async def send_game(self, *args, **kwargs):
        return await super().send_game(*args, **self._protected(kwargs))

    async def send_media_group(self, *args, **kwargs):
        return await super().send_media_group(*args, **self._protected(kwargs))

    async def copy_message(self, *args, **kwargs):
        return await super().copy_message(*args, **self._protected(kwargs))

    async def forward_message(self, *args, **kwargs):
        return await super().forward_message(*args, **self._protected(kwargs))

    async def forward_messages(self, *args, **kwargs):
        return await super().forward_messages(*args, **self._protected(kwargs))
