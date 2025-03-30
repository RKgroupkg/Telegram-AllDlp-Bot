#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from pyrogram import filters
from pyrogram.errors import MessageTooLong
from pyrogram.types import Message

from src import bot
from src.helpers.filters import sudo_cmd
from src.helpers.pasting_services import katbin_paste


@bot.on_message(filters.command("inspect") & sudo_cmd)
async def inspect(_, message: Message):
    """Inspects the message and give reply in json format."""

    try:
        return await message.reply_text(message, quote=True)
    except MessageTooLong:
        output = await katbin_paste(message)
        return await message.reply_text(output, quote=True)
