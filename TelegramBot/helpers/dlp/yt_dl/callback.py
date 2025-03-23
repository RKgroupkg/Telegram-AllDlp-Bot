import os
import time
import asyncio
from datetime import timedelta
import traceback

from pyrogram import Client
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified, FloodWait

from TelegramBot.logging import LOGGER

from TelegramBot.helpers.dlp.yt_dl.ytdl_core import (
    fetch_youtube_info,
    download_youtube_video,
    format_progress,
    clean_temporary_file,
    MAX_VIDEO_LENGTH_MINUTES
)
from TelegramBot.helpers.dlp.yt_dl.chach import (
    get_callback_data, get_video_info_from_cache, add_video_info_to_cache,
    clear_video_info_cache, clean_expired_cache
)
from TelegramBot.helpers.dlp.yt_dl.utils import extract_video_id, create_format_selection_markup, YT_LINK_REGEX

logger = LOGGER(__name__)

# Track active downloads to prevent multiple downloads for the same user
active_downloads = {}
# Keep track of user format preferences
user_preferences = {}
# Download queue for users
download_queue = {}

# Constants
PROGRESS_UPDATE_INTERVAL = 3  # seconds
MAX_RETRIES = 3
STALLED_DOWNLOAD_TIMEOUT = 300  # 5 minutes

async def handle_youtube_link(client: Client, message: Message) -> None:
    """
    Handle YouTube video link detection and display available formats
    
    Args:
        client: Pyrogram client
        message: Message containing YouTube link
    """
    # Run cache cleanup
    clean_expired_cache()
    
    # Extract video ID
    video_id = extract_video_id(message.text)
    if not video_id:
        return
    
    # Check if user already has an active download
    user_id = message.from_user.id if message.from_user else 0
    if user_id in active_downloads and active_downloads[user_id]['expiry'] > time.time():
        # Only inform if this is a direct command, not a detected link
        if message.command and message.command[0] in ["youtube", "yt", "ytdl"]:
            # Add to queue option
            if user_id not in download_queue:
                download_queue[user_id] = []
            
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel current download", callback_data=f"ytcancel_{user_id}")],
                [InlineKeyboardButton("Add to queue", callback_data=f"ytqueue_{video_id}")]
            ])
            
            await message.reply_text(
                "⚠️ You already have an active download in progress. You can cancel it or add this to your queue.",
                quote=True,
                reply_markup=markup
            )
        return
    
    processing_msg = await message.reply_text("🔍 Processing YouTube link...", quote=True)
    
    try:
        # Fetch video information with retries
        cached_info = get_video_info_from_cache(video_id)
        if cached_info:
            info = cached_info
            logger.info(f"Using cached info for video {video_id}")
        else:
            logger.info(f"Fetching info for video {video_id}")
            for attempt in range(MAX_RETRIES):
                try:
                    info = await fetch_youtube_info(video_id)
                    if info:
                        add_video_info_to_cache(video_id, info)
                        break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2)  # Wait before retry
                        continue
                    raise e
            else:
                # All retries failed
                info = None
        
        if not info:
            await processing_msg.edit_text("❌ Failed to fetch video information. Please try again later.")
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
        
        # Get user's preferred filter type
        preferred_filter = user_preferences.get(user_id, {}).get('filter_type', 'all')
        
        # Filter formats based on user preference
        if preferred_filter == "video":
            info['formats'] = info['combined_formats'] + info['video_formats']
        elif preferred_filter == "audio":
            info['formats'] = info['audio_formats']
        
        # Create format selection keyboard
        markup = create_format_selection_markup(info['formats'], page=0)
        
        # Add thumbnail if available
        thumbnail_url = info.get('thumbnail')
        thumbnail_markup = ""
        if thumbnail_url:
            # We can't directly embed images, but we can provide a link
            thumbnail_markup = f"🖼 [View Thumbnail]({thumbnail_url})\n\n"
        
        # Update message with video information and format selection
        await processing_msg.edit_text(
            f"📝 **{info['title']}**\n\n"
            f"{thumbnail_markup}"
            f"👤 Uploader: {info['uploader']}\n"
            f"⏱️ Duration: {duration_str}\n"
            f"👁️ Views: {info.get('view_count', 'N/A')}\n\n"
            f"Please select a format to download:",
            reply_markup=markup,
            disable_web_page_preview=False  # Allow thumbnail preview if available
        )
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error processing YouTube link: {e}\n{error_trace}")
        await processing_msg.edit_text(f"❌ Error processing YouTube link: {str(e)}")

async def handle_youtube_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Handle callback queries for format selection and pagination
    
    Args:
        client: Pyrogram client
        callback_query: Callback query
    """
    data = callback_query.data
    message = callback_query.message
    user_id = callback_query.from_user.id
    
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
    if not cached_data and callback_type not in ["ytcancel", "ytqueue"]:
        logger.error(f"Callback data not found or expired: {callback_id}")
        await callback_query.answer("This selection has expired. Please try again.", show_alert=True)
        try:
            await message.edit_text("⏰ This selection has expired. Please request the YouTube link again.")
        except MessageNotModified:
            pass
        return
    
    # Handle different callback types
    try:
        if callback_type == "ytcancel":
            # If this user has an active download, mark it as cancelled
            if user_id in active_downloads:
                active_downloads[user_id]['cancelled'] = True
                await message.edit_text("❌ Download cancelled.")
                
                # Process next queued download if any
                if user_id in download_queue and download_queue[user_id]:
                    next_video_id = download_queue[user_id].pop(0)
                    # Create a fake message to process the next download
                    await callback_query.answer("Starting next download from queue...")
                    await handle_youtube_link(client, Message(
                        client=client,
                        chat=message.chat,
                        text=f"https://youtu.be/{next_video_id}",
                        from_user=callback_query.from_user
                    ))
                else:
                    if user_id in active_downloads:
                        del active_downloads[user_id]
                    await callback_query.answer("Download cancelled.")
            else:
                await callback_query.answer("No active download to cancel.")
                await message.edit_text("❌ No active download to cancel.")
            return
            
        elif callback_type == "ytqueue":
            video_id = callback_id
            if user_id not in download_queue:
                download_queue[user_id] = []
            
            download_queue[user_id].append(video_id)
            await callback_query.answer("Added to download queue!")
            return
            
        elif callback_type == "ytinfo":
            video_id = cached_data.get('video_id')
            info = get_video_info_from_cache(video_id)
            if not info:
                await callback_query.answer("ℹ️ Video information not available anymore.", show_alert=True)
                return
            
            duration_str = str(timedelta(seconds=info['duration']))
            # Enhanced info display
            info_text = (
                f"Title: {info['title']}\n"
                f"Duration: {duration_str}\n"
                f"Uploader: {info['uploader']}\n"
                f"Views: {info.get('view_count', 'N/A')}\n"
                f"Upload Date: {info.get('upload_date', 'N/A')}"
            )
            await callback_query.answer(info_text, show_alert=True)
            return
            
        elif callback_type == "ytfilter":
            video_id = cached_data.get('video_id')
            filter_type = cached_data.get('filter_type')
            page = 0  # Reset to first page when changing filters
            
            # Save user preference
            if user_id not in user_preferences:
                user_preferences[user_id] = {}
            user_preferences[user_id]['filter_type'] = filter_type
            
            info = get_video_info_from_cache(video_id)
            if not info:
                await callback_query.answer("ℹ️ Video information not available anymore.", show_alert=True)
                return
            
            if filter_type == "all":
                info['formats'] = info['all_formats']
            elif filter_type == "video":
                info['formats'] = info['combined_formats'] + info['video_formats']
            elif filter_type == "audio":
                info['formats'] = info['audio_formats']
            
            markup = create_format_selection_markup(info['formats'], page=page)
            
            try:
                await message.edit_reply_markup(reply_markup=markup)
            except MessageNotModified:
                pass
            await callback_query.answer(f"Showing {filter_type} formats")
            return
            
        elif callback_type == "ytpage":
            video_id = cached_data.get('video_id')
            page = cached_data.get('page', 0)
            
            info = get_video_info_from_cache(video_id)
            if not info:
                await callback_query.answer("ℹ️ Video information not available anymore.", show_alert=True)
                return
            
            markup = create_format_selection_markup(info['formats'], page=page)
            
            try:
                await message.edit_reply_markup(reply_markup=markup)
            except MessageNotModified:
                pass
            await callback_query.answer(f"Page {page+1}")
            return
            
        elif callback_type == "ytdl":
            # Check if user already has an active download
            if user_id in active_downloads and active_downloads[user_id]['expiry'] > time.time():
                # Offer to queue this download instead
                video_id = cached_data.get('video_id')
                format_id = cached_data.get('format_id')
                
                queue_data = f"{video_id}:{format_id}"
                queue_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Add to queue", callback_data=f"ytqueueformat_{queue_data}")]
                ])
                
                await callback_query.answer("⚠️ You already have an active download in progress", show_alert=True)
                try:
                    await message.edit_reply_markup(reply_markup=queue_markup)
                except MessageNotModified:
                    pass
                return
            
            video_id = cached_data.get('video_id')
            format_id = cached_data.get('format_id')
            
            info = get_video_info_from_cache(video_id)
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
            
            # For large files, ask for confirmation
            file_size = selected_format.get('filesize', selected_format.get('filesize_approx', 0))
            if file_size > 100 * 1024 * 1024:  # Over 100MB
                confirm_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Download anyway", callback_data=f"ytdlconfirm_{callback_id}")],
                    [InlineKeyboardButton("❌ Cancel", callback_data=f"ytcancel_{user_id}")]
                ])
                
                size_mb = file_size / (1024 * 1024)
                await message.edit_text(
                    f"⚠️ Warning: This file is large ({size_mb:.1f}MB).\n\n"
                    f"Title: {info['title']}\n"
                    f"Format: {selected_format.get('height', 'Audio')}p {selected_format.get('ext', '')}\n\n"
                    f"Do you want to proceed with the download?",
                    reply_markup=confirm_markup
                )
                await callback_query.answer("Large file detected, confirmation needed")
                return
            
            # Proceed with download
            await start_download(client, callback_query, message, video_id, format_id, info, selected_format)
            
        elif callback_type == "ytdlconfirm":
            # User confirmed a large download
            original_callback_id = callback_id
            cached_data = get_callback_data(original_callback_id)
            if not cached_data:
                await callback_query.answer("This selection has expired. Please try again.", show_alert=True)
                return
                
            video_id = cached_data.get('video_id')
            format_id = cached_data.get('format_id')
            
            info = get_video_info_from_cache(video_id)
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
                
            # Proceed with download
            await start_download(client, callback_query, message, video_id, format_id, info, selected_format)
            
        elif callback_type == "ytqueueformat":
            # Add download with specific format to queue
            data_parts = callback_id.split(":")
            if len(data_parts) != 2:
                await callback_query.answer("Invalid queue data", show_alert=True)
                return
                
            video_id, format_id = data_parts
            
            if user_id not in download_queue:
                download_queue[user_id] = []
            
            download_queue[user_id].append((video_id, format_id))
            
            queue_position = len(download_queue[user_id])
            await callback_query.answer(f"Added to download queue (position: {queue_position})")
            await message.edit_text(
                f"✅ Added to download queue (position: {queue_position})\n\n"
                f"Your download will start automatically when current download completes."
            )
            return
    
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error handling YouTube callback: {e}\n{error_trace}")
        await callback_query.answer("❌ An error occurred while processing your request.", show_alert=True)
        try:
            await message.edit_text(f"❌ An error occurred: {str(e)}")
        except:
            pass

async def start_download(client, callback_query, message, video_id, format_id, info, selected_format):
    """Helper function to start a download with progress tracking"""
    user_id = callback_query.from_user.id
    
    # Register active download
    active_downloads[user_id] = {
        'expiry': time.time() + 3600,  # 1 hour timeout
        'video_id': video_id,
        'format_id': format_id,
        'cancelled': False,
        'last_progress': 0,
        'last_update': time.time(),
        'stalled_since': None
    }
    
    # Format info
    format_info = ""
    if selected_format.get('height'):
        format_info = f"{selected_format.get('height', '')}p"
    else:
        format_info = "Audio"
    
    if selected_format.get('fps'):
        format_info += f" {selected_format.get('fps')}fps"
    
    format_info += f" {selected_format.get('ext', '')}"
    
    # Update message to show download status with cancel button
    cancel_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Download", callback_data=f"ytcancel_{user_id}")]
    ])
    
    await message.edit_text(
        f"🔄 Preparing to download: **{info['title']}**\n\n"
        f"Format: {format_info}\n"
        f"Status: Initializing...",
        reply_markup=cancel_markup
    )
    
    # Set up progress tracking
    start_time = time.time()
    last_update_time = start_time
    file_size = selected_format.get('filesize', selected_format.get('filesize_approx', 0))
    
    async def progress_hook(d):
        nonlocal last_update_time
        current_time = time.time()
        
        # Check if download was cancelled
        if active_downloads.get(user_id, {}).get('cancelled', False):
            return
        
        if d['status'] == 'downloading':
            downloaded_bytes = d.get('downloaded_bytes', 0)
            total_bytes = d.get('total_bytes', d.get('total_bytes_estimate', file_size))
            
            # Check for stalled download (no progress for a while)
            if active_downloads[user_id]['last_progress'] == downloaded_bytes:
                if active_downloads[user_id]['stalled_since'] is None:
                    active_downloads[user_id]['stalled_since'] = current_time
                elif current_time - active_downloads[user_id]['stalled_since'] > STALLED_DOWNLOAD_TIMEOUT:
                    # Mark as cancelled due to stall
                    active_downloads[user_id]['cancelled'] = True
                    try:
                        await message.edit_text(
                            f"❌ Download stalled for too long. Cancelled automatically."
                        )
                    except:
                        pass
                    return
            else:
                active_downloads[user_id]['last_progress'] = downloaded_bytes
                active_downloads[user_id]['stalled_since'] = None
            
            # Update progress message at specified intervals
            if current_time - last_update_time >= PROGRESS_UPDATE_INTERVAL:
                last_update_time = current_time
                progress_text = await format_progress(downloaded_bytes, total_bytes, start_time)
                
                # Calculate speed
                elapsed = current_time - start_time
                if elapsed > 0:
                    speed = downloaded_bytes / elapsed
                    speed_text = f"{format_size(speed)}/s"
                    
                    # Calculate ETA
                    if speed > 0 and total_bytes > 0:
                        eta_seconds = (total_bytes - downloaded_bytes) / speed
                        eta_text = format_time(eta_seconds)
                    else:
                        eta_text = "Unknown"
                else:
                    speed_text = "Calculating..."
                    eta_text = "Calculating..."
                
                try:
                    await message.edit_text(
                        f"{progress_text}\n"
                        f"Speed: {speed_text} | ETA: {eta_text}\n\n"
                        f"🎬 **{info['title']}**",
                        reply_markup=cancel_markup
                    )
                except (MessageNotModified, FloodWait) as e:
                    if isinstance(e, FloodWait):
                        await asyncio.sleep(e.value)
                except Exception as e:
                    logger.error(f"Error updating progress: {e}")
    
    try:
        await callback_query.answer("Starting download...")
        
        # Download the video with retries
        for attempt in range(MAX_RETRIES):
            try:
                download_task = asyncio.create_task(
                    download_youtube_video(video_id, format_id, progress_hook)
                )
                
                result = await download_task
                
                # If successful, break the retry loop
                if result['success']:
                    break
                
                # If cancelled, also break
                if active_downloads.get(user_id, {}).get('cancelled', False):
                    break
                    
                # Otherwise retry
                if attempt < MAX_RETRIES - 1:
                    await message.edit_text(
                        f"⚠️ Download attempt {attempt+1} failed, retrying...\n\n"
                        f"Error: {result.get('error', 'Unknown error')}"
                    )
                    await asyncio.sleep(2)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    await message.edit_text(f"⚠️ Download error, retrying ({attempt+1}/{MAX_RETRIES})...")
                    await asyncio.sleep(2)
                else:
                    raise e
        
        # Check if download was cancelled during the process
        if active_downloads.get(user_id, {}).get('cancelled', False):
            if 'result' in locals() and 'file_path' in result and result['file_path']:
                clean_temporary_file(result['file_path'])
            await process_next_in_queue(client, user_id, message)
            return
        
        if not result['success']:
            await message.edit_text(
                f"❌ Download failed after {MAX_RETRIES} attempts: {result.get('error', 'Unknown error')}"
            )
            await process_next_in_queue(client, user_id, message)
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
                    caption=f"🎵 **{title}**\n\n__Downloaded via__ @{(await client.get_me()).username}",
                    file_name=f"{title}.{ext}",
                    reply_to_message_id=callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else None
                )
            else:
                await client.send_video(
                    chat_id=message.chat.id,
                    video=file_path,
                    caption=f"🎬 **{title}**\n\n__Downloaded via__ @{(await client.get_me()).username}",
                    file_name=f"{title}.{ext}",
                    reply_to_message_id=callback_query.message.reply_to_message.id if callback_query.message.reply_to_message else None
                )
            
            await message.edit_text(f"✅ Successfully downloaded and uploaded: **{title}**")
        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"Failed to upload file: {e}\n{error_trace}")
            await message.edit_text(f"❌ Failed to upload file: {str(e)}")
        finally:
            # Clean up downloaded file and active download status
            try:
                if os.path.exists(file_path):
                    clean_temporary_file(file_path)
            except Exception as e:
                logger.error(f"Error cleaning up temporary file: {e}")
            
            # Process next queued download if any
            await process_next_in_queue(client, user_id, message)
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error handling YouTube download: {e}\n{error_trace}")
        await message.edit_text(f"❌ An error occurred during download: {str(e)}")
        process_next_in_queue(client, user_id, message)

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

def format_time(seconds):
    """Format time in human readable format"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes:.0f}m {seconds:.0f}s"
    else:
        hours = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        return f"{hours:.0f}h {minutes:.0f}m"

async def process_next_in_queue(client, user_id, message):
    """Process next download in user's queue if any"""
    if user_id in active_downloads:
        del active_downloads[user_id]
    
    # Check if there are queued downloads
    if user_id in download_queue and download_queue[user_id]:
        next_item = download_queue[user_id].pop(0)
        
        # Check if it's a tuple (video_id, format_id) or just video_id
        if isinstance(next_item, tuple):
            video_id, format_id = next_item
            
            # Create a fake callback query to start the download
            info = get_video_info_from_cache(video_id)
            if not info:
                await message.edit_text("❌ Queued video information expired. Please try again.")
                await process_next_in_queue(client, user_id, message)
                return
                
            # Find selected format
            selected_format = None
            for fmt in info['formats']:
                if fmt['format_id'] == format_id:
                    selected_format = fmt
                    break
                    
            if not selected_format:
                await message.edit_text("❌ Queued format not available anymore.")
                await process_next_in_queue(client, user_id, message)
                return
                
            # Create a simulated callback query
            fake_callback = CallbackQuery(
                client=client,
                id="queued_download",
                from_user=message.chat,
                chat_instance=message.chat.id,
                message=message,
                data=f"ytdl_{video_id}:{format_id}"
            )
            
            await message.edit_text(f"🔄 Starting next download from queue...")
            await start_download(client, fake_callback, message, video_id, format_id, info, selected_format)
        else:
            # Just a video ID, need to show format selection
            video_id = next_item
            await message.edit_text(f"🔄 Processing next video from queue...")
            
            # Create a fake message to process the next download
            fake_message = Message(
                client=client,
                chat=message.chat,
                text=f"https://youtu.be/{video_id}",
                from_user=message.from_user,
                id=message.id
            )
            
            await handle_youtube_link(client, fake_message)