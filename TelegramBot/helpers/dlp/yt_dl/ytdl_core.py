import os
import time
import random
import asyncio
import logging
import yt_dlp
import threading
from datetime import timedelta
from typing import Dict, Any, Callable, Coroutine, Optional, List, Set
from concurrent.futures import ThreadPoolExecutor


from TelegramBot.logging import LOGGER
logger = LOGGER(__name__)

from TelegramBot.config import(
    COOKIE_ROTATION_COOLDOWN, # seconds between using the same cookie file
    DEFAULT_COOKIES_DIR,
    YT_PROGRESS_UPDATE_INTERVAL,
    YT_DOWNLOAD_PATH,
    MAX_VIDEO_LENGTH_MINUTES,
    
)

# Ensure download directory exists
os.makedirs(YT_DOWNLOAD_PATH, exist_ok=True)
os.makedirs(DEFAULT_COOKIES_DIR, exist_ok=True)

# Cookie rotation management
class CookieManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CookieManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.cookies_dir = DEFAULT_COOKIES_DIR
        self.cookies_files = []
        self.cookie_usage_history = {}
        self.refresh_cookies_list()
        self._initialized = True
        self._lock = asyncio.Lock()
        
    def refresh_cookies_list(self):
        """Refresh the list of available cookie files"""
        self.cookies_files = []
        if os.path.isdir(self.cookies_dir):
            for file in os.listdir(self.cookies_dir):
                if file.endswith('.txt'):
                    self.cookies_files.append(os.path.join(self.cookies_dir, file))
        
        # Add the root cookies.txt if it exists
        if os.path.exists('cookies.txt'):
            self.cookies_files.append('cookies.txt')
            
        logger.info(f"Found {len(self.cookies_files)} cookie files")
    
    async def get_cookie_file(self) -> Optional[str]:
        """Get the next cookie file to use based on rotation policy"""
        async with self._lock:
            now = time.time()
            
            # If no cookies available, return None
            if not self.cookies_files:
                return None
                
            # Filter cookies that aren't in cooldown
            available_cookies = [
                cookie for cookie in self.cookies_files
                if now - self.cookie_usage_history.get(cookie, 0) >= COOKIE_ROTATION_COOLDOWN
            ]
            
            # If all cookies are in cooldown, use the least recently used one
            if not available_cookies:
                cookie = min(self.cookies_files, key=lambda x: self.cookie_usage_history.get(x, 0))
            else:
                cookie = random.choice(available_cookies)
                
            # Update usage history
            self.cookie_usage_history[cookie] = now
            return cookie

cookie_manager = CookieManager()

# Thread-local storage for event loops
_thread_local = threading.local()

def get_or_create_eventloop():
    """Get the current event loop or create a new one for the current thread"""
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        # If there's no event loop in this thread, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

class DownloadTracker:
    """Class to track download progress and manage callbacks"""
    def __init__(self, callback: Callable[[Dict[str, Any]], Coroutine], interval: float = YT_PROGRESS_UPDATE_INTERVAL):
        self.callback = callback
        self.interval = interval
        self.last_update_time = 0
        self.start_time = time.time()
        self.progress_data = {'status': 'starting'}
        
    async def update(self, progress: Dict[str, Any]):
        """Update progress and potentially trigger callback"""
        now = time.time()
        status = progress.get('status', '')
        
        # Update our data
        self.progress_data.update(progress)  # Use update() instead of assignment to preserve the status field
        
        # Always update on 'finished' or 'error' status
        if status in ('finished', 'error'):
            await self.force_update()
            return

        # Update based on time interval
        if now - self.last_update_time >= self.interval:
            await self.force_update()
    
    async def force_update(self):
        """Force a progress update"""
        self.last_update_time = time.time()
        
        # Format the progress data
        if 'downloaded_bytes' in self.progress_data and 'total_bytes' in self.progress_data:
            formatted_progress = await format_progress(
                self.progress_data.get('downloaded_bytes', 0),
                self.progress_data.get('total_bytes', 0),
                self.start_time
            )
            update_data = {
                **self.progress_data,
                'formatted_progress': formatted_progress
            }
        else:
            update_data = self.progress_data
            
        # Call the callback
        try:
            await self.callback(update_data)
        except Exception as e:
            logger.error(f"Error in progress callback: {str(e)}")

class DownloadPool:
    """Manages concurrent downloads to limit system resources"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DownloadPool, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_concurrent: int = 3):
        if self._initialized:
            return
            
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._initialized = True
        
    async def run_download(self, fn, *args, **kwargs):
        """Run a download function with concurrency limits"""
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self.executor, fn, *args, **kwargs)

download_pool = DownloadPool()

async def fetch_youtube_info(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch information about a YouTube video
    
    Args:
        video_id: The YouTube video ID
        
    Returns:
        Dictionary containing video information or None if an error occurred
    """
    # Get a cookie file
    cookie_file = await cookie_manager.get_cookie_file()
    
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extract_flat': 'in_playlist',
        'ignoreerrors': True,
    }
    
    # Add cookie file if available
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file
    
    try:
        def extract_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        
        # Run extraction in thread pool
        info = await download_pool.run_download(extract_info)
        
        if not info:
            logger.warning(f"Failed to fetch info for video {video_id}")
            return None
            
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
        
        # Save relevant info
        result = {
            'title': info.get('title', 'Unknown Title'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', None),
            'uploader': info.get('uploader', 'Unknown'),
            'view_count': info.get('view_count', 0),
            'upload_date': info.get('upload_date', ''),
            'description': info.get('description', ''),
            'formats': formats,
            'all_formats': formats,
            'video_formats': video_formats,
            'audio_formats': audio_formats,
            'combined_formats': combined_formats
        }
        
        return result
    except Exception as e:
        logger.error(f"Error fetching YouTube info for {video_id}: {str(e)}")
        return None

async def format_progress(current: int, total: int, start_time: float) -> str:
    """
    Format download progress information
    
    Args:
        current: Current downloaded bytes
        total: Total bytes to download
        start_time: Time when download started
        
    Returns:
        Formatted progress string
    """
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

async def download_youtube_video(
    video_id: str, 
    format_id: str, 
    progress_callback: Callable[[Dict[str, Any]], Coroutine]
) -> Dict[str, Any]:
    """
    Download a YouTube video with progress updates
    
    Args:
        video_id: YouTube video ID
        format_id: Format ID to download
        progress_callback: Async callback function for progress updates
        
    Returns:
        Dictionary with download results
    """
    # Get a cookie file
    cookie_file = await cookie_manager.get_cookie_file()
    
    # Create a download tracker for progress updates
    tracker = DownloadTracker(progress_callback)
    
    # Create output filename with temp suffix during download
    output_template = f'{YT_DOWNLOAD_PATH}/%(id)s.%(ext)s'
    
    ydl_opts = {
        'format': format_id,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'outtmpl': output_template,
        'socket_timeout': 30,
        'retries': 5,
        'fragment_retries': 5,
        'ignoreerrors': False,
    }
    
    # Add cookie file if available
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file
    
    # Use a queue for thread-safe progress updates
    progress_queue = asyncio.Queue()
    stop_event = threading.Event()
    
    # Task that processes progress updates from the queue
    async def process_progress_updates():
        while not stop_event.is_set() or not progress_queue.empty():
            try:
                progress_data = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                await tracker.update(progress_data)
                progress_queue.task_done()
            except asyncio.TimeoutError:
                # No updates in queue, just continue
                pass
            except Exception as e:
                logger.error(f"Error processing progress update: {str(e)}")
    
    # Get the current loop for thread-safe operations
    main_loop = asyncio.get_running_loop()
    
    # Progress hook that puts updates in the queue rather than creating tasks directly
    def progress_hook(d):
        try:
            # Create a copy to avoid reference issues and ensure status is present
            update_data = d.copy()
            if 'status' not in update_data:
                update_data['status'] = 'unknown'
                
            # Put in the queue using run_coroutine_threadsafe
            asyncio.run_coroutine_threadsafe(progress_queue.put(update_data), main_loop)
        except Exception as e:
            logger.error(f"Error in progress hook: {str(e)}")
    
    ydl_opts['progress_hooks'] = [progress_hook]
    
    # Start the progress processing task
    progress_task = asyncio.create_task(process_progress_updates())
    
    try:
        def download_fn():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            except Exception as e:
                logger.error(f"Error in download thread: {str(e)}")
                return {'error': str(e)}
        
        # Run download in thread pool
        info = await download_pool.run_download(download_fn)
        
        # Stop the progress processing
        stop_event.set()
        await progress_task
        
        if not info or 'error' in info:
            error_msg = info.get('error', 'Failed to download video') if info else 'Failed to download video'
            return {
                'success': False,
                'error': error_msg
            }
        
        # Determine actual file path
        if 'requested_downloads' in info and info['requested_downloads']:
            file_path = info['requested_downloads'][0]['filepath']
        else:
            file_path = os.path.join(YT_DOWNLOAD_PATH, f"{video_id}.{info['ext']}")
        
        return {
            'success': True,
            'file_path': file_path,
            'title': info.get('title', 'Unknown Title'),
            'ext': info.get('ext', 'unknown'),
            'filesize': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            'duration': info.get('duration', 0)
        }
    except Exception as e:
        logger.error(f"Error downloading YouTube video {video_id}: {str(e)}")
        # Stop the progress processing
        stop_event.set()
        try:
            await progress_task
        except:
            pass
            
        # Send one final error update with a guaranteed status field
        final_update = {
            'status': 'error',
            'error': str(e),
            'video_id': video_id
        }
        # Update progress data instead of replacing it
        tracker.progress_data.update(final_update)
        await tracker.force_update()
        
        return {
            'success': False,
            'error': str(e)
        }
    finally:
        # Ensure progress task is completed
        stop_event.set()
        try:
            if not progress_task.done():
                await progress_task
        except:
            pass

def is_valid_youtube_id(video_id: str) -> bool:
    """
    Check if the provided string is a valid YouTube video ID
    
    Args:
        video_id: String to check
        
    Returns:
        True if valid, False otherwise
    """
    # Basic validation: YouTube IDs are 11 characters long and contain alphanumeric chars, underscore and dash
    return len(video_id) == 11 and all(c.isalnum() or c in '-_' for c in video_id)

def get_formats_by_type(info: Dict[str, Any], filter_type: str) -> List[Dict[str, Any]]:
    """
    Get formats filtered by type
    
    Args:
        info: Video info dictionary
        filter_type: Type of formats to return ('all', 'video', 'audio')
        
    Returns:
        List of formats
    """
    if not info:
        return []
        
    if filter_type == "all":
        return info.get('all_formats', [])
    elif filter_type == "video":
        return info.get('combined_formats', []) + info.get('video_formats', [])
    elif filter_type == "audio":
        return info.get('audio_formats', [])
    else:
        return info.get('all_formats', [])

def is_audio_format(format_info: Dict[str, Any]) -> bool:
    """
    Determine if a format is audio-only
    
    Args:
        format_info: Format information dictionary
        
    Returns:
        True if audio-only, False otherwise
    """
    return format_info.get('acodec') != 'none' and format_info.get('vcodec') == 'none'

def clean_temporary_file(file_path: str) -> bool:
    """
    Clean up a downloaded file
    
    Args:
        file_path: Path to the file to delete
        
    Returns:
        True if successfully deleted, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted temporary file: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error cleaning up file {file_path}: {str(e)}")
        return False