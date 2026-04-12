# File: src/plugins/users/info.py
#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from pyrogram import Client, filters
from pyrogram.types import Message

from src.helpers.filters import is_rate_limited


@Client.on_message(filters.command(["id"]) & is_rate_limited)
async def get_id_info(client: Client, message: Message):
    """
    Plugin that provides detailed information about a message or user
    when the /id command is used.
    """
    # Check if the message is a reply
    if message.reply_to_message:
        target_message = message.reply_to_message
        target_user = target_message.from_user
    else:
        target_message = message
        target_user = message.from_user

    # Get chat information
    chat_info = f"`{message.chat.id}`" if message.chat else "N/A"
    chat_type = message.chat.type if message.chat else "N/A"

    # Get user information
    user_id = f"`{target_user.id}`" if target_user else "N/A"
    first_name = target_user.first_name if target_user else "N/A"
    last_name = (
        target_user.last_name if target_user and target_user.last_name else "None"
    )
    username = (
        f"@{target_user.username}" if target_user and target_user.username else "None"
    )

    # Get message information
    message_id = f"`{target_message.id}`"
    date = (
        target_message.date.strftime("%Y-%m-%d %H:%M:%S")
        if target_message.date
        else "N/A"
    )

    # Prepare the response in markdown format
    response = (
        f"♚ **𝙼𝚎𝚜𝚜𝚊𝚐𝚎 𝙸𝚗𝚏𝚘𝚛𝚖𝚊𝚝𝚒𝚘𝚗**\n\n"
        f"⟢ **Message ID:** {message_id}\n"
        f"⟢ **Date:** `{date}`\n\n"
        f"⟢ **User Information**\n\n"
        f"⟢ **User ID:** {user_id}\n"
        f"⟢ **First Name:** `{first_name}`\n"
        f"⟢ **Last Name:** `{last_name}`\n"
        f"⟢ **Username:** `{username}`\n\n"
        f"⟢ **Chat Information**\n\n"
        f"⟢ **Chat ID:** {chat_info}\n"
        f"⟢ **Chat Type:** `{chat_type}`\n"
    )

    # Add forwarded information if available
    if target_message.forward_from or target_message.forward_from_chat:
        forward_from = target_message.forward_from
        forward_from_chat = target_message.forward_from_chat

        response += "\n**𝙵𝚘𝚛𝚠𝚊𝚛𝚍𝚎𝚍 𝙵𝚛𝚘𝚖:**\n\n"

        if forward_from:
            f_user_id = f"`{forward_from.id}`"
            f_first_name = forward_from.first_name
            f_last_name = forward_from.last_name if forward_from.last_name else "None"
            f_username = (
                f"@{forward_from.username}" if forward_from.username else "None"
            )

            response += (
                f"⟢ **User ID:** {f_user_id}\n"
                f"⟢ **First Name:** `{f_first_name}`\n"
                f"⟢ **Last Name:** `{f_last_name}`\n"
                f"⟢ **Username:** `{f_username}`\n"
            )

        if forward_from_chat:
            f_chat_id = f"`{forward_from_chat.id}`"
            f_chat_title = forward_from_chat.title
            f_chat_type = forward_from_chat.type

            response += (
                f"⟢ **Chat ID:** {f_chat_id}\n"
                f"⟢ **Chat Title:** `{f_chat_title}`\n"
                f"⟢ **Chat Type:** `{f_chat_type}`\n"
            )

    # Add file information if message contains media
    if hasattr(target_message, "document") and target_message.document:
        file_id = f"`{target_message.document.file_id}`"
        file_name = (
            target_message.document.file_name
            if target_message.document.file_name
            else "N/A"
        )
        file_size = (
            f"{target_message.document.file_size / 1024:.2f} KB"
            if target_message.document.file_size
            else "N/A"
        )

        response += (
            f"\n**𝙵𝚒𝚕𝚎 𝙸𝚗𝚏𝚘𝚛𝚖𝚊𝚝𝚒𝚘𝚗**\n\n"
            f"⟢ **File ID:** {file_id}\n"
            f"⟢ **File Name:** `{file_name}`\n"
            f"⟢ **File Size:** `{file_size}`\n"
        )

    # Send the response with a disable_web_page_preview to avoid unwanted previews
    return await message.reply_text(
        response,
        disable_web_page_preview=True,
        quote=True,  # Reply to the original message
    )
