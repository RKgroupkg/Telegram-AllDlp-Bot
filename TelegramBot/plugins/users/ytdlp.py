import os
import re
import time
import asyncio
import aiofiles
import ffmpeg
import uuid
from datetime import timedelta, datetime

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

import yt_dlp
from yt_dlp.utils import DownloadError

from TelegramBot import bot
from TelegramBot.helpers.filters import is_ratelimited
from TelegramBot.logging import LOGGER

logger = LOGGER(__name__)

# Configuration constants
MAX_VIDEO_LENGTH_MINUTES = 15
DOWNLOAD_PATH = "./tmp"
PROGRESS_UPDATE_INTERVAL = 5  # seconds
CACHE_EXPIRY_HOURS = 1  # Cache expiry time in hours

# Ensure download directory exists
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# Regular expressions for YouTube links
YT_LINK_REGEX = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:watch\?v=|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})"

# Cache structure for callback data
callback_cache = {}

def generate_callback_id():
    """Generate a short unique ID for callbacks"""
    # Generate a 6-digit number for simplicity
    return str(uuid.uuid4().int % 1000000).zfill(6)

def store_callback_data(data, expiry_hours=CACHE_EXPIRY_HOURS):
    """Store data in cache with expiry time and return a callback ID"""
    callback_id = generate_callback_id()
    callback_cache[callback_id] = {
        'data': data,
        'expires_at': datetime.now() + timedelta(hours=expiry_hours)
    }
    return callback_id

def get_callback_data(callback_id):
    """Retrieve data from cache if it exists and hasn't expired"""
    if callback_id not in callback_cache:
        return None
    
    cache_item = callback_cache[callback_id]
    if datetime.now() > cache_item['expires_at']:
        # Clean up expired item
        del callback_cache[callback_id]
        return None
    
    return cache_item['data']

def clean_expired_cache():
    """Remove expired items from the callback cache"""
    current_time = datetime.now()
    expired_keys = [
        key for key, item in callback_cache.items()
        if current_time > item['expires_at']
    ]
    
    for key in expired_keys:
        del callback_cache[key]
    
    return len(expired_keys)

# Dynamic button creation for pagination
def generate_format_buttons(formats, page=0, items_per_page=5):
    """Generate paginated format selection buttons"""
    if not formats:
        return []
    
    total_pages = (len(formats) + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(formats))
    
    buttons = []
    # Add format buttons for current page
    for idx in range(start_idx, end_idx):
        fmt = formats[idx]
        if fmt.get('acodec') != 'none' and fmt.get('vcodec') != 'none':
            # Both audio and video
            quality = fmt.get('height', 'N/A')
            file_size = fmt.get('filesize', fmt.get('filesize_approx', 0))
            size_text = f"{file_size / (1024 * 1024):.1f}MB" if file_size else "Unknown"
            label = f"🎬 {quality}p • {fmt.get('ext')} • {size_text}"
        elif fmt.get('vcodec') != 'none':
            # Video only
            quality = fmt.get('height', 'N/A')
            file_size = fmt.get('filesize', fmt.get('filesize_approx', 0))
            size_text = f"{file_size / (1024 * 1024):.1f}MB" if file_size else "Unknown"
            label = f"📹 {quality}p • {fmt.get('ext')} • {size_text}"
        else:
            # Audio only
            file_size = fmt.get('filesize', fmt.get('filesize_approx', 0))
            size_text = f"{file_size / (1024 * 1024):.1f}MB" if file_size else "Unknown"
            label = f"🎵 {fmt.get('asr', 'N/A')}kHz • {fmt.get('ext')} • {size_text}"
        
        # Store format selection data in cache and get a callback ID
        format_data = {
            'type': 'format',
            'video_id': formats[idx].get('video_id'),
            'format_id': fmt['format_id']
        }
        format_callback_id = store_callback_data(format_data)
        
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"ytdl_{format_callback_id}"
            )
        ])
    
    # Add pagination controls
    pagination_buttons = []
    
    # Store page data for previous button
    if page > 0:
        prev_page_data = {
            'type': 'page',
            'video_id': formats[0].get('video_id') if formats else None,
            'page': page - 1
        }
        prev_callback_id = store_callback_data(prev_page_data)
        pagination_buttons.append(
            InlineKeyboardButton(
                text="◄ Previous",
                callback_data=f"ytpage_{prev_callback_id}"
            )
        )
    
    # Store video info data
    if formats:
        info_data = {
            'type': 'info',
            'video_id': formats[0].get('video_id')
        }
        info_callback_id = store_callback_data(info_data)
        pagination_buttons.append(
            InlineKeyboardButton(
                text=f"📄 {page+1}/{total_pages}",
                callback_data=f"ytinfo_{info_callback_id}"
            )
        )
    
    # Store page data for next button
    if page < total_pages - 1:
        next_page_data = {
            'type': 'page',
            'video_id': formats[0].get('video_id') if formats else None,
            'page': page + 1
        }
        next_callback_id = store_callback_data(next_page_data)
        pagination_buttons.append(
            InlineKeyboardButton(
                text="Next ►",
                callback_data=f"ytpage_{next_callback_id}"
            )
        )
    
    buttons.append(pagination_buttons)
    
    # Add category filter buttons
    if formats:
        # Store filter data for each category
        all_filter_data = {
            'type': 'filter',
            'video_id': formats[0].get('video_id'),
            'filter_type': 'all',
            'page': 0
        }
        video_filter_data = {
            'type': 'filter',
            'video_id': formats[0].get('video_id'),
            'filter_type': 'video',
            'page': 0
        }
        audio_filter_data = {
            'type': 'filter',
            'video_id': formats[0].get('video_id'),
            'filter_type': 'audio',
            'page': 0
        }
        
        all_callback_id = store_callback_data(all_filter_data)
        video_callback_id = store_callback_data(video_filter_data)
        audio_callback_id = store_callback_data(audio_filter_data)
        
        filter_buttons = [
            InlineKeyboardButton(
                text="🎬 All",
                callback_data=f"ytfilter_{all_callback_id}"
            ),
            InlineKeyboardButton(
                text="📹 Video",
                callback_data=f"ytfilter_{video_callback_id}"
            ),
            InlineKeyboardButton(
                text="🎵 Audio",
                callback_data=f"ytfilter_{audio_callback_id}"
            )
        ]
        buttons.append(filter_buttons)
    
    # Add cancel button
    if formats:
        cancel_data = {
            'type': 'cancel',
            'video_id': formats[0].get('video_id')
        }
        cancel_callback_id = store_callback_data(cancel_data)
        buttons.append([
            InlineKeyboardButton(
                text="❌ Cancel",
                callback_data=f"ytcancel_{cancel_callback_id}"
            )
        ])
    
    return buttons

# Cache for video information to avoid repeated API calls
video_info_cache = {}

async def fetch_youtube_info(video_id):
    """Fetch information about a YouTube video"""
    if video_id in video_info_cache:
        return video_info_cache[video_id]
    
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'cookiefile': 'cookies.txt',  # Add your cookies file here if needed
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            
            # Filter and sort formats
            formats = []
            
            # Add combined formats first (with both video and audio)
            combined_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') != 'none']
            # Sort by quality (height) in descending order
            combined_formats.sort(key=lambda x: (x.get('height', 0) or 0), reverse=True)
            # Add video_id to each format for reference
            for fmt in combined_formats:
                fmt['video_id'] = video_id
            formats.extend(combined_formats)
            
            # Add video-only formats
            video_formats = [f for f in info['formats'] if f.get('acodec') == 'none' and f.get('vcodec') != 'none']
            video_formats.sort(key=lambda x: (x.get('height', 0) or 0), reverse=True)
            # Add video_id to each format for reference
            for fmt in video_formats:
                fmt['video_id'] = video_id
            formats.extend(video_formats)
            
            # Add audio-only formats
            audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
            audio_formats.sort(key=lambda x: (x.get('asr', 0) or 0), reverse=True)
            # Add video_id to each format for reference
            for fmt in audio_formats:
                fmt['video_id'] = video_id
            formats.extend(audio_formats)
            
            # Save relevant info to cache
            result = {
                'title': info.get('title', 'Unknown Title'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', None),
                'uploader': info.get('uploader', 'Unknown'),
                'formats': formats,
                'all_formats': formats,
                'video_formats': video_formats,
                'audio_formats': audio_formats,
                'combined_formats': combined_formats
            }
            
            video_info_cache[video_id] = result
            return result
    except Exception as e:
        logger.error(f"Error fetching YouTube video info: {e}")
        return None

async def format_progress(current, total, start_time):
    """Format download progress information"""
    elapsed_time = time.time() - start_time
    speed = current / elapsed_time if elapsed_time > 0 else 0
    
    percentage = current * 100 / total if total > 0 else 0
    progress_bar_length = 10
    completed_length = int(progress_bar_length * current / total) if total > 0 else 0
    remaining_length = progress_bar_length - completed_length
    
    progress_bar = '█' * completed_length + '░' * remaining_length
    
    # Calculate ETA
    if speed > 0:
        eta = (total - current) / speed
        eta_str = str(timedelta(seconds=int(eta)))
    else:
        eta_str = "Unknown"
    
    return (
        f"**Downloading...**\n"
        f"Progress: {percentage:.1f}% [{progress_bar}]\n"
        f"Speed: {speed / (1024 * 1024):.2f} MB/s\n"
        f"Downloaded: {current / (1024 * 1024):.2f}/{total / (1024 * 1024):.2f} MB\n"
        f"ETA: {eta_str}"
    )

async def download_youtube_video(video_id, format_id, progress_callback):
    """Download a YouTube video with progress updates"""
    ydl_opts = {
        'format': format_id,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'outtmpl': f'{DOWNLOAD_PATH}/%(id)s.%(ext)s',
        'cookiefile': 'cookies.txt',  # Add your cookies file here if needed
        'progress_hooks': [progress_callback],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            return {
                'success': True,
                'file_path': os.path.join(DOWNLOAD_PATH, f"{video_id}.{info['ext']}"),
                'title': info.get('title', 'Unknown Title'),
                'ext': info.get('ext', 'unknown')
            }
    except Exception as e:
        logger.error(f"Error downloading YouTube video: {e}")
        return {
            'success': False,
            'error': str(e)
        }

# Command handler for YouTube download
@bot.on_message(filters.regex(YT_LINK_REGEX) & is_ratelimited)
async def youtube_download_command(client, message: Message):
    """Handle YouTube video link detection and display available formats"""
    # Extract video ID
    match = re.search(YT_LINK_REGEX, message.text)
    if not match:
        return
    
    video_id = match.group(1)
    processing_msg = await message.reply_text("🔍 Processing YouTube link...", quote=True)
    
    try:
        # Fetch video information
        info = await fetch_youtube_info(video_id)
        if not info:
            await processing_msg.edit_text("❌ Failed to fetch video information. Please try again.")
            return
        
        # Check video duration
        duration_minutes = info['duration'] / 60
        if duration_minutes > MAX_VIDEO_LENGTH_MINUTES:
            await processing_msg.edit_text(
                f"❌ Video is too long ({int(duration_minutes)} minutes). Maximum allowed duration is {MAX_VIDEO_LENGTH_MINUTES} minutes."
            )
            return
        
        # Format duration
        duration_str = str(timedelta(seconds=info['duration']))
        
        # Create format selection keyboard
        buttons = generate_format_buttons(info['formats'], page=0)
        
        # Update message with video information and format selection
        await processing_msg.edit_text(
            f"📝 **{info['title']}**\n\n"
            f"👤 Uploader: {info['uploader']}\n"
            f"⏱️ Duration: {duration_str}\n\n"
            f"Please select a format to download:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Error processing YouTube link: {e}")
        await processing_msg.edit_text(f"❌ Error processing YouTube link: {str(e)}")

# Fixed callback query handler for format selection and pagination
@bot.on_callback_query(filters.regex(r"^yt(dl|page|filter|cancel|info)_"))
async def youtube_callback_handler(client, callback_query):
    """Handle callback queries for format selection and pagination"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    message = callback_query.message
    
    # Extract callback type and identifier
    parts = data.split("_", 1)
    if len(parts) != 2:
        logger.error(f"Invalid callback data format: {data}")
        await callback_query.answer("Invalid callback data", show_alert=True)
        return
    
    callback_type = parts[0]
    callback_id = parts[1]
    
    # Retrieve cached data for this callback
    cached_data = get_callback_data(callback_id)
    if not cached_data and callback_type != "ytcancel":
        logger.error(f"Callback data not found or expired: {callback_id}")
        await callback_query.answer("This selection has expired. Please try again.", show_alert=True)
        return
    
    # Handle different callback types
    try:
        if callback_type == "ytcancel":
            await message.edit_text("❌ Download cancelled.")
            return
            
        elif callback_type == "ytinfo":
            video_id = cached_data.get('video_id')
            info = video_info_cache.get(video_id)
            if not info:
                await callback_query.answer("ℹ️ Video information not available anymore.", show_alert=True)
                return
            
            duration_str = str(timedelta(seconds=info['duration']))
            await callback_query.answer(
                f"Title: {info['title']}\n"
                f"Duration: {duration_str}\n"
                f"Uploader: {info['uploader']}",
                show_alert=True
            )
            return
            
        elif callback_type == "ytfilter":
            video_id = cached_data.get('video_id')
            filter_type = cached_data.get('filter_type')
            page = 0  # Reset to first page when changing filters
            
            info = video_info_cache.get(video_id)
            if not info:
                await callback_query.answer("ℹ️ Video information not available anymore.", show_alert=True)
                return
            
            if filter_type == "all":
                info['formats'] = info['all_formats']
            elif filter_type == "video":
                info['formats'] = info['combined_formats'] + info['video_formats']
            elif filter_type == "audio":
                info['formats'] = info['audio_formats']
            
            buttons = generate_format_buttons(info['formats'], page=page)
            
            await message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
            
        elif callback_type == "ytpage":
            video_id = cached_data.get('video_id')
            page = cached_data.get('page', 0)
            
            info = video_info_cache.get(video_id)
            if not info:
                await callback_query.answer("ℹ️ Video information not available anymore.", show_alert=True)
                return
            
            buttons = generate_format_buttons(info['formats'], page=page)
            
            await message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
            
        elif callback_type == "ytdl":
            video_id = cached_data.get('video_id')
            format_id = cached_data.get('format_id')
            
            info = video_info_cache.get(video_id)
            if not info:
                await callback_query.answer("ℹ️ Video information not available anymore.", show_alert=True)
                return
            
            # Find selected format
            selected_format = None
            for fmt in info['formats']:
                if fmt['format_id'] == format_id:
                    selected_format = fmt
                    break
            
            if not selected_format:
                await callback_query.answer("❌ Selected format not available.", show_alert=True)
                return
            
            # Update message to show download status
            await message.edit_text(
                f"🔄 Preparing to download: **{info['title']}**\n\n"
                f"Format: {selected_format.get('height', 'Audio')}p {selected_format.get('ext', '')}"
            )
            
            # Set up progress tracking
            start_time = time.time()
            last_update_time = start_time
            file_size = selected_format.get('filesize', selected_format.get('filesize_approx', 0))
            
            async def progress_hook(d):
                nonlocal last_update_time
                current_time = time.time()
                
                if d['status'] == 'downloading':
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    total_bytes = d.get('total_bytes', d.get('total_bytes_estimate', file_size))
                    
                    # Update progress message at specified intervals
                    if current_time - last_update_time >= PROGRESS_UPDATE_INTERVAL:
                        last_update_time = current_time
                        progress_text = await format_progress(downloaded_bytes, total_bytes, start_time)
                        
                        try:
                            await message.edit_text(
                                f"{progress_text}\n\n"
                                f"🎬 **{info['title']}**"
                            )
                        except Exception as e:
                            logger.error(f"Error updating progress: {e}")
            
            # Download the video
            download_task = asyncio.create_task(
                download_youtube_video(video_id, format_id, lambda d: asyncio.create_task(progress_hook(d)))
            )
            
            result = await download_task
            
            if not result['success']:
                await message.edit_text(
                    f"❌ Download failed: {result.get('error', 'Unknown error')}"
                )
                return
            
            # Upload the file to Telegram
            file_path = result['file_path']
            title = result['title']
            ext = result['ext']
            
            # Determine if it's audio or video based on extension
            is_audio = ext in ['mp3', 'm4a', 'aac', 'flac', 'opus', 'ogg']
            
            await message.edit_text(f"📤 Uploading **{title}**...")
            
            try:
                if is_audio:
                    await client.send_audio(
                        chat_id=message.chat.id,
                        audio=file_path,
                        caption=f"🎵 **{title}**\n\nDownloaded via @{(await client.get_me()).username}",
                        reply_to_message_id=callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else None
                    )
                else:
                    await client.send_video(
                        chat_id=message.chat.id,
                        video=file_path,
                        caption=f"🎬 **{title}**\n\nDownloaded via @{(await client.get_me()).username}",
                        reply_to_message_id=callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else None
                    )
                
                await message.edit_text(f"✅ Successfully downloaded and uploaded: **{title}**")
            except Exception as e:
                await message.edit_text(f"❌ Failed to upload file: {str(e)}")
            finally:
                # Clean up downloaded file
                try:
                    os.remove(file_path)
                except:
                    pass
    except Exception as e:
        logger.error(f"Error handling {callback_type} callback: {e}")
        await callback_query.answer("An error occurred", show_alert=True)

# Add a specific command for YouTube downloads too
@bot.on_message(filters.command("ytdl") & is_ratelimited)
async def youtube_download_manual_command(client, message: Message):
    """Handle /ytdl command with YouTube video link"""
    if len(message.command) < 2:
        await message.reply_text(
            "**Usage:** /ytdl [YouTube URL]\n\n"
            "Example: `/ytdl https://www.youtube.com/watch?v=dQw4w9WgXcQ`\n\n"
            "You can also simply send a YouTube video link directly."
        )
        return
    
    video_url = message.command[1]
    match = re.search(YT_LINK_REGEX, video_url)
    if not match:
        await message.reply_text("❌ Invalid YouTube URL. Please provide a valid YouTube video link.")
        return
    
    # Create a fake message with the URL to reuse existing handler
    fake_message = Message(
        id=message.id,
        from_user=message.from_user,
        chat=message.chat,
        text=video_url,
        reply_to_message=message.reply_to_message,
        client=client
    )
    await youtube_download_command(client, fake_message)

# Help command for YouTube downloader
@bot.on_message(filters.command("ythelp") & is_ratelimited)
async def youtube_help_command(client, message: Message):
    """Show help information for YouTube downloader"""
    help_text = (
        "**📥 YouTube Downloader Help**\n\n"
        "This module allows you to download videos and audio from YouTube.\n\n"
        "**Usage:**\n"
        "• Simply send a YouTube video/shorts link\n"
        "• Or use `/ytdl [YouTube URL]`\n\n"
        "**Features:**\n"
        "• Download videos up to 15 minutes in length\n"
        "• Choose from various quality options\n"
        "• Download audio-only versions\n"
        "• Real-time download progress\n\n"
        "**Note:** Downloading copyrighted content may be illegal in your country. Use responsibly."
    )
    
    await message.reply_text(help_text)

# Clean up expired cache periodically
@bot.on_message(filters.command("cleancache") & filters.user([123456]))  # Replace with admin user IDs
async def clean_cache_command(client, message: Message):
    """Clean up expired video info cache and callback cache (admin only)"""
    video_cache_count = len(video_info_cache)
    video_info_cache.clear()
    
    callback_cache_count = len(callback_cache)
    expired_count = clean_expired_cache()
    remaining_count = callback_cache_count - expired_count
    
    # Clean temporary files
    file_count = 0
    try:
        for file in os.listdir(DOWNLOAD_PATH):
            file_path = os.path.join(DOWNLOAD_PATH, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                file_count += 1
    except Exception as e:
        logger.error(f"Error cleaning temporary files: {e}")
    
    await message.reply_text(
        f"✅ Cache cleared:\n"
        f"• Video info cache: {video_cache_count} entries removed\n"
        f"• Callback cache: {expired_count} expired entries removed, {remaining_count} active entries remain\n"
        f"• Temporary files: {file_count} files deleted"
    )

# Setup a periodic task to clean expired callback cache
async def periodic_cache_cleanup():
    """Periodically clean up expired callback cache entries"""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        count = clean_expired_cache()
        if count > 0:
            logger.info(f"Periodic cache cleanup: {count} expired entries removed")

# Start the periodic cleanup task
try:
    asyncio.create_task(periodic_cache_cleanup())
except Exception as e:
    logger.error(f"Failed to start periodic cache cleanup: {e}")