#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from pyrogram import filters
from pyrogram.types import Message

from src import bot
from src.database import MongoDb
from src.helpers.filters import sudo_cmd


@bot.on_message(filters.command("dbstats") & sudo_cmd)
async def dbstats(_, message: Message):
    """
    Returns database stats of MongoDB, which includes Total number
    of bot user and total number of bot chats.
    """

    TotalUsers = await MongoDb.users.total_documents()
    TotalChats = await MongoDb.chats.total_documents()

    stats_string = f"**Bot Database Statics.\n\n**♚ Total Number of users : __{TotalUsers}__\n♚ Total number of chats : __{TotalChats}__"
    return await message.reply_text(stats_string)
