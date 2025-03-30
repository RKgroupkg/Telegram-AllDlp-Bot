# Copyright (c) 2025 Rkgroup.
# Quick Dl is an open-source Downloader bot licensed under MIT.
# All rights reserved where applicable.

import os

import aiofiles
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from src import bot
from src.helpers.filters import (is_download_callback_rate_limited,
                                 is_rate_limited)
from src.helpers.pasting_services import (katbin_paste, telegraph_image_paste,
                                          telegraph_paste)


@bot.on_message(filters.command("paste") & is_rate_limited)
async def paste(_, message: Message):
    """Handles pasting of text or images with interactive options."""
    paste_usage = "♚ **Usage:** Paste text or image. Reply to a text file, text message, image, or type text after the command.\n\n**Example:** /paste type your text"
    paste_reply = await message.reply_text("processing...", quote=True)
    replied_message = message.reply_to_message

    if replied_message:
        # Handle image pasting (photo or document with image mime_type)
        if replied_message.photo or (
            replied_message.document and "image" in replied_message.document.mime_type
        ):
            try:
                file_path = await replied_message.download()
                output = await telegraph_image_paste(file_path)
                os.remove(file_path)
                await paste_reply.edit(output)
            except Exception as e:
                await paste_reply.edit(f"Failed to paste image: {e}")
            return

        # Handle text pasting (text or text file)
        elif replied_message.text or (
            replied_message.document
            and any(
                format in replied_message.document.mime_type
                for format in {"text", "json"}
            )
        ):
            buttons = [
                [
                    InlineKeyboardButton("◍ Katb.in", callback_data="paste_katbin"),
                    InlineKeyboardButton(
                        "◍ Telegraph", callback_data="paste_telegraph"
                    ),
                ]
            ]
            await paste_reply.edit(
                "Choose paste service:", reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        else:
            await paste_reply.edit(paste_usage)
            return

    # Handle direct text input with the command
    elif len(message.command) > 1:
        buttons = [
            [
                InlineKeyboardButton("◍ Katb.in", callback_data="paste_katbin"),
                InlineKeyboardButton("◍ Telegraph", callback_data="paste_telegraph"),
            ]
        ]
        await paste_reply.edit(
            "♔ Choose paste service:", reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    else:
        await paste_reply.edit(paste_usage)


@bot.on_callback_query(filters.regex("paste_") & is_download_callback_rate_limited)
async def paste_callback(client, callback_query):
    """Handles callback queries from paste service selection buttons."""
    data = callback_query.data
    if data == "paste_katbin":
        paste_func = katbin_paste
        service_name = "Katb.in"
    elif data == "paste_telegraph":
        paste_func = telegraph_paste
        service_name = "Telegraph"
    else:
        return

    original_message = callback_query.message.reply_to_message
    content = None

    # Extract content based on whether it’s a reply or direct command
    if original_message.reply_to_message:
        replied = original_message.reply_to_message
        if replied.text:
            content = replied.text
        elif replied.document and any(
            format in replied.document.mime_type for format in {"text", "json"}
        ):
            try:
                file_path = await replied.download()
                async with aiofiles.open(file_path, "r+") as file:
                    content = await file.read()
                os.remove(file_path)
            except Exception as e:
                await callback_query.message.edit_text(f"Failed to read file: {e}")
                return
    else:
        if len(original_message.command) > 1:
            content = original_message.text.split(None, 1)[1]

    if not content:
        await callback_query.message.edit_text("No content to paste.")
        return

    # Paste the content and update the message
    try:
        output = await paste_func(content)
        button = [
            [InlineKeyboardButton(text=f"♔ Pasted to {service_name} ", url=output)]
        ]
        await callback_query.message.edit_text(
            output,
            reply_markup=InlineKeyboardMarkup(button),
            disable_web_page_preview=True,
        )
    except Exception as e:
        await callback_query.message.edit_text(
            f"Failed to paste to {service_name}: {e}"
        )
