# src/plugins/users/start.py
#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                            InlineKeyboardMarkup, InputMediaPhoto, Message)

from src import bot
from src.config import OWNER_USERID, SUDO_USERID
from src.database import database
from src.helpers.filters import (is_download_callback_rate_limited,
                                 is_rate_limited)
from src.helpers.start_constants import (ABOUT_CAPTION, COMMAND_CAPTION,
                                         DEV_TEXT, DLP_TEXT, QUICKDL_BANNER,
                                         RKGROUP_LOGO, START_CAPTION,
                                         SUDO_TEXT, USER_TEXT)

# ──────────────────────────────────────────────
#  Keyboard layouts
# ──────────────────────────────────────────────

START_BUTTON = [
    [
        InlineKeyboardButton("⌤ Commands", callback_data="COMMAND_BUTTON"),
        InlineKeyboardButton("∴ About me",  callback_data="ABOUT_BUTTON"),
    ],
    [
        InlineKeyboardButton("♚ Need Help", url="https://t.me/Rkgroup_helpbot?start=start"),
    ],
    [
        InlineKeyboardButton("♔ Updates", url="https://t.me/rkgroup_update"),
    ],
]

COMMAND_BUTTON = [
    [InlineKeyboardButton("⚜ DLP",          callback_data="DLP_BUTTON")],
    [
        InlineKeyboardButton("⚜ Users",      callback_data="USER_BUTTON"),
        InlineKeyboardButton("⚜ Sudo",       callback_data="SUDO_BUTTON"),
    ],
    [
        InlineKeyboardButton("⚜ Developer",  callback_data="DEV_BUTTON"),
        InlineKeyboardButton("⚜ Inline",     switch_inline_query=""),
    ],
    [InlineKeyboardButton("⚜ How to use?",  url="https://telegra.ph/Quickl-Dl-03-28")],
    [InlineKeyboardButton("◄ Go Back",       callback_data="START_BUTTON")],
]

ABOUT_ME_BUTTON = [
    [InlineKeyboardButton("♔ Source",          url="https://github.com/RKgroupkg/Telegram-AllDlp-Bot")],
    [InlineKeyboardButton("♧ Privacy Policy",  url="https://telegra.ph/Quick-Dl-03-25")],
    [InlineKeyboardButton("♧ Code Of Conduct", url="https://telegra.ph/Quick-Dl-03-25-2")],
    [InlineKeyboardButton("◄ Go Back",         callback_data="START_BUTTON_ABOUTME")],
]

GOBACK_1_BUTTON = [[InlineKeyboardButton("◄ Go Back", callback_data="START_BUTTON")]]
GOBACK_2_BUTTON = [[InlineKeyboardButton("◄ Go Back", callback_data="COMMAND_BUTTON")]]


# ──────────────────────────────────────────────
#  /start  /help
# ──────────────────────────────────────────────

@bot.on_message(filters.command(["start", "help"]) & is_rate_limited)
async def start(_, message: Message):
    is_new_user = not await database.user_exists(message.from_user)
    await database.save_user(message.from_user)

    caption = START_CAPTION
    if is_new_user:
        caption += (
            "\n\n∷ **First time here?**\n"
            "Tap **⌤ Commands** to explore, or drop any supported link here and I will handle the rest."
        )

    await message.reply_photo(
        photo=QUICKDL_BANNER,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(START_BUTTON),
        quote=True,
    )


# ──────────────────────────────────────────────
#  Callback router
# ──────────────────────────────────────────────

@bot.on_callback_query(filters.regex("_BUTTON") & is_download_callback_rate_limited)
async def botCallbacks(_, callback: CallbackQuery):
    clicker_id = callback.from_user.id
    owner_id   = callback.message.reply_to_message.from_user.id

    if clicker_id != owner_id:
        return await callback.answer(
            "This command was not initiated by you.", show_alert=True
        )

    data = callback.data

    if data == "SUDO_BUTTON":
        if clicker_id not in SUDO_USERID:
            return await callback.answer(
                "You are not in the sudo user list.", show_alert=True
            )
        return await callback.edit_message_text(
            SUDO_TEXT, reply_markup=InlineKeyboardMarkup(GOBACK_2_BUTTON)
        )

    if data == "DEV_BUTTON":
        if clicker_id not in OWNER_USERID:
            return await callback.answer(
                "This is a developer-restricted section.", show_alert=True
            )
        return await callback.edit_message_text(
            DEV_TEXT, reply_markup=InlineKeyboardMarkup(GOBACK_2_BUTTON)
        )

    if data == "ABOUT_BUTTON":
        await callback.edit_message_media(
            media=InputMediaPhoto(media=RKGROUP_LOGO, caption=ABOUT_CAPTION),
            reply_markup=InlineKeyboardMarkup(ABOUT_ME_BUTTON),
        )

    elif data == "START_BUTTON":
        await callback.edit_message_text(
            START_CAPTION, reply_markup=InlineKeyboardMarkup(START_BUTTON)
        )

    elif data == "START_BUTTON_ABOUTME":
        await callback.edit_message_media(
            media=InputMediaPhoto(media=QUICKDL_BANNER, caption=START_CAPTION),
            reply_markup=InlineKeyboardMarkup(START_BUTTON),
        )

    elif data == "COMMAND_BUTTON":
        await callback.edit_message_text(
            COMMAND_CAPTION, reply_markup=InlineKeyboardMarkup(COMMAND_BUTTON)
        )

    elif data == "USER_BUTTON":
        await callback.edit_message_text(
            USER_TEXT, reply_markup=InlineKeyboardMarkup(GOBACK_2_BUTTON)
        )

    elif data == "DLP_BUTTON":
        await callback.edit_message_text(
            DLP_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(GOBACK_2_BUTTON),
        )

    await callback.answer()


# ──────────────────────────────────────────────
#  Group join handler
# ──────────────────────────────────────────────

@bot.on_message(filters.new_chat_members, group=1)
async def new_chat(_, message: Message):
    """Save group chat_id to the database when the bot is added."""
    for member in message.new_chat_members:
        if member.id == bot.me.id:
            await database.save_chat(message.chat.id)
            break
