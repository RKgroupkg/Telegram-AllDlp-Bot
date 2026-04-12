# File: src/plugins/sudo/cookies.py
#  Copyright (c) 2025 Rkgroup.
#  Quick DL is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.

from __future__ import annotations
from typing import List, Optional
import re
import asyncio

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from cookies._cookies.fetchCookies import save_all_cookies
from src import bot
from src.helpers.dlp.yt_dl.ytdl_core import cookie_manager
from src.helpers.filters import dev_cmd
from src.logging import LOGGER


# ----------------------------
# Utility Functions
# ----------------------------

def parse_cmd_args(message: str, separator: str = ",") -> List[str]:
    """
    Parse command arguments from a message string.

    Args:
        message (str): The full message string after the command.
        separator (str, optional): The separator used to split arguments. Defaults to ','.

    Returns:
        List[str]: A list of parsed arguments.
    """
    cleaned_message = message.strip()
    if not cleaned_message:
        return []
    return [arg.strip() for arg in cleaned_message.split(separator) if arg.strip()]


def extract_url(text: str) -> Optional[str]:
    """Extracts the first valid URL from text (for pastebin/gist/etc)."""
    url_pattern = r"(https?://[^\s]+)"
    matches = re.findall(url_pattern, text)
    return matches[0] if matches else None


# ----------------------------
# Core Bot Handler
# ----------------------------

@bot.on_message(filters.command(["cookie", "cookies"]) & dev_cmd)
async def cookie_handler(_, message: Message):
    """
    Handle cookie import via /cookies command.
    
    Usage:
        /cookies <pastebin_or_url_with_base64_data>
    """
    if len(message.command) < 2:
        usage_text = (
            "🍪 **Usage:** Adds cookies directly to the bot.\n\n"
            "**Example:**\n"
            "`/cookies https://pastebin.com/raw/xxxxx`\n\n"
            "Ensure the link contains base64-encoded cookie data."
        )
        return await message.reply_text(usage_text, quote=True)

    args_text = message.text.split(maxsplit=1)[1]
    urls = parse_cmd_args(args_text)

    if not urls:
        return await message.reply_text("⚠️ No valid URLs provided.", quote=True)

    msg = await message.reply_text("🔄 **Fetching and saving cookies...**", quote=True)
    processed_results = []
    success_count = 0
    fail_count = 0

    # Sequential or parallel cookie loading
    for url in urls:
        url_to_process = extract_url(url) or url
        try:
            await asyncio.sleep(1)  # simulate processing delay
            result = await save_all_cookies(url_to_process)
            success_count += 1
            processed_results.extend(result)
        except Exception as e:
            fail_count += 1
            LOGGER(__name__).warning(f"Failed to save cookies from {url_to_process}: {e}")

    try:
        total_cookies = await cookie_manager.refresh_cookies()
    except Exception as refresh_err:
        LOGGER(__name__).error(f"Cookie refresh failed: {refresh_err}")
        total_cookies = "Unknown"

    cookies_summary = (
        f"✅ **Saved:** {success_count} | ❌ **Failed:** {fail_count}\n\n"
        f"📦 **Total cookies now:** `{total_cookies}`\n"
        f"🗂️ Saved to: `{', '.join(processed_results) if processed_results else 'N/A'}`"
    )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🧩 Verify cookies", callback_data="verify_cookies")]]
    )

    await msg.edit_text(
        f"🍪 **Cookie Import Summary**\n\n{cookies_summary}\n\n"
        "_Use_ `/shell ls cookies` _to verify manually._",
        reply_markup=keyboard,
    )


# ----------------------------
# Optional Callback Handler
# ----------------------------

@bot.on_callback_query(filters.regex("^verify_cookies$"))
async def verify_cookies_cb(_, query):
    """Responds to the verify cookies button."""
    await query.answer("🔍 Checking cookies...")
    try:
        count = await cookie_manager.refresh_cookies()
        await query.edit_message_text(f"✅ **Total cookies currently loaded:** `{count}`")
    except Exception as e:
        LOGGER(__name__).error(f"Verification error: {e}")
        await query.edit_message_text(f"⚠️ Error verifying cookies:\n`{e}`")
