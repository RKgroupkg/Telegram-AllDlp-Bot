import os
import re
import time
import asyncio
import html
from typing import Dict, Any, Optional, Callable, List, Tuple, Union
from datetime import timedelta
import contextlib
from functools import wraps
from enum import Enum, auto

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from src.logging import LOGGER
from src.helpers.filters import Main_dlURl, is_ratelimiter_dl, ytdlp_url
from src.helpers.dlp._rex import URL_REGEX
from src.helpers.dlp.yt_dl.ytdl_core import (
    download_video_from_link, clean_temporary_file, DownloadInfo
)
from src.helpers.dlp._util import format_size, format_time
from src.helpers.dlp._Thumb.thumbnail import download_and_verify_thumbnail, delete_thumbnail


logger = LOGGER(__name__)

# Configuration constants
class Config:
    PROGRESS_UPDATE_INTERVAL = 6  # Seconds between progress updates
    MAX_QUEUE_SIZE = 2  # Maximum number of downloads that can be queued per chat
    PROGRESS_BAR_LENGTH = 10
    MAX_RETRY_COUNT = 3
    LINK_PREVIEW_LENGTH = 50
    TITLE_MAX_LENGTH = 40
    
    class FileFormats:
        AUDIO = ['mp3', 'm4a', 'aac', 'flac', 'opus', 'ogg', 'wav']
        VIDEO = ['mp4', 'mkv', 'webm', 'avi', 'mov', '3gp', 'flv']
        DOCUMENT = ['pdf', 'doc', 'docx', 'txt', 'zip', 'rar', '7z']

# Status enum for better type safety
class DownloadStatus(Enum):
    EXTRACTING_INFO = auto()
    DOWNLOADING = auto()
    WAITING_IN_QUEUE = auto()
    UPLOADING = auto()
    FINISHED = auto()
    ERROR = auto()
    RETRY = auto()
    CANCELLED = auto()

# State management classes
class DownloadManager:
    """Manages download state across chats"""
    
    def __init__(self):
        self.active_downloads = {}  # {chat_id: True}
        self.download_queue = {}    # {chat_id: [Message]}
        self.download_progress = {}  # {chat_id: {msg_id: {progress_data}}}
    
    def is_chat_active(self, chat_id: int) -> bool:
        """Check if a chat has an active download"""
        return chat_id in self.active_downloads
    
    def set_chat_active(self, chat_id: int) -> None:
        """Mark a chat as having an active download"""
        self.active_downloads[chat_id] = True
    
    def clear_chat_active(self, chat_id: int) -> None:
        """Clear a chat's active download status"""
        if chat_id in self.active_downloads:
            del self.active_downloads[chat_id]
    
    def get_queue_position(self, chat_id: int) -> int:
        """Get the current queue size for a chat"""
        if chat_id not in self.download_queue:
            return 0
        return len(self.download_queue[chat_id])
    
    def queue_is_full(self, chat_id: int) -> bool:
        """Check if the queue for a chat is full"""
        return self.get_queue_position(chat_id) >= Config.MAX_QUEUE_SIZE
    
    def add_to_queue(self, chat_id: int, message: Message) -> int:
        """Add a message to download queue and return position"""
        if chat_id not in self.download_queue:
            self.download_queue[chat_id] = []
        
        self.download_queue[chat_id].append(message)
        return len(self.download_queue[chat_id])
    
    def remove_from_queue(self, chat_id: int, message_id: int) -> bool:
        """Remove a message from queue by ID, return True if successful"""
        if chat_id not in self.download_queue:
            return False
            
        for i, msg in enumerate(self.download_queue[chat_id]):
            if msg.id == message_id:
                self.download_queue[chat_id].pop(i)
                return True
        
        return False
    
    def get_next_in_queue(self, chat_id: int) -> Optional[Message]:
        """Get the next message in queue for processing"""
        if chat_id in self.download_queue and self.download_queue[chat_id]:
            msg = self.download_queue[chat_id].pop(0)
            
            # Update remaining queue positions
            if chat_id in self.download_progress:
                for msg_id, progress in self.download_progress[chat_id].items():
                    if progress.get('status') == DownloadStatus.WAITING_IN_QUEUE:
                        progress['position'] = progress['position'] - 1
            
            # Clean up if queue is empty
            if not self.download_queue[chat_id]:
                del self.download_queue[chat_id]
                
            return msg
            
        return None
    
    def register_progress(self, chat_id: int, msg_id: int, progress_data: Dict) -> None:
        """Register or update progress tracking for a message"""
        if chat_id not in self.download_progress:
            self.download_progress[chat_id] = {}
        
        if msg_id in self.download_progress[chat_id]:
            self.download_progress[chat_id][msg_id].update(progress_data)
        else:
            self.download_progress[chat_id][msg_id] = progress_data
    
    def clear_progress(self, chat_id: int, msg_id: int) -> None:
        """Remove progress tracking for a message"""
        if chat_id in self.download_progress and msg_id in self.download_progress[chat_id]:
            del self.download_progress[chat_id][msg_id]
            
            # Clean up if no more progresses for the chat
            if not self.download_progress[chat_id]:
                del self.download_progress[chat_id]

# Initialize the download manager
download_manager = DownloadManager()

# Utility functions
def get_file_type(ext: str) -> str:
    """Determine file type based on extension"""
    if ext in Config.FileFormats.AUDIO:
        return 'audio'
    elif ext in Config.FileFormats.VIDEO:
        return 'video'
    else:
        return 'document'

def create_progress_bar(percentage: float) -> str:
    """Create a visual progress bar based on percentage"""
    completed = int(Config.PROGRESS_BAR_LENGTH * percentage / 100)
    remaining = Config.PROGRESS_BAR_LENGTH - completed
    return '|' + '▰' * completed + '▱' * remaining + '|'

def format_download_progress(progress_data: Dict[str, Any]) -> str:
    """Format download progress information for display"""
    status = progress_data.get('status', 'unknown')
    
    if status == DownloadStatus.DOWNLOADING:
        downloaded = progress_data.get('downloaded_bytes', 0)
        total = progress_data.get('total_bytes', 0)
        speed = progress_data.get('speed', 0)
        eta = progress_data.get('eta', 0)
        
        if total > 0:
            percentage = (downloaded / total) * 100
            progress_bar = create_progress_bar(percentage)
            
            return (
                f"♔ ** Downloading **\n"
                f"۞ ** Progress **: __{percentage:.1f}% {progress_bar}__\n"
                f"✧ ** Size **: {format_size(downloaded)}/{format_size(total)}\n"
                f"✦ ** Speed **: {format_size(speed)}/s\n"
                f"✿ ** ETA **: {format_time(eta)}"
            )
        else:
            return f"♔ ** Downloading **: __{format_size(downloaded)}__\n✦ ** Speed **: __{format_size(speed)}/s__"
    
    elif status == DownloadStatus.EXTRACTING_INFO:
        return "♔ ** Analyzing link **...\n__This may take a moment for some sites.__"
    
    elif status == DownloadStatus.WAITING_IN_QUEUE:
        position = progress_data.get('position', 0)
        return f"♔ ** Queued ** (Position: {position})\n__Your download will start automatically.__"
    
    elif status == DownloadStatus.UPLOADING:
        percentage = progress_data.get('percentage', 0)
        progress_bar = create_progress_bar(percentage)
        return f"♔ ** Uploading **: __{percentage:.1f}% {progress_bar}__"
    
    elif status == DownloadStatus.FINISHED:
        return "♔ ** Download complete! **\n__Preparing to upload...__"
    
    elif status == DownloadStatus.ERROR:
        error = progress_data.get('error', 'Unknown error')
        return f"⚠ ** Error **: __{error}__"
    
    elif status == DownloadStatus.RETRY:
        retry_count = progress_data.get('retry_count', 0)
        max_retries = progress_data.get('max_retries', 0)
        return f"❀ ** Retrying ** ({retry_count}/{max_retries})..."
    
    elif status == DownloadStatus.CANCELLED:
        return "♔ ** Download cancelled by user **"
        
    return "♔ ** Processing **..."

def get_callback_keyboard(
    link: str, 
    download_info: Optional[DownloadInfo] = None, 
    processing: bool = True,
    is_queued: bool = False
) -> InlineKeyboardMarkup:
    """Generate appropriate callback keyboard based on download state"""
    buttons = []
    
    # Always show the source link
    buttons.append([InlineKeyboardButton("❀ Source", url=link)])
    
    # If still processing or queued, show cancel button
    if processing or is_queued:
        buttons.append([InlineKeyboardButton("✘ Cancel", callback_data=f"cancel_dl")])
    
    # When completed, could add more options here in the future
    # if not processing and download_info and download_info.success:
    #     if download_info.ext in Config.FileFormats.VIDEO:
    #         buttons.append([InlineKeyboardButton("❀ Extract Audio", callback_data=f"convert_audio")])
    #         buttons.append([InlineKeyboardButton("❀ Other Formats", callback_data=f"show_formats")])
    
    return InlineKeyboardMarkup(buttons)

# Decorator for error handling and cleanup
def download_handler(func):
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        chat_id = message.chat.id
        download_info = None
        msg = None
        cancel_event = asyncio.Event()
        thumb_path = None
        
        try:
            result = await func(client, message, cancel_event, *args, **kwargs)
            return result
        except asyncio.CancelledError:
            logger.info(f"Download cancelled for chat {chat_id}")
            if msg:
                await msg.edit_text("♔ Download cancelled")
        except Exception as e:
            logger.error(f"Error in {func.__name__} for chat {chat_id}: {e}", exc_info=True)
            if msg:
                await msg.edit_text(
                    f"♔ An error occurred: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✿ Try Again", callback_data="retry_download")
                    ]])
                )
        finally:
            # Cleanup resources
            
            # Thumbnail cleanup
            if thumb_path and os.path.exists(thumb_path):
                try:
                    delete_thumbnail(thumb_path)
                except Exception as e:
                    logger.error(f"Error cleaning up thumbnail {thumb_path}: {e}")
            
            # Temporary file cleanup
            if download_info and download_info.file_path and os.path.exists(download_info.file_path):
                try:
                    await clean_temporary_file(download_info.file_path)
                    logger.info(f"Cleaned up file: {download_info.file_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {download_info.file_path}: {e}")
            
            # Progress tracking cleanup
            if chat_id in download_manager.download_progress and msg and msg.id in download_manager.download_progress[chat_id]:
                download_manager.clear_progress(chat_id, msg.id)
            
            # Release active download status
            download_manager.clear_chat_active(chat_id)
            
            # Process next in queue
            next_message = download_manager.get_next_in_queue(chat_id)
            if next_message:
                await video_handler(client, next_message)
    
    return wrapper

# Callback handlers
@Client.on_callback_query(filters.regex(r'^cancel_dl$'))
async def handle_cancel_download(client: Client, callback_query: CallbackQuery):
    """Handle download cancellation requests"""
    chat_id = callback_query.message.chat.id
    message_id = callback_query.message.id
    
    # Check if this is an active download message
    if chat_id in download_manager.download_progress and message_id in download_manager.download_progress[chat_id]:
        # Mark as cancelled in the progress data
        if download_manager.download_progress[chat_id][message_id].get('cancel_callback'):
            # Call the cancellation callback
            try:
                await download_manager.download_progress[chat_id][message_id]['cancel_callback']()
                await callback_query.answer("Download cancelled")
                await callback_query.message.edit_text(
                    "♔ Download cancelled by user",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("❀ Try Again", callback_data="retry_download")
                    ]])
                )
            except Exception as e:
                logger.error(f"Error cancelling download: {e}")
                await callback_query.answer("⚠ Failed to cancel download", show_alert=True)
        else:
            await callback_query.answer("⚠ This download cannot be cancelled", show_alert=True)
    else:
        # Check if it's from a queued message
        removed = False
        
        # If the message is a reply to the original request message
        if callback_query.message.reply_to_message:
            original_msg_id = callback_query.message.reply_to_message.id
            removed = download_manager.remove_from_queue(chat_id, original_msg_id)
        
        if removed:
            await callback_query.answer("♔ Download removed from queue")
            await callback_query.message.edit_text("♔ Download cancelled from queue")
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

@Client.on_callback_query(filters.regex(r'^queue_info$'))
async def handle_queue_info(client: Client, callback_query: CallbackQuery):
    """Provide information about the queue system"""
    await callback_query.answer("Queue information", show_alert=True)
    queue_info = (
        f"Queue is limited to {Config.MAX_QUEUE_SIZE} downloads per chat to ensure fair usage.\n\n"
        f"Each download is processed in order. You'll be notified when your download starts."
    )
    await callback_query.message.edit_text(queue_info)

# Main download handler
@Client.on_message(ytdlp_url & Main_dlURl & filters.incoming & filters.text & is_ratelimiter_dl)



# Main download handler for direct messages
@Client.on_message(ytdlp_url & Main_dlURl & filters.text & is_ratelimiter_dl)
async def text_msg_handler(client: Client, message: Message):
    """Handle video/media download requests from URLs"""
    await video_handler(client, message)

# Handler for /dl command
@Client.on_message(filters.command("dl") & ytdlp_url & filters.incoming & filters.text & is_ratelimiter_dl)
async def dl_command_handler(client: Client, message: Message):
    """Handle download requests through the /dl command"""
    await video_handler(client, message)


async def video_handler(client: Client, message: Message):
    """Handle video/media download requests from URLs"""
    chat_id = message.chat.id
    download_info = None
    msg = None
    cancel_event = asyncio.Event()
    thumb_path = None
    
    # Extract URL first
    match = re.search(URL_REGEX, message.text or "")
    if not match:
        await message.reply_text("⚠ No valid link found in your message.")
        return
    link = match.group(0)
    sanitized_link = html.escape(link)
    shortened_link = f"{sanitized_link[:Config.LINK_PREVIEW_LENGTH]}{'...' if len(link) > Config.LINK_PREVIEW_LENGTH else ''}"
    
    # Check if a download is active for this chat
    if download_manager.is_chat_active(chat_id):
        # Check queue size limit
        if download_manager.queue_is_full(chat_id):
            await message.reply_text(
                f"⚠ Queue limit reached ({Config.MAX_QUEUE_SIZE} items). Please try again later.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Why?", callback_data="queue_info")
                ]]),
                disable_web_page_preview=True,
            )
            return
            
        # Add to queue
        queue_position = download_manager.add_to_queue(chat_id, message)
        
        # Inform user about queue position
        queued_msg = await message.reply_text(
            f"** Queued ** (position: {queue_position})\n"
            f"** Link **: {shortened_link}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Cancel", callback_data="cancel_dl")
            ]]),
            disable_web_page_preview=True,
        )
        
        # Register in progress tracking
        download_manager.register_progress(chat_id, queued_msg.id, {
            'status': DownloadStatus.WAITING_IN_QUEUE,
            'position': queue_position,
            'link': link
        })
        
        return

    # Mark this chat as having an active download
    download_manager.set_chat_active(chat_id)
    
    try:
        # Send initial processing message
        msg = await message.reply_text(
            "Processing link...",
            reply_markup=get_callback_keyboard(link, processing=True)
        )
        
        # Register in progress tracking with cancel callback
        download_manager.register_progress(chat_id, msg.id, {
            'status': DownloadStatus.EXTRACTING_INFO,
            'link': link,
            'start_time': time.time(),
            'cancel_callback': lambda: cancel_event.set()
        })
        
        # Progress callback for user feedback
        last_update_time = 0
        last_progress_text = ""
        async def progress_callback(progress_data):
            nonlocal last_update_time, last_progress_text
            now = time.time()
            
            # Update progress tracking
            download_manager.register_progress(chat_id, msg.id, progress_data)
            
            # Only update message at intervals to avoid flood
            if now - last_update_time >= Config.PROGRESS_UPDATE_INTERVAL:
                try:
                    progress_text = format_download_progress(progress_data)
                    new_text = f"{progress_text}\n\n** Link **: {shortened_link}"
                    
                    # Only update if the text has changed
                    if new_text != last_progress_text:
                        await msg.edit_text(
                            new_text,
                            reply_markup=get_callback_keyboard(link, processing=True),
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=True
                        )
                        last_progress_text = new_text
                    
                    last_update_time = now
                except Exception as e:
                    # Specifically ignore MessageNotModified error
                    if "MESSAGE_NOT_MODIFIED" not in str(e):
                        logger.warning(f"Failed to update progress message: {e}")
                        
        # Prepare upload progress callback
        async def upload_progress_callback(current, total):
            if total > 0:
                percentage = (current / total) * 100
                await progress_callback({
                    'status': DownloadStatus.UPLOADING,
                    'percentage': percentage,
                    'uploaded_bytes': current,
                    'total_bytes': total
                })
        
        # Download the video with retry logic
        retry_count = 0
        max_retries = Config.MAX_RETRY_COUNT
        
        while retry_count <= max_retries:
            if retry_count > 0:
                await progress_callback({
                    'status': DownloadStatus.RETRY,
                    'retry_count': retry_count,
                    'max_retries': max_retries
                })
                
            try:
                download_info = await download_video_from_link(
                    link, 
                    progress_callback=progress_callback,
                    cancel_event=cancel_event
                )
                
                # Break if successful or definitely failed (not a temporary error)
                if download_info and download_info.success:
                    break
                    
                # If it's a definite failure (not just a network issue)
                if download_info and not download_info.should_retry:
                    break
                    
                retry_count += 1
                
                # Wait before retrying
                if retry_count <= max_retries:
                    await asyncio.sleep(2 * retry_count)  # Exponential backoff
                    
            except Exception as e:
                logger.error(f"Download error (attempt {retry_count}/{max_retries}): {e}")
                retry_count += 1
                
                if retry_count <= max_retries:
                    await asyncio.sleep(2 * retry_count)
                else:
                    # Create a failure download_info
                    download_info = DownloadInfo(
                        success=False,
                        error=f"Failed after {max_retries} attempts: {str(e)}",
                        should_retry=False
                    )
                    break

        # Check if download was cancelled
        if cancel_event.is_set():
            return  # Exit early, message already updated by cancel handler
        
        if not download_info or not download_info.success:
            error_msg = download_info.error if download_info else "Unknown error occurred."
            await msg.edit_text(
                f"Download failed: {error_msg}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Try Again", callback_data="retry_download")
                ]]),
                disable_web_page_preview=True,
            )
            return

        # Prepare file details
        file_path = download_info.file_path
        title = (download_info.title[:Config.TITLE_MAX_LENGTH] + '..') if download_info.title and len(download_info.title) > Config.TITLE_MAX_LENGTH else (download_info.title or 'Unknown')
        thumbnail = download_info.thumbnail 
        ext = download_info.ext
        performer = download_info.performer
        duration = download_info.duration
        filesize = download_info.filesize
        file_type = get_file_type(ext)

        # Get the thumbnail 
        if thumbnail:
            is_thumbnail_ok, thumb_path = await download_and_verify_thumbnail(thumbnail)
            logger.info(f"Thumbnail download status: {is_thumbnail_ok}, path: {thumb_path}")
        else:
            is_thumbnail_ok = False
            thumb_path = None

        # Update progress with upload status
        await progress_callback({
            'status': DownloadStatus.UPLOADING,
            'percentage': 0,
            'file_type': file_type
        })
        
        # Prepare caption with metadata
        caption = (
            f"≡ **__{html.escape(title)}__ **\n\n"
            f"♚ **Format **: __{ext.upper()}__\n"
            f"✿ **Size **: __{format_size(filesize)}__\n"
        )
        
        if duration:
            duration_str = time.strftime('%H:%M:%S', time.gmtime(duration)) if duration >= 3600 else time.strftime('%M:%S', time.gmtime(duration))
            caption += f"⏱ **Duration **: __{duration_str}__\n"
            
        if performer:
            caption += f"♚ **Creator **: __{html.escape(performer)}__\n"
        
        caption += f"\n__via__ @{(await client.get_me()).username}"
        
        # Upload based on file type
        upload_start_time = time.time()
        
        try:
            if file_type == 'audio':
                await client.send_audio(
                    chat_id=chat_id,
                    audio=file_path,
                    thumb=thumb_path if is_thumbnail_ok else None,
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
                    thumb=thumb_path if is_thumbnail_ok else None,
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
                
            upload_time = time.time() - upload_start_time
            logger.info(f"Upload completed in {upload_time:.2f} seconds for file {download_info.title}.{ext}")
            
            # Success message and clean up progress message
            await msg.delete()
            
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            await msg.edit_text(
                f"Download successful but upload failed: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Try Again", callback_data="retry_download")
                ]]),
                disable_web_page_preview=True
            )
            
    except asyncio.CancelledError:
        raise  # Re-raise to be handled by the outer try-except
    except Exception as e:
        logger.error(f"Error in video_handler for chat {chat_id}: {e}", exc_info=True)
        if msg:
            await msg.edit_text(
                f"♔ An error occurred: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✿ Try Again", callback_data="retry_download")
                ]])
            )
    finally:
        # Cleanup temporary files
        if download_info and download_info.file_path and os.path.exists(download_info.file_path):
            try:
                clean_temporary_file(download_info.file_path)
                logger.info(f"Cleaned up file: {download_info.file_path}")
            except Exception as e:
                logger.error(f"Error cleaning up file {download_info.file_path}: {e}")
                
        # Cleanup thumbnail
        if thumb_path and os.path.exists(thumb_path):
            try:
                delete_thumbnail(thumb_path)
            except Exception as e:
                logger.error(f"Error cleaning up thumbnail {thumb_path}: {e}")

        # Remove from progress tracking
        if chat_id in download_manager.download_progress and msg and msg.id in download_manager.download_progress[chat_id]:
            download_manager.clear_progress(chat_id, msg.id)
        
        # Remove chat from active downloads
        download_manager.clear_chat_active(chat_id)

        # Process next in queue
        next_message = download_manager.get_next_in_queue(chat_id)
        if next_message:
            await video_handler(client, next_message)