import os
import re
import time
import asyncio
import html
from typing import Dict, Any, Optional
from datetime import timedelta
import humanize

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from src.logging import LOGGER
from src.helpers.filters import Main_dlURl, is_ratelimiter_dl, ytdlp_url
from src.helpers.dlp._rex import URL_REGEX
from src.helpers.dlp.yt_dl.ytdl_core import (
    download_video_from_link, clean_temporary_file, format_progress, DownloadInfo
)
from src.helpers.dlp._util import format_size, format_time

logger = LOGGER(__name__)

# Track active downloads and queues per chat
active_downloads = {}  # {chat_id: True}
download_queue = {}    # {chat_id: [Message]}
download_progress = {}  # {chat_id: {msg_id: {progress_data}}}
PROGRESS_UPDATE_INTERVAL = 2  # Seconds between progress updates
MAX_QUEUE_SIZE = 5  # Maximum number of downloads that can be queued per chat

# Format constants
PROGRESS_BAR_LENGTH = 10
FORMATS = {
    'audio': ['mp3', 'm4a', 'aac', 'flac', 'opus', 'ogg', 'wav'],
    'video': ['mp4', 'mkv', 'webm', 'avi', 'mov', '3gp', 'flv'],
    'document': ['pdf', 'doc', 'docx', 'txt', 'zip', 'rar', '7z']
}

def get_file_type(ext: str) -> str:
    """Determine file type based on extension"""
    if ext in FORMATS['audio']:
        return 'audio'
    elif ext in FORMATS['video']:
        return 'video'
    else:
        return 'document'

def create_progress_bar(percentage: float) -> str:
    """Create a visual progress bar based on percentage"""
    completed = int(PROGRESS_BAR_LENGTH * percentage / 100)
    remaining = PROGRESS_BAR_LENGTH - completed
    return '|' + '#' * completed + '-' * remaining + '|'

def format_download_progress(progress_data: Dict[str, Any]) -> str:
    """Format download progress information for display"""
    status = progress_data.get('status', 'unknown')
    
    if status == 'downloading':
        downloaded = progress_data.get('downloaded_bytes', 0)
        total = progress_data.get('total_bytes', 0)
        speed = progress_data.get('speed', 0)
        eta = progress_data.get('eta', 0)
        
        if total > 0:
            percentage = (downloaded / total) * 100
            progress_bar = create_progress_bar(percentage)
            
            return (
                f"** Downloading **\n"
                f"** Progress **: {percentage:.1f}% {progress_bar}\n"
                f"** Size **: {format_size(downloaded)}/{format_size(total)}\n"
                f"** Speed **: {format_size(speed)}/s\n"
                f"** ETA **: {format_time(eta)}"
            )
        else:
            return f"** Downloading **: {format_size(downloaded)}\n** Speed **: {format_size(speed)}/s"
    
    elif status == 'extracting_info':
        return "** Analyzing link **...\nThis may take a moment for some sites."
    
    elif status == 'waiting_in_queue':
        position = progress_data.get('position', 0)
        return f"** Queued ** (Position: {position})\nYour download will start automatically."
    
    elif status == 'uploading':
        percentage = progress_data.get('percentage', 0)
        progress_bar = create_progress_bar(percentage)
        return f"** Uploading **: {percentage:.1f}% {progress_bar}"
    
    elif status == 'finished':
        return "** Download complete! **\nPreparing to upload..."
    
    elif status == 'error':
        error = progress_data.get('error', 'Unknown error')
        return f"** Error **: {error}"
    
    elif status == 'retry':
        retry_count = progress_data.get('retry_count', 0)
        max_retries = progress_data.get('max_retries', 0)
        return f"** Retrying ** ({retry_count}/{max_retries})..."
    
    return "** Processing **..."

def get_callback_keyboard(link: str, download_info: Optional[DownloadInfo] = None, processing: bool = True) -> InlineKeyboardMarkup:
    """Generate appropriate callback keyboard based on download state"""
    buttons = []
    
    # Always show the source link
    buttons.append([InlineKeyboardButton("Source", url=link)])
    
    # If still processing, show cancel button
    if processing:
        buttons.append([InlineKeyboardButton("Cancel", callback_data=f"cancel_dl")])
    else:
        # Download completed, show format selection if applicable
        if download_info and download_info.success:
            if download_info.ext in FORMATS['video']:
                # For videos, offer conversion to audio
                buttons.append([InlineKeyboardButton("Extract Audio", callback_data=f"convert_audio")])
            
            # For all successful downloads, offer quality options if video
            if download_info.ext in FORMATS['video']:
                buttons.append([
                    InlineKeyboardButton("Other Formats", callback_data=f"show_formats")
                ])
    
    return InlineKeyboardMarkup(buttons)

@Client.on_callback_query(filters.regex(r'^cancel_dl$'))
async def handle_cancel_download(client: Client, callback_query: CallbackQuery):
    """Handle download cancellation requests"""
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    
    # Check if this is an active download message
    if chat_id in download_progress and message_id in download_progress[chat_id]:
        # Mark as cancelled in the progress data
        if download_progress[chat_id][message_id].get('cancel_callback'):
            # Call the cancellation callback
            try:
                await download_progress[chat_id][message_id]['cancel_callback']()
                await callback_query.answer("Download cancelled")
                await callback_query.message.edit_text(
                    "Download cancelled by user",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Try Again", callback_data="retry_download")
                    ]])
                )
            except Exception as e:
                logger.error(f"Error cancelling download: {e}")
                await callback_query.answer("Failed to cancel download", show_alert=True)
        else:
            await callback_query.answer("This download cannot be cancelled", show_alert=True)
    else:
        # Remove from queue if it's queued
        removed = False
        if chat_id in download_queue:
            for i, msg in enumerate(download_queue[chat_id]):
                if msg.id == callback_query.message.reply_to_message.id:
                    download_queue[chat_id].pop(i)
                    removed = True
                    break
        
        if removed:
            await callback_query.answer("Download removed from queue")
            await callback_query.message.edit_text("Download cancelled from queue")
        else:
            await callback_query.answer("No active download to cancel", show_alert=True)

@Client.on_callback_query(filters.regex(r'^retry_download$'))
async def handle_retry_download(client: Client, callback_query: CallbackQuery):
    """Handle download retry requests"""
    original_message = callback_query.message.reply_to_message
    
    if original_message:
        # Create a copy of the original message to reprocess
        await callback_query.answer("Retrying download...")
        await callback_query.message.delete()
        await video_handler(client, original_message)
    else:
        await callback_query.answer("Cannot retry, original message not found", show_alert=True)

@Client.on_message(ytdlp_url & Main_dlURl & filters.incoming & filters.text & is_ratelimiter_dl)
async def video_handler(client: Client, message: Message):
    """Handle video/media download requests from URLs"""
    chat_id = message.chat.id
    download_info = None
    msg = None
    cancel_event = asyncio.Event()
    
    # Extract URL first
    match = re.search(URL_REGEX, message.text or "")
    if not match:
        await message.reply_text("No valid link found in your message.")
        return
    link = match.group(0)
    sanitized_link = html.escape(link)
    
    # Check if a download is active for this chat
    if chat_id in active_downloads:
        # Check queue size limit
        if chat_id in download_queue and len(download_queue[chat_id]) >= MAX_QUEUE_SIZE:
            await message.reply_text(
                f"Queue limit reached ({MAX_QUEUE_SIZE} items). Please try again later.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Why", callback_data="queue_info")
                ]])
            )
            return
            
        if chat_id not in download_queue:
            download_queue[chat_id] = []
        
        # Add to queue
        queue_position = len(download_queue[chat_id]) + 1
        download_queue[chat_id].append(message)
        
        # Inform user about queue position
        queued_msg = await message.reply_text(
            f"** Queued ** (position: {queue_position})\n"
            f"** Link **: {sanitized_link[:50]}{'...' if len(link) > 50 else ''}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Cancel", callback_data="cancel_dl")
            ]])
        )
        
        # Register in progress tracking
        if chat_id not in download_progress:
            download_progress[chat_id] = {}
        download_progress[chat_id][queued_msg.id] = {
            'status': 'waiting_in_queue',
            'position': queue_position,
            'link': link
        }
        
        return

    # Mark this chat as having an active download
    active_downloads[chat_id] = True
    
    # Initialize progress tracking for this chat if not exists
    if chat_id not in download_progress:
        download_progress[chat_id] = {}

    try:
        # Send initial processing message
        msg = await message.reply_text(
            "Processing link...",
            reply_markup=get_callback_keyboard(link, processing=True)
        )
        
        # Register in progress tracking with cancel callback
        download_progress[chat_id][msg.id] = {
            'status': 'extracting_info',
            'link': link,
            'start_time': time.time(),
            'cancel_callback': lambda: cancel_event.set()
        }
        
        # Progress callback for user feedback
        last_update_time = 0
        async def progress_callback(progress_data):
            nonlocal last_update_time
            now = time.time()
            
            # Update progress tracking
            if chat_id in download_progress and msg and msg.id in download_progress[chat_id]:
                download_progress[chat_id][msg.id].update(progress_data)
            
            # Only update message at intervals to avoid flood
            if now - last_update_time >= PROGRESS_UPDATE_INTERVAL:
                try:
                    progress_text = format_download_progress(progress_data)
                    await msg.edit_text(
                        f"{progress_text}\n\n** Link **: {sanitized_link[:50]}{'...' if len(link) > 50 else ''}",
                        reply_markup=get_callback_keyboard(link, processing=True),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    last_update_time = now
                except Exception as e:
                    logger.warning(f"Failed to update progress message: {e}")
        
        # Prepare upload progress callback
        async def upload_progress_callback(current, total):
            if total > 0:
                percentage = (current / total) * 100
                await progress_callback({
                    'status': 'uploading',
                    'percentage': percentage,
                    'uploaded_bytes': current,
                    'total_bytes': total
                })
        
        # Download the video
        download_info = await download_video_from_link(
            link, 
            progress_callback=progress_callback,
            cancel_event=cancel_event
        )

        # Check if download was cancelled
        if cancel_event.is_set():
            return  # Exit early, message already updated by cancel handler
        
        if not download_info or not download_info.success:
            error_msg = download_info.error if download_info else "Unknown error occurred."
            await msg.edit_text(
                f"Download failed: {error_msg}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Try Again", callback_data="retry_download")
                ]])
            )
            return

        # Prepare file details
        file_path = download_info.file_path
        title = (download_info.title[:40] + '.') if download_info.title else 'Unknown'
        ext = download_info.ext
        performer = download_info.performer
        duration = download_info.duration
        filesize = download_info.filesize
        file_type = get_file_type(ext)
        
        # Update progress with upload status
        await progress_callback({
            'status': 'uploading',
            'percentage': 0,
            'file_type': file_type
        })
        
        # Prepare caption with metadata
        caption = (
            f"** {html.escape(download_info.title)} **\n\n"
            f"** Format **: {ext.upper()}\n"
            f"** Size **: {format_size(filesize)}\n"
        )
        
        if duration:
            caption += f"** Duration **: {str(timedelta(seconds=int(duration)))}\n"
        
        if performer:
            caption += f"** Creator **: {html.escape(performer)}\n"
        
        caption += f"\nDownloaded via @{(await client.get_me()).username}"
        
        # Upload based on file type
        if file_type == 'audio':
            await client.send_audio(
                chat_id=chat_id,
                audio=file_path,
                performer=performer,
                title=download_info.title,
                duration=duration,
                caption=caption,
                file_name=f"{download_info.title}.{ext}",
                progress=upload_progress_callback,
                reply_markup=get_callback_keyboard(link, download_info, processing=False)
            )
        elif file_type == 'video':
            await client.send_video(
                chat_id=chat_id,
                video=file_path,
                duration=duration,
                caption=caption,
                file_name=f"{download_info.title}.{ext}",
                progress=upload_progress_callback,
                reply_markup=get_callback_keyboard(link, download_info, processing=False)
            )
        else:
            await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                file_name=f"{download_info.title}.{ext}",
                progress=upload_progress_callback,
                reply_markup=get_callback_keyboard(link, download_info, processing=False)
            )

        # Success message and clean up progress message
        await msg.delete()
        
        # Send a confirmation message
        elapsed_time = time.time() - download_progress[chat_id][msg.id].get('start_time', time.time())
        await message.reply_text(
            f"Successfully downloaded and uploaded in {humanize.naturaldelta(elapsed_time)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Get Another Link", callback_data="get_another")
            ]])
        )

    except asyncio.CancelledError:
        logger.info(f"Download cancelled for chat {chat_id}")
        if msg:
            await msg.edit_text("Download cancelled")
    except Exception as e:
        logger.error(f"Error in video_handler for chat {chat_id}: {e}")
        if msg:
            await msg.edit_text(
                f"An error occurred: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Try Again", callback_data="retry_download")
                ]])
            )
    finally:
        # Cleanup temporary file
        if download_info and download_info.file_path and os.path.exists(download_info.file_path):
            try:
                clean_temporary_file(download_info.file_path)
                logger.info(f"Cleaned up file: {download_info.file_path}")
            except Exception as e:
                logger.error(f"Error cleaning up file {download_info.file_path}: {e}")

        # Remove from progress tracking
        if chat_id in download_progress and msg and msg.id in download_progress[chat_id]:
            del download_progress[chat_id][msg.id]
        
        # Remove chat from active downloads
        if chat_id in active_downloads:
            del active_downloads[chat_id]

        # Process next in queue
        await process_next_in_queue(client, chat_id)

@Client.on_callback_query(filters.regex(r'^get_another$'))
async def handle_get_another(client: Client, callback_query: CallbackQuery):
    """Handle request for downloading another link"""
    await callback_query.answer("Please send another link to download")
    await callback_query.message.edit_text(
        "Please send another link to download",
        reply_markup=None
    )

@Client.on_callback_query(filters.regex(r'^queue_info$'))
async def handle_queue_info(client: Client, callback_query: CallbackQuery):
    """Provide information about the queue system"""
    await callback_query.answer("Queue information", show_alert=True)
    queue_info = (
        f"Queue is limited to {MAX_QUEUE_SIZE} downloads per chat to ensure fair usage.\n\n"
        f"Each download is processed in order. You'll be notified when your download starts."
    )
    await callback_query.message.edit_text(queue_info)

async def process_next_in_queue(client: Client, chat_id: int):
    """Process the next queued download for the given chat."""
    if chat_id in download_queue and download_queue[chat_id]:
        next_message = download_queue[chat_id].pop(0)
        
        # Update remaining queue positions
        if chat_id in download_progress:
            for msg_id, progress in download_progress[chat_id].items():
                if progress.get('status') == 'waiting_in_queue':
                    progress['position'] = progress['position'] - 1
        
        # Start processing the next download
        await video_handler(client, next_message)
    elif chat_id in download_queue:
        del download_queue[chat_id]  # Clean up empty queue