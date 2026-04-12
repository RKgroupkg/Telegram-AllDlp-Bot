# File: src/plugins/sudo/log.py
#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
# --------------------------------------------------------------------------- #
#                             Log Management Panel                            #
# --------------------------------------------------------------------------- #

import os
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from PIL import Image, ImageDraw, ImageFont

from src import bot
from src.helpers.filters import sudo_cmd
from src.logging import LOGGER

log = LOGGER(__name__)

LOG_FILE = "logs.txt"


def ensure_log_file() -> None:
    """Ensure log file exists."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write("[Log file created]\n")


# --------------------------------------------------------------------------- #
#                            Log File Screenshot                              #
# --------------------------------------------------------------------------- #

def render_log_as_image(path: str) -> str:
    """Render a log file as an image and return its path."""
    try:
        with open(path, "r") as f:
            lines = f.readlines()[-50:]  # last 50 lines
    except Exception:
        lines = ["<Unable to read logs>"]

    # Basic image styling
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    font = ImageFont.truetype(font_path, 14)
    width, height = 1000, max(400, 20 * len(lines) + 40)
    img = Image.new("RGB", (width, height), color=(20, 20, 20))
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([(0, 0), (width, 30)], fill=(35, 35, 35))
    draw.text((10, 7), "Quick DL - Recent Log Snapshot", font=font, fill=(220, 220, 220))

    # Content
    y = 40
    for line in lines:
        draw.text((10, y), line.strip(), font=font, fill=(180, 180, 180))
        y += 18

    out_path = "log_preview.png"
    img.save(out_path)
    return out_path


# --------------------------------------------------------------------------- #
#                               Command Handler                               #
# --------------------------------------------------------------------------- #

@bot.on_message(filters.command(["log", "logs"]) & sudo_cmd)
async def log_panel(_, message: Message):
    """Main log management control panel."""
    ensure_log_file()

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("1. View Logs", callback_data="log_view")],
            [InlineKeyboardButton("2. Download Logs", callback_data="log_file")],
            [InlineKeyboardButton("3. Get as Image", callback_data="log_pic")],
            [InlineKeyboardButton("4. Clear Logs", callback_data="log_clear")],
            [InlineKeyboardButton("Close", callback_data="log_close")],
        ]
    )

    await message.reply_text(
        "**[ Log Management Panel ]**\n\n"
        "Choose an action:\n"
        "──────────────────────────────\n"
        "  [1] View last 40 lines\n"
        "  [2] Download logs as text file\n"
        "  [3] Get visual image preview\n"
        "  [4] Clear all logs\n"
        "──────────────────────────────",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )


# --------------------------------------------------------------------------- #
#                             Callback Handlers                               #
# --------------------------------------------------------------------------- #

@bot.on_callback_query(filters.regex("^log_view$"))
async def cb_view_logs(_, query: CallbackQuery):
    ensure_log_file()
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()[-40:]
        content = "".join(lines).strip() or "(empty)"
        text = f"**[ Log Preview — Last 40 Lines ]**\n\n```{content[-3500:]}```"
        await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await query.message.edit_text(f"✗ Failed to read logs:\n`{e}`", parse_mode=ParseMode.MARKDOWN)


@bot.on_callback_query(filters.regex("^log_file$"))
async def cb_file_logs(_, query: CallbackQuery):
    ensure_log_file()
    try:
        await query.message.reply_document(LOG_FILE, caption="logs.txt")
    except Exception as e:
        await query.message.edit_text(f"✗ Error sending file:\n`{e}`", parse_mode=ParseMode.MARKDOWN)


@bot.on_callback_query(filters.regex("^log_pic$"))
async def cb_picture_logs(_, query: CallbackQuery):
    ensure_log_file()
    try:
        img_path = render_log_as_image(LOG_FILE)
        await query.message.reply_photo(img_path, caption="Log Snapshot (Last 50 lines)")
        os.remove(img_path)
    except Exception as e:
        await query.message.edit_text(f"✗ Failed to generate image:\n`{e}`", parse_mode=ParseMode.MARKDOWN)


@bot.on_callback_query(filters.regex("^log_clear$"))
async def cb_clear_confirm(_, query: CallbackQuery):
    """Ask for confirmation before clearing logs."""
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Deletion", callback_data="log_clear_yes")],
            [InlineKeyboardButton("Cancel", callback_data="log_close")],
        ]
    )
    await query.message.edit_text(
        "**[ Confirm Log Deletion ]**\n\n"
        "This will remove all contents from `logs.txt`.\n"
        "Are you sure you want to proceed?",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )


@bot.on_callback_query(filters.regex("^log_clear_yes$"))
async def cb_clear_logs(_, query: CallbackQuery):
    """Clear logs after confirmation."""
    ensure_log_file()
    try:
        open(LOG_FILE, "w").close()
        await query.message.edit_text("✓ Logs have been cleared successfully.")
    except Exception as e:
        await query.message.edit_text(f"✗ Failed to clear logs:\n`{e}`", parse_mode=ParseMode.MARKDOWN)


@bot.on_callback_query(filters.regex("^log_close$"))
async def cb_log_close(_, query: CallbackQuery):
    """Close log interface."""
    await query.message.delete()
