#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
import os
import time

from src.helpers.dlp._rex import YT_LINK_REGEX
from src.helpers.dlp.yt_dl.catch import clean_expired_cache
from src.helpers.dlp.yt_dl.callback import handle_youtube_link, handle_youtube_callback
from src.helpers.filters import is_download_rate_limited , is_rate_limited,is_download_callback_rate_limited
from src.helpers.filters import sudo_cmd

from src.logging import LOGGER
logger = LOGGER(__name__)

# Clean expired cache periodically
@Client.on_message(filters.command("clean_ytcache") & sudo_cmd)
async def clean_cache_command(client: Client, message: Message):
    """Clean YouTube downloader cache on command"""
    if not message.from_user or not message.from_user.id:
        return
    
    
    # Clean expired callbacks
    start_time = time.time()
    cleaned_count = clean_expired_cache()
    
    # Also clean temporary download directory
    temp_files_deleted = 0
    try:
        download_path = "./tmp"
        if os.path.exists(download_path):
            for filename in os.listdir(download_path):
                file_path = os.path.join(download_path, filename)
                # Check if file is older than 12 hours
                if os.path.isfile(file_path) and time.time() - os.path.getmtime(file_path) > 12 * 3600:
                    os.remove(file_path)
                    temp_files_deleted += 1
    except Exception as e:
        logger.error(f"Error cleaning temporary files: {e}")
    
    elapsed_time = time.time() - start_time
    await message.reply_text(
        f"✅ Cleanup completed in {elapsed_time:.2f} seconds:\n"
        f"• Cleaned {cleaned_count} expired cache entries\n"
        f"• Deleted {temp_files_deleted} old temporary files"
    )

# YouTube download command
@Client.on_message(filters.command(["youtube", "yt", "ytdl"]) & ~filters.bot & is_download_rate_limited)
async def youtube_command(client: Client, message: Message):
    """Handle YouTube download command"""
    
    # Check if command has a YouTube link as argument
    if len(message.command) > 1:
        # Join all arguments to handle YouTube links with parameters
        link = " ".join(message.command[1:])
        # Create a new message object to reuse the link handler
        new_message = Message(
            id=message.id,
            date=message.date,
            chat=message.chat,
            from_user=message.from_user,
            text=link,
            outgoing=message.outgoing,
            reply_to_message=message.reply_to_message,
            client=client
        )
        await handle_youtube_link(client, new_message)
    else:
        await message.reply_text(
            "ℹ️ **YouTube Downloader**\n\n"
            "Send a YouTube video link or use the command with a link:\n"
            "`/yt https://youtube.com/watch?v=...`\n\n"
            "I will process the link and let you choose the format to download.",
            quote=True
        )

# YouTube link detection
@Client.on_message(filters.regex(YT_LINK_REGEX) & filters.text & ~filters.bot & is_download_rate_limited)
async def youtube_link_detector(client: Client, message: Message):
    """Detect and handle YouTube links in messages"""
    await handle_youtube_link(client, message)

# Callback query handler for YouTube downloads
@Client.on_callback_query(filters.regex(r'^yt') & is_download_callback_rate_limited)
async def youtube_callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle YouTube download callbacks"""
    await handle_youtube_callback(client, callback_query)

# Command to show statistics about the YouTube downloader
@Client.on_message(filters.command(["ytstats"])& is_rate_limited)
async def yt_stats_command(client: Client, message: Message):
    """Show statistics about the YouTube downloader"""
    from src.helpers.dlp.yt_dl.catch import callback_cache, video_info_cache
    
    # Get stats
    total_callback_cache = len(callback_cache)
    total_video_cache = len(video_info_cache)
    
    # Check temp directory
    download_path = "./tmp"
    temp_files = 0
    total_size_mb = 0
    
    try:
        if os.path.exists(download_path):
            for filename in os.listdir(download_path):
                file_path = os.path.join(download_path, filename)
                if os.path.isfile(file_path):
                    temp_files += 1
                    total_size_mb += os.path.getsize(file_path) / (1024 * 1024)
    except Exception as e:
        logger.error(f"Error checking temp directory: {e}")
    
    stats_message = (
        "📊 **YouTube Downloader Stats**\n\n"
        f"• Cached callbacks: {total_callback_cache}\n"
        f"• Cached video info: {total_video_cache}\n"
        f"• Temporary files: {temp_files}\n"
        f"• Disk usage: {total_size_mb:.2f} MB\n\n"
        f"Use `/clean_ytcache` to clean up old cache entries."
    )
    
    await message.reply_text(stats_message, quote=True)