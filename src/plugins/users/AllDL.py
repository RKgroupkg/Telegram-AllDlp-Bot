#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
import os
import re
import time  # Add this import for time tracking
import asyncio  # Add this for async operations

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from src.logging import LOGGER
logger = LOGGER(__name__)

from src.helpers.dlp.yt_dl.ytdl_core import (
    fetch_youtube_info,
    download_youtube_video,
    format_progress,
    clean_temporary_file,
    MAX_VIDEO_LENGTH_MINUTES,
    beautify_views,
    download_video_from_link
)

# rex patterns not to match with
from src.helpers.dlp.yt_dl.utils import YT_LINK_REGEX
# Regex patterns for Spotify links
SPOTIFY_TRACK_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/track/([a-zA-Z0-9]+)"
SPOTIFY_ALBUM_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/album/([a-zA-Z0-9]+)"
SPOTIFY_PLAYLIST_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/playlist/([a-zA-Z0-9]+)"
INSTAGRAM_URL_PATTERN = r"https?://(?:www\.)?instagram\.com/(?:share/)?(?:p|reel|tv)/([a-zA-Z0-9_-]+)(?:/[a-zA-Z0-9_-]+)?"
# Simple regex pattern to find URLs starting with https://
URL_REGEX = r"https://\S+"  
# List all regex patterns you want to check
LINK_REGEX_PATTERNS = [
    YT_LINK_REGEX,
    SPOTIFY_TRACK_REGEX,
    SPOTIFY_ALBUM_REGEX,
    SPOTIFY_PLAYLIST_REGEX,
    INSTAGRAM_URL_PATTERN,
]

def no_supported_link_filter_func(_, __, message):
    """
    This filter returns True if the message text does NOT match any of the specified link patterns.
    If any pattern matches, it returns False.
    """
    text = message.text or ""
    for pattern in LINK_REGEX_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    return True

# Create the filter using filters.create
no_link_filter = filters.create(no_supported_link_filter_func)

# Track active downloads and download queue
active_downloads = {}
download_queue = {}
PROGRESS_UPDATE_INTERVAL = 3  # Update progress every 3 seconds
STALLED_DOWNLOAD_TIMEOUT = 30  # Cancel download if stalled for 30 seconds


# Simple handler to process any URL message
@Client.on_message(no_link_filter & filters.incoming)
async def video_handler(client: Client, message: Message):
    try:
        download_info = None
        # Send initial processing message.
        msg = await message.reply_text(" Processing The link...")

        # Extract the first valid link
        match = re.search(URL_REGEX, message.text or "")
        if not match:
            await msg.edit_text("⚠ No valid link found in your message.")
            return
        
        link = match.group(0)  # Extract the URL
        

        # Call your generic download function.
        # Optionally, you could pass a progress callback if needed.
        download_info = await download_video_from_link(link)
        ext = download_info.ext


        # Upload the file to Telegram
        file_path = download_info.file_path
        title = f"{download_info.title[:40]}."
        ext = download_info.ext
        performer = download_info.performer
        duration = download_info.duration

        # Determine if it's audio or video based on extension
        is_audio = ext in ['mp3', 'm4a', 'aac', 'flac', 'opus', 'ogg']
        
        await msg.edit_text(f"↥ Uploading __[{format_size(int(download_info.filesize))}]__\n\n  __{download_info.title[:40]}__...")
        
        # Check if the download was successful.
        if download_info.success:
            if is_audio:
        
                await client.send_audio(
                    chat_id=message.chat.id,
                    audio=file_path,
                    performer = performer,
                    duration = duration,
                    caption=f"≡ __{title}__\n\n__Via__ @{(await client.get_me()).username}",
                    file_name=f"{title}.{ext}",
                   )
                
            else:
                await client.send_video(
                    chat_id=message.chat.id,
                    video=file_path,
                    caption=f"≡ __{title}__\n\n__via__ @{(await client.get_me()).username}",
                    file_name=f"{title}.{ext}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("♙ Open Site ♙", url=link)]])
                )
            await msg.delete()  # Remove the processing message if desired.
        else:
            # Inform the user if something went wrong.
            await msg.edit_text(f"Download failed: {download_info.error}")
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        await msg.edit_text("An error occurred while processing your request.", parse_mode=ParseMode.HTML)
    finally:
        if download_info:
            if download_info.success:
                try:
                    if os.path.exists(download_info.file_path):
                        clean_temporary_file(download_info.file_path) # Delete the Media
                except Exception as e:
                    logger.error(f"Error cleaning up temporary file: {e}")
                


async def process_next_in_queue(client, chat_id, last_message):
    """Process next download in queue if any"""
    if chat_id in download_queue and download_queue[chat_id]:
        next_download = download_queue[chat_id].pop(0)
        # Start the next download
        await video_handler(client, next_download)
    else:
        if chat_id in download_queue:
            del download_queue[chat_id]
        if chat_id in active_downloads:
            del active_downloads[chat_id]

def format_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.1f} GB"
