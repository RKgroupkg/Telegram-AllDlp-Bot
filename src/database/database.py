#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from datetime import datetime
from typing import Union

from pyrogram.types import Message

from src.database.MongoDb import chats, users


async def save_user(user: Message) -> None:
    """Saves the new user id in the database if it is not already there."""

    insert_format = {
        "name": (user.first_name or " ") + (user.last_name or ""),
        "username": user.username,
        "date": datetime.now(),
    }

    return await users.update_document(user.id, insert_format)


async def save_chat(chatid: Union[int, str]) -> None:
    """Save the new chat id in the database if it is not already there."""

    insert_format = {"date": datetime.now()}
    return await chats.update_document(chatid, insert_format)
