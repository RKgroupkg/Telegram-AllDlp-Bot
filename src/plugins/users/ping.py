#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from time import time
from httpx import AsyncClient
from datetime import datetime

from pyrogram import filters
from pyrogram.types import Message

from src import bot
from src import BotStartTime
from src.helpers.filters import is_rate_limited
from src.helpers.functions import get_readable_time


@bot.on_message(filters.command(["ping", "alive"]) & is_rate_limited)
async def ping(_, message: Message):
    """Give ping speed of Telegram API along with Bot Uptime."""

    pong_reply = await message.reply_text("pong!", quote=True)

    start = datetime.now()
    async with AsyncClient() as client:
        await client.get("http://api.telegram.org")
    end = datetime.now()

    botuptime = get_readable_time(time() - BotStartTime)
    pong = (end - start).microseconds / 1000
    return await pong_reply.edit(f"♔ **Ping Time:** `{pong}`ms | ❀ **Bot is alive since:** `{botuptime}`")
