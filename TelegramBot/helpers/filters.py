"""
Creating custom filters.
https://docs.pyrogram.org/topics/create-filters
"""

from typing import Union
from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message, CallbackQuery
from TelegramBot.helpers.ratelimiter import RateLimiter
from TelegramBot.config import SUDO_USERID, OWNER_USERID


from TelegramBot.logging import LOGGER
logger = LOGGER(__name__)

# command authorizations filters.
def dev_users(_, __, message: Message) -> bool:
    return message.from_user.id in OWNER_USERID if message.from_user else False


def sudo_users(_, __, message: Message) -> bool:
    return message.from_user.id in SUDO_USERID if message.from_user else False


# ratelimit filter

chatid_ratelimiter = RateLimiter(limit_sec=1,limit_min=20,interval_sec=1,interval_min=60)
global_ratelimiter = RateLimiter(limit_sec=30,limit_min=1800,interval_sec=1,interval_min=60)
dl_ratelimiter = RateLimiter(limit_sec=1,limit_min=5,interval_sec=1,interval_min=60)


async def ratelimiter(_, __, update: Union[Message, CallbackQuery]) -> bool:
    """
    This filter will monitor the new messages or callback queries updates and ignore them if the
    bot is about to hit the rate limit.

    Telegram Official Rate Limits: 20msg/minute in same group, 30msg/second globally for all groups/users.
    Additionally There is no mention of rate limit in  bot's private message so we will ignore in this filter.

    You can customize the rate limit according to your needs and add user specific rate limit too.

    https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this
    https://telegra.ph/So-your-bot-is-rate-limited-01-26

    params:
        update (`Message | CallbackQuery`): The update to check for rate limit.

    returns:
        bool: True if the bot is not about to hit the rate limit, False otherwise.
    """

    is_global_limited = await global_ratelimiter.acquire("globalupdate")

    if is_global_limited:
        logger.info(f"Global Ratelimit hit while processing: {chatid}")
        return False

    chatid = update.chat.id if isinstance(update, Message) else update.message.chat.id
    chat_type = update.chat.type if isinstance(update, Message) else update.message.chat.type

    if chat_type != ChatType.PRIVATE:
        is_chatid_limited = await chatid_ratelimiter.acquire(chatid)

        if is_chatid_limited:
            if isinstance(update, CallbackQuery):
                await update.answer("Bot is getting too many requests, please try again later.", show_alert=True)
            logger.info(f"Chat Ratelimit hit for: {chatid}")
            return False

    return True


async def ratelimiter_dl(_, __, update: Union[Message, CallbackQuery]) -> bool:
    """
    This filter will monitor the new messages or callback queries updates and ignore them if the
    bot is about to hit the rate limit.
    https://telegra.ph/So-your-bot-is-rate-limited-01-26

    params:
        update (`Message | CallbackQuery`): The update to check for rate limit.

    returns:
        bool: True if the bot is not about to hit the rate limit, False otherwise.
    """

    is_global_limited = await global_ratelimiter.acquire("globalupdate")

    if is_global_limited:
        logger.info(f"Global Ratelimit hit while processing: {chatid}")
        return False

    chatid = update.chat.id if isinstance(update, Message) else update.message.chat.id
    chat_type = update.chat.type if isinstance(update, Message) else update.message.chat.type

    if chat_type != ChatType.PRIVATE:
        is_chatid_limited_dl = await dl_ratelimiter.acquire(chatid)
        is_chatid_limited = await chatid_ratelimiter.acquire(chatid)

        if is_chatid_limited_dl:
            if isinstance(update, CallbackQuery):
                await update.answer("You have reached the limit. Please try again in few minutes.", show_alert=True)
            elif isinstance(update, Message):
                await update.reply_text("You have reached the limit. Please try again in few minutes.", quote=True)
            logger.info(f"Chat dl Ratelimit hit for: {chatid}")
            return False
        elif is_chatid_limited:
            if isinstance(update, CallbackQuery):
                logger.info(f"Chat Ratelimit hit for: {chatid}")
                await update.answer("Bot is getting too many requests, please try again later.", show_alert=True)
            return False


    return True


# creating filters.
dev_cmd = filters.create(dev_users)
sudo_cmd = filters.create(sudo_users)
is_ratelimited = filters.create(ratelimiter)
is_ratelimiter_dl = filters.create(ratelimiter_dl)