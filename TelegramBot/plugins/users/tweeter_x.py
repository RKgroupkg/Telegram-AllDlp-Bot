from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ParseMode

from TelegramBot.helpers.filters import is_ratelimited,is_ratelimiter_dl
from TelegramBot.helpers.start_constants import BOT_NAME  # bot name
from TelegramBot.logging import LOGGER
logger = LOGGER(__name__)

# Current not working 

# @Client.on_message(filters.regex(r'https?://.*twitter[^\s]+') & filters.incoming | filters.regex(r'https?://(?:www\.)?x\.com/\S+') & filters.incoming)
async def twitter_handler(client: Client, message: Message):
    try:
        msg = await message.reply_text("۞ **Processing** __the link__...")
        link=message.matches[0].group(0)
        origanl_link = link
        if "x.com" in link:
         link=link.replace("x.com","fxtwitter.com")
        elif "twitter.com" in link:
         link = link.replace("twitter.com","fxtwitter.com")

        Send_media = await message.reply_video(
           link,
           caption=f"❀ __via__ {BOT_NAME}",
           quote = True,
           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("♙ Open Tweetter ♙", url=origanl_link)]]
                                             )
                                                                                                               )
    except Exception as e:
        logger.error(f"Error in sending music results: {str(e)}")
        await msg.edit_text(
            f"<b>⚠ Display Error</b>\n{str(e)}\n\n Link:- <a herf='{link}'>x</a>",
            parse_mode=ParseMode.HTML
        )


