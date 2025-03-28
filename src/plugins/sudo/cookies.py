#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from typing import List

from pyrogram import filters
from pyrogram.types import (
    Message,
)
from cookies._cookies.fetchCookies import save_all_cookies

from src import bot
from src.logging import LOGGER
from src.helpers.filters import dev_cmd

from src.helpers.dlp.yt_dl.ytdl_core import cookie_manager

@bot.on_message(filters.command(["cookie", "cookies"]) & dev_cmd)
async def shell_executor(_, message: Message):
    """Executes command in terminal via bot."""

    if len(message.command) < 2:
        cookies_usage = "**USAGE:** Adds cookies directly to the bot.\n\n**Example: **<pre>/cookies <paste_bin_url> with base64 encoded data in that/pre>"
        return await message.reply_text(cookies_usage, quote=True)

    args = parse_cmd_args(message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else '')
    msg = await message.reply_text(f"♔ **Processing Url:** __{args}__",quote=True)

    try:
    
        result = await save_all_cookies(args)
        new_cookie_count = await cookie_manager.refresh_cookies()
        msg = await msg.edit_text(f"♔ **The cookies saved to:** __{',\n'.join(result)}__\n\n♔ **The total Cookies now is:** __{new_cookie_count}__\n\n use `/shell ls cookies`to verify it.")
    except Exception as error:
        LOGGER(__name__).warning(f"{error}")
        return await msg.edit(f"--♔ **Error**--\n\n`{error}`")



def parse_cmd_args(message: str, separator: str = ',') -> List[str]:
    """
    Parse command arguments from a message string.
    
    Args:
        message (str): The full message string after the command.
        separator (str, optional): The separator used to split arguments. Defaults to ','.
    
    Returns:
        List[str]: A list of parsed arguments. Returns an empty list if no arguments are provided.
    """
    # Strip any leading/trailing whitespace
    cleaned_message = message.strip()
    
    # If the message is empty, return an empty list
    if not cleaned_message:
        return []
    
    # Split the message using the specified separator
    return [arg.strip() for arg in cleaned_message.split(separator)]
