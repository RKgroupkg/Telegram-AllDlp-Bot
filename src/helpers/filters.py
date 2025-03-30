"""
Rate limiting and permission filters for Telegram bot operations.

This module provides custom Pyrogram filters for:
- User authorization (owner/sudo permissions)
- Rate limiting for different operations
- URL validation and processing

The filters help manage bot resources and prevent abuse while ensuring
smooth operation within Telegram's rate limitations.
"""

import re
import time
from typing import Callable, Dict, List, Union
from urllib.parse import urlparse

import yt_dlp
from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import CallbackQuery, Message

from src.config import OWNER_USERID, SUDO_USERID
from src.helpers.dlp._rex import LINK_REGEX_PATTERNS
from src.helpers.ratelimiter import RateLimiter
from src.logging import LOGGER

logger = LOGGER(__name__)

# ============================================================================
# Authorization Filters
# ============================================================================


def is_developer(_, __, message: Message) -> bool:
    """Filter messages from developer/owner users only."""
    return message.from_user and message.from_user.id in OWNER_USERID


def is_sudo_user(_, __, message: Message) -> bool:
    """Filter messages from sudo users only."""
    return message.from_user and message.from_user.id in SUDO_USERID


# ============================================================================
# Rate Limiting Configuration
# ============================================================================

# Chat-specific rate limiter (20 msg/min per chat as per Telegram limits)
CHAT_RATE_LIMITER = RateLimiter(
    limit_sec=1, limit_min=20, interval_sec=1, interval_min=60
)

# Global rate limiter (30 msg/sec globally as per Telegram limits)
GLOBAL_RATE_LIMITER = RateLimiter(
    limit_sec=30, limit_min=1800, interval_sec=1, interval_min=60
)

# Download operation rate limiter
DOWNLOAD_RATE_LIMITER = RateLimiter(
    limit_sec=1, limit_min=5, interval_sec=1, interval_min=60
)

# Download callback operation rate limiter
DOWNLOAD_CALLBACK_RATE_LIMITER = RateLimiter(
    limit_sec=3, limit_min=15, interval_sec=1, interval_min=60
)


# ============================================================================
# General Rate Limiting Filter
# ============================================================================


async def check_rate_limit(_, __, update: Union[Message, CallbackQuery]) -> bool:
    """
    Filter to prevent rate limit violations for general bot operations.

    Implements Telegram's official rate limits:
    - 20 messages per minute in the same group
    - 30 messages per second globally across all chats

    Private chats are not rate-limited by this filter.

    Args:
        update: The Message or CallbackQuery to check

    Returns:
        bool: True if not rate-limited, False otherwise
    """
    # Check global rate limit first
    is_global_limited = await GLOBAL_RATE_LIMITER.acquire("global_update")
    if is_global_limited:
        chat_id = (
            update.chat.id if isinstance(update, Message) else update.message.chat.id
        )
        logger.info(f"Global rate limit hit while processing chat: {chat_id}")
        return False

    # Extract chat info
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    chat_type = (
        update.chat.type if isinstance(update, Message) else update.message.chat.type
    )

    # Skip rate limiting for private chats
    if chat_type != ChatType.PRIVATE:
        is_chat_limited = await CHAT_RATE_LIMITER.acquire(chat_id)
        if is_chat_limited:
            if isinstance(update, CallbackQuery):
                await update.answer(
                    "Bot is receiving too many requests, please try again later.",
                    show_alert=True,
                )
            logger.info(f"Chat rate limit hit for: {chat_id}")
            return False

    return True


# ============================================================================
# Download Operation Rate Limiting Filter
# ============================================================================


async def check_download_rate_limit(
    _, __, update: Union[Message, CallbackQuery]
) -> bool:
    """
    Filter to prevent rate limit violations specifically for download operations.

    Implements stricter limits for resource-intensive download operations:
    - Still respects global limits
    - Adds download-specific limits per chat

    Args:
        update: The Message or CallbackQuery to check

    Returns:
        bool: True if not rate-limited, False otherwise
    """
    # Check global rate limit first
    is_global_limited = await GLOBAL_RATE_LIMITER.acquire("global_update")
    if is_global_limited:
        chat_id = (
            update.chat.id if isinstance(update, Message) else update.message.chat.id
        )
        logger.info(
            f"Global rate limit hit while processing download from chat: {chat_id}"
        )
        return False

    # Extract chat info
    chat_id = update.chat.id if isinstance(update, Message) else update.message.chat.id
    chat_type = (
        update.chat.type if isinstance(update, Message) else update.message.chat.type
    )

    # Check both regular chat limit and download-specific limit
    is_download_limited = await DOWNLOAD_RATE_LIMITER.acquire(chat_id)
    is_chat_limited = await CHAT_RATE_LIMITER.acquire(chat_id)
    if is_download_limited:
        if isinstance(update, CallbackQuery):
            await update.answer(
                "Download limit reached. Please try again in a few minutes.",
                show_alert=True,
            )
        elif isinstance(update, Message):
            await update.reply_text(
                "Download limit reached. Please try again in a few minutes.", quote=True
            )
        logger.info(f"Download rate limit hit for chat: {chat_id}")
        return False

    elif is_chat_limited:
        if isinstance(update, CallbackQuery):
            await update.answer(
                "Bot is receiving too many requests, please try again later.",
                show_alert=True,
            )
            logger.info(f"Chat rate limit hit for download from: {chat_id}")
        return False

    return True


# ============================================================================
# Download Callback Rate Limiting Filter
# ============================================================================


async def check_download_callback_rate_limit(_, __, update: CallbackQuery) -> bool:
    """
    Filter to prevent rate limit violations for download-related callbacks.

    Args:
        update: The CallbackQuery to check

    Returns:
        bool: True if not rate-limited, False otherwise
    """
    # Check global rate limit first
    is_global_limited = await GLOBAL_RATE_LIMITER.acquire("global_update")
    if is_global_limited:
        logger.info(
            f"Global rate limit hit while processing download callback from chat: {update.message.chat.id}"
        )
        return False

    # Extract chat info
    chat_id = update.message.chat.id
    chat_type = update.message.chat.type

    # Skip rate limiting for private chats
    # Check both callback-specific and general chat limits
    is_callback_limited = await DOWNLOAD_CALLBACK_RATE_LIMITER.acquire(chat_id)
    is_chat_limited = await CHAT_RATE_LIMITER.acquire(chat_id)

    if is_callback_limited:
        await update.answer(
            "Calm down! Action limit reached. Please try again.You might need to wait.",
            show_alert=True,
        )
        logger.info(f"Download callback rate limit hit for chat: {chat_id}")
        return False

    elif is_chat_limited:
        await update.answer(
            "Bot is receiving too many requests, please try again later.",
            show_alert=True,
        )
        logger.info(f"Chat rate limit hit for download callback from: {chat_id}")
        return False

    return True


# ============================================================================
# URL Filtering Functions
# ============================================================================


def is_blocked_url(_, __, message: Message) -> bool:
    """
    Filter that returns True if the message text does NOT match any blocked URL patterns.

    Args:
        message: The message to check

    Returns:
        bool: True if URL is allowed, False if it matches a blocked pattern
    """
    text = message.text or ""
    for pattern in LINK_REGEX_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    return True


# ============================================================================
# YT-DLP URL Filter Class
# ============================================================================


class YTDLPUrlFilter:
    """
    Advanced filter for checking if a message contains a URL supported by yt-dlp.

    Features:
    - URL extraction and validation
    - Domain pattern caching for performance
    - Intelligent URL format correction
    """

    # Common URL regex pattern for extraction
    URL_PATTERN = re.compile(
        r"(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|"
        r"www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|"
        r"https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|"
        r"www\.[a-zA-Z0-9]+\.[^\s]{2,})"
    )

    # Cache for domain validation results to reduce repeated checks
    _domain_cache: Dict[str, bool] = {}

    # Cache expiration time in seconds (24 hours)
    _CACHE_EXPIRY = 86400

    # Common domain patterns from extractors (populated on initialization)
    _domain_patterns: List[re.Pattern] = []

    # Initialization flag
    _initialized = False

    @classmethod
    def is_supported_url(cls, url: str) -> bool:
        """
        Check if a URL is supported by yt-dlp.

        Performs multiple validation stages:
        1. URL parsing and normalization
        2. Domain cache lookup
        3. Pattern-based quick check
        4. Full yt-dlp extraction test (as last resort)

        Args:
            url: The URL to check

        Returns:
            bool: True if the URL is supported, False otherwise
        """
        try:
            # Parse and normalize URL
            parsed_url = urlparse(url)
            domain = parsed_url.netloc

            # Handle URLs without scheme
            if not domain:
                if url.startswith("www."):
                    domain = url.split("/")[0]
                    url = f"http://{url}"
                elif "." in url and "/" in url:
                    domain = url.split("/")[0]
                    url = f"http://{url}"
                else:
                    return False

            # Check cache first for performance
            if domain in cls._domain_cache:
                return cls._domain_cache[domain]

            # Quick check using pre-compiled domain patterns
            if cls._domain_patterns:
                for pattern in cls._domain_patterns:
                    if pattern.search(domain):
                        cls._domain_cache[domain] = True
                        return True

            # Full extraction test as fallback
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "skip_download": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    # Quick check with process=False for better performance
                    ydl.extract_info(url, download=False, process=False)
                    cls._domain_cache[domain] = True
                    return True
                except yt_dlp.utils.UnsupportedError:
                    cls._domain_cache[domain] = False
                    return False
                except yt_dlp.utils.ExtractorError:
                    # If we get an extractor error, the URL format is valid but content may not be
                    # This is considered supported
                    cls._domain_cache[domain] = True
                    return True
                except yt_dlp.utils.DownloadError:
                    cls._domain_cache[domain] = False
                    return False

        except Exception as e:
            logger.error(f"Error validating URL {url}: {str(e)}")
            return False

    @classmethod
    def extract_urls(cls, text: str) -> List[str]:
        """
        Extract all URLs from a text string.

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
        Initialize common domain patterns from yt-dlp extractors.

        This optimization should be called at bot startup to cache patterns
        for faster URL checking during operation.
        """
        try:
            start_time = time.time()

            # Get all available extractors
            extractors = yt_dlp.extractor.gen_extractors()

            # Collect domain patterns from extractors
            domain_patterns = []

            for extractor in extractors:
                # Try to extract patterns from _VALID_URL regex if available
                valid_url = getattr(extractor, "_VALID_URL", None)
                if valid_url:
                    try:
                        # Extract domain pattern from regex
                        domain_parts = re.findall(
                            r"(?:https?://)?(?:(?:www|m)\.)?([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
                            valid_url,
                        )
                        for part in domain_parts:
                            if part and "." in part:
                                domain_patterns.append(part.replace("\\", ""))
                    except Exception:
                        pass

                # Use IE_NAME as fallback/additional pattern
                ie_name = getattr(extractor, "IE_NAME", "").lower()
                if ie_name and "." in ie_name:
                    domain_patterns.append(ie_name)

            # Compile patterns for faster matching
            cls._domain_patterns = [
                re.compile(re.escape(pattern), re.IGNORECASE)
                for pattern in set(domain_patterns)
                if pattern and len(pattern) > 3  # Filter short patterns
            ]

            cls._initialized = True
            logger.info(
                f"Initialized {len(cls._domain_patterns)} yt-dlp domain patterns in {time.time() - start_time:.2f}s"
            )
        except Exception as e:
            logger.error(f"Error initializing yt-dlp domain patterns: {str(e)}")

    @classmethod
    def has_supported_url(cls) -> Callable:
        """
        Create a Pyrogram filter that checks if a message contains a yt-dlp supported URL.

        When this filter passes, it adds a 'ytdlp_url' attribute to the message for convenience.

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
                    # Store the found URL in message.ytdlp_url for easy access in handlers
                    message.ytdlp_url = url
                    return True

            return False

        return filters.create(func)

    @classmethod
    def clear_cache(cls):
        """Clear the domain support cache."""
        cls._domain_cache.clear()


# ============================================================================
# Create filter instances for easy importing
# ============================================================================

# Permission filters
dev_cmd = filters.create(is_developer)
sudo_cmd = filters.create(is_sudo_user)

# Rate limiting filters
is_rate_limited = filters.create(check_rate_limit)
is_download_rate_limited = filters.create(check_download_rate_limit)
is_download_callback_rate_limited = filters.create(check_download_callback_rate_limit)

# URL filters
allowed_url = filters.create(is_blocked_url)
ytdlp_url = YTDLPUrlFilter.has_supported_url()


# old

# # Create the filter instance for easy importing
# ytdlp_url = YtdlpUrlFilter.has_supported_url()


# # Create the filter using filters.create
# Main_dlURl = filters.create(Main_supportedDlUrl)
# # creating filters.
# dev_cmd = filters.create(dev_users)
# sudo_cmd = filters.create(sudo_users)
# is_ratelimited = filters.create(ratelimiter)
# is_download_rate_limited = filters.create(ratelimiter_dl)
