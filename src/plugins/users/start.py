#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from pyrogram.types import InputMediaPhoto

from src import bot
from src.database import database
from src.helpers.filters import is_ratelimited
from src.config import OWNER_USERID, SUDO_USERID
from src.helpers.start_constants import (
    START_CAPTION,
    USER_TEXT,
    COMMAND_CAPTION,
    ABOUT_CAPTION,
    DEV_TEXT,
    SUDO_TEXT,
    DLP_TEXT,
    QUICKDL_BANNER,
    QUICKDL_LOGO,
    RKGROUP_LOGO,
)


START_BUTTON = [
    [
        InlineKeyboardButton("⌤ Commands", callback_data="COMMAND_BUTTON"),
        InlineKeyboardButton("∴ About me", callback_data="ABOUT_BUTTON"),
    ],
    [
        InlineKeyboardButton(
            "♚ Need Help",
            url="https://t.me/Rkgroup_helpbot?start=start",
        )
    ],
    [
        InlineKeyboardButton(
            "♔ Updates",
            url="https://t.me/rkgroup_update",
        )
    ],

]


COMMAND_BUTTON = [
    [
        InlineKeyboardButton("⚜ DLP", callback_data="DLP_BUTTON")
    ],
    [
        InlineKeyboardButton("⚜ Users", callback_data="USER_BUTTON"),
        InlineKeyboardButton("⚜ Sudo", callback_data="SUDO_BUTTON"),
    ],
    [InlineKeyboardButton("⚜ Developer", callback_data="DEV_BUTTON"),
     InlineKeyboardButton("⚜ Inline", switch_inline_query="")
    ],
    [InlineKeyboardButton("⚜ How to use?", url="https://telegra.ph/Quickl-Dl-03-28")],
    [InlineKeyboardButton("◄ Go Back", callback_data="START_BUTTON")],
]

ABOUT_ME_BUTTON =[
    [    InlineKeyboardButton(
            "♔ Source",
            url="https://github.com/RKgroupkg/Telegram-AllDlp-Bot",
        )
    ],
    [    InlineKeyboardButton(
            "♧ Privacy Policy",
            url="https://telegra.ph/Quick-Dl-03-25",
        ),
    ],
    [
        InlineKeyboardButton(
            "♧ Code Of Conduct",
            url="https://telegra.ph/Quick-Dl-03-25-2",
        )
   ],
    [
        InlineKeyboardButton("◄ Go Back", callback_data="START_BUTTON_ABOUTME")
    ],
    ]


GOBACK_1_BUTTON = [[InlineKeyboardButton("◄ Go Back", callback_data="START_BUTTON")]]
GOBACK_2_BUTTON = [[InlineKeyboardButton("◄ Go Back", callback_data="COMMAND_BUTTON")]]


@bot.on_message(filters.command(["start", "help"]) & is_ratelimited)
async def start(_, message: Message):
    await database.save_user(message.from_user)
        
    return await message.reply_photo(
        photo = QUICKDL_BANNER,
        caption = START_CAPTION,
        reply_markup=InlineKeyboardMarkup(START_BUTTON),
        quote=True
    )


@bot.on_callback_query(filters.regex("_BUTTON"))
async def botCallbacks(_, CallbackQuery: CallbackQuery):

    clicker_user_id = CallbackQuery.from_user.id
    user_id = CallbackQuery.message.reply_to_message.from_user.id

    if clicker_user_id != user_id:
        return await CallbackQuery.answer(
            "This command is not initiated by you.", show_alert=True
        )

    if CallbackQuery.data == "SUDO_BUTTON":
        if clicker_user_id not in SUDO_USERID:
            return await CallbackQuery.answer(
                "You are not in the sudo user list.", show_alert=True
            )
        await CallbackQuery.edit_message_text(
            SUDO_TEXT, reply_markup=InlineKeyboardMarkup(GOBACK_2_BUTTON)
        )

    elif CallbackQuery.data == "DEV_BUTTON":
        if clicker_user_id not in OWNER_USERID:
            return await CallbackQuery.answer(
                "This is developer restricted command.", show_alert=True
            )
        await CallbackQuery.edit_message_text(
            DEV_TEXT, reply_markup=InlineKeyboardMarkup(GOBACK_2_BUTTON)
        )

    if CallbackQuery.data == "ABOUT_BUTTON":
        await CallbackQuery.edit_message_media(
            media= InputMediaPhoto( media=RKGROUP_LOGO,caption=ABOUT_CAPTION),
            reply_markup = InlineKeyboardMarkup(ABOUT_ME_BUTTON),
        )

    elif CallbackQuery.data == "START_BUTTON":
        await CallbackQuery.edit_message_text(
            START_CAPTION, reply_markup=InlineKeyboardMarkup(START_BUTTON)
        )
    elif CallbackQuery.data == "START_BUTTON_ABOUTME":
        await CallbackQuery.edit_message_media(
            media= InputMediaPhoto(media=QUICKDL_BANNER,caption=START_CAPTION),
            reply_markup = InlineKeyboardMarkup(START_BUTTON),
        )



    elif CallbackQuery.data == "COMMAND_BUTTON":
        await CallbackQuery.edit_message_text(
            COMMAND_CAPTION, reply_markup=InlineKeyboardMarkup(COMMAND_BUTTON)
        )

    elif CallbackQuery.data == "USER_BUTTON":
        await CallbackQuery.edit_message_text(
            USER_TEXT, reply_markup=InlineKeyboardMarkup(GOBACK_2_BUTTON)
        )
    elif CallbackQuery.data == "DLP_BUTTON":
        await CallbackQuery.edit_message_text(
            DLP_TEXT,
            parse_mode = ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(GOBACK_2_BUTTON)
        )
    await CallbackQuery.answer()


@bot.on_message(filters.new_chat_members, group=1)
async def new_chat(_, message: Message):
    """
    Get notified when someone add bot in the group,
    then it saves that group chat_id in the database.
    """

    chatid = message.chat.id
    for new_user in message.new_chat_members:
        if new_user.id == bot.me.id:
            await database.save_chat(chatid)
    
