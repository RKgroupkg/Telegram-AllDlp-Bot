#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

"""
Creating custom filters.
https://docs.pyrogram.org/topics/create-filters
"""
import re
from typing import Union
from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message, CallbackQuery
from src.helpers.ratelimiter import RateLimiter
from src.config import SUDO_USERID, OWNER_USERID
import time

from urllib.parse import urlparse
from typing import Callable, Optional, Union, List, Dict, Any
import functools

from src.helpers.dlp._rex import LINK_REGEX_PATTERNS
import yt_dlp
from src.logging import LOGGER
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


def Main_supportedDlUrl(_, __, message):
    """
    This filter returns True if the message text does NOT match any of the specified link patterns.
    If any pattern matches, it returns False.
    """
    text = message.text or ""
    for pattern in LINK_REGEX_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    return True

class YtdlpUrlFilter:
    """A filter for Pyrogram to check if a message contains a valid URL supported by yt-dlp."""
    
    # Common URL regex pattern
    URL_PATTERN = re.compile(
        r'(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|'
        r'www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|'
        r'https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|'
        r'www\.[a-zA-Z0-9]+\.[^\s]{2,})'
    )
    
    # Cache for domain validation results to avoid repeated checks
    _supported_domains_cache: Dict[str, bool] = {}
    
    # Cache expiration time (in seconds)
    _cache_expiry = 86400  # 24 hours
    
    # Store common domain patterns from extractors (populated in initialize_domain_patterns)
    _common_domain_patterns: List[re.Pattern] = []
    
    # Store initialization time
    _initialized = False
    
    @classmethod
    def is_supported_url(cls, url: str) -> bool:
        """
        Check if the URL is supported by yt-dlp.
        
        Args:
            url: The URL to check
            
        Returns:
            bool: True if the URL is supported, False otherwise
        """
        try:
            # Try to get domain from URL
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            # Handle URLs without scheme
            if not domain and url.startswith("www."):
                domain = url.split("/")[0]
                url = f"http://{url}"
            elif not domain:
                # Try to fix the URL if it doesn't have a scheme
                if "." in url and "/" in url:
                    domain = url.split("/")[0]
                    url = f"http://{url}"
                else:
                    return False
            
            # Check cache first
            if domain in cls._supported_domains_cache:
                return cls._supported_domains_cache[domain]
            
            # Quick check using common domain patterns (if initialized)
            if cls._common_domain_patterns:
                for pattern in cls._common_domain_patterns:
                    if pattern.search(domain):
                        cls._supported_domains_cache[domain] = True
                        return True
            
            # Full extraction test as fallback
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "skip_download": True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Use extract_info with process=False to just check if the URL is recognized
                # This is much faster than trying to fully process the URL
                try:
                    ydl.extract_info(url, download=False, process=False)
                    cls._supported_domains_cache[domain] = True
                    return True
                except yt_dlp.utils.UnsupportedError:
                    cls._supported_domains_cache[domain] = False
                    return False
                except yt_dlp.utils.ExtractorError:
                    # If we get an extractor error, that means an extractor was found
                    # but there was an issue with the specific URL. Consider this supported.
                    cls._supported_domains_cache[domain] = True
                    return True
                except yt_dlp.utils.DownloadError:
                    cls._supported_domains_cache[domain] = False
                    return False
                
        except Exception as e:
            logger.error(f"Error checking URL {url}: {str(e)}")
            return False
    
    @classmethod
    def extract_urls(cls, text: str) -> List[str]:
        """
        Extract all URLs from a text.
        
        Args:
            text: The text to extract URLs from
            
        Returns:
            List[str]: List of extracted URLs
        """
        if not text:
            return []
        
        return cls.URL_PATTERN.findall(text)
    
    @classmethod
    def initialize_domain_patterns(cls) -> None:
        """
        Initialize common domain patterns from yt-dlp extractors for faster URL checking.
        This should be called at bot startup.
        """
        try:
            start_time = time.time()
            
            # Get all extractors
            extractors = yt_dlp.extractor.gen_extractors()
            
            # Gather domain patterns from IE_NAME and _VALID_URL patterns
            domain_patterns = []
            
            for extractor in extractors:
                # Try to get patterns from _VALID_URL if available
                valid_url = getattr(extractor, '_VALID_URL', None)
                if valid_url:
                    # Extract domain pattern from _VALID_URL 
                    try:
                        # Look for common domain parts in the pattern
                        domain_parts = re.findall(r'(?:https?://)?(?:(?:www|m)\.)?([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', valid_url)
                        for part in domain_parts:
                            if part and '.' in part:
                                domain_patterns.append(part.replace('\\', ''))
                    except:
                        pass
                
                # Get IE_NAME as a fallback
                ie_name = getattr(extractor, 'IE_NAME', '').lower()
                if ie_name and '.' in ie_name:
                    domain_patterns.append(ie_name)
            
            # Compile patterns for faster matching
            cls._common_domain_patterns = [
                re.compile(re.escape(pattern), re.IGNORECASE) 
                for pattern in set(domain_patterns) 
                if pattern and len(pattern) > 3  # Filter out very short patterns
            ]
            
            cls._initialized = True
            logger.info(f"Initialized {len(cls._common_domain_patterns)} domain patterns in {time.time() - start_time:.2f}s")
        except Exception as e:
            logger.error(f"Error initializing domain patterns: {str(e)}")
    
    @classmethod
    def has_supported_url(cls) -> Callable:
        """
        Create a Pyrogram filter that checks if a message contains a URL supported by yt-dlp.
        
        Returns:
            Callable: A Pyrogram filter function
        """
        # Initialize domain patterns if not already done
        if not cls._initialized:
            cls.initialize_domain_patterns()
            
        async def func(flt, client, message: Message) -> bool:
            # Skip processing for non-text messages
            if not message.text and not message.caption:
                return False
                
            text = message.text or message.caption
            urls = cls.extract_urls(text)
            
            # No URLs found
            if not urls:
                return False
                
            # Check if any URL is supported
            for url in urls:
                if cls.is_supported_url(url):
                    # Store the found URL in message.ytdlp_url for easy access
                    message.ytdlp_url = url
                    return True
                    
            return False
            
        return filters.create(func)

    @classmethod
    def clear_cache(cls):
        """Clear the domain support cache"""
        cls._supported_domains_cache.clear()

# Create the filter instance for easy importing
ytdlp_url = YtdlpUrlFilter.has_supported_url()


# Create the filter using filters.create
Main_dlURl = filters.create(Main_supportedDlUrl)
# creating filters.
dev_cmd = filters.create(dev_users)
sudo_cmd = filters.create(sudo_users)
is_ratelimited = filters.create(ratelimiter)
is_ratelimiter_dl = filters.create(ratelimiter_dl)