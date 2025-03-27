import os
import time
import random
import asyncio
import logging

import shutil
import tempfile

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
    CATCH_PATH,
    MAX_VIDEO_LENGTH_MINUTES,
)

# Ensure download directory exists
os.makedirs(CATCH_PATH, exist_ok=True)
os.makedirs(DEFAULT_COOKIES_DIR, exist_ok=True)




# Utils
def beautify_views(views):
    """
    Format view counts in a human-readable way.
    
    Handles various input types including strings, integers, and floats.
    Supports inputs with non-digit characters and handles edge cases.
    
    Args:
        views: The view count (string, integer, float, or None)
        
    Returns:
        Formatted view count as a string (e.g., "1.2k", "3.4m", "42")
    
    Examples:
        >>> beautify_views(1234)
        '1.2k'
        >>> beautify_views('56,789')
        '56.8k'
        >>> beautify_views(1234567)
        '1.2m'
        >>> beautify_views(None)
        '0'
        >>> beautify_views('abc')
        '0'
    """
    # Handle None or empty inputs
    if views is None:
        return "0"
    
    # Convert input to string and extract only digits
    try:
        # Remove any non-digit characters except potential decimal point
        views_str = ''.join(char for char in str(views) if char.isdigit() or char == '.')
        
        # Convert to float, handling potential conversion errors
        views_num = float(views_str) if views_str else 0
    except (ValueError, TypeError):
        return "0"
    
    # Format based on magnitude
    if views_num < 1000:
        return str(int(views_num))
    elif views_num < 1_000_000:
        return f"{views_num / 1000:.1f}k"
    elif views_num < 1_000_000_000:
        return f"{views_num / 1_000_000:.1f}m"
    else:
        return f"{views_num / 1_000_000_000:.1f}b"


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
        self._lock = asyncio.Lock()
        self.refresh_cookies_list()
        self._initialized = True
    
    def fix_cookie_file(self, input_file, output_file):
        """Fix cookie file by ensuring tab separation in cookie entries."""
        for line in input_file:
            stripped = line.lstrip()
            if stripped == "" or stripped.startswith("#"):
                # Preserve empty lines and comments
                output_file.write(line)
            else:
                # Check if already correctly formatted with tabs
                tab_parts = line.split("\t")
                if len(tab_parts) == 7:
                    # Already fixed, write as is
                    output_file.write(line)
                else:
                    # Split by whitespace and reconstruct if possible
                    space_parts = line.split()
                    if len(space_parts) >= 6:
                        # Take first 6 fields, rest is value
                        domain, flag, path, secure, expiration, name = space_parts[:6]
                        value = " ".join(space_parts[6:]) if len(space_parts) > 6 else ""
                        new_line = "\t".join([domain, flag, path, secure, expiration, name, value]) + "\n"
                        output_file.write(new_line)
                    else:
                        # Invalid line, preserve and warn
                        output_file.write(line)
                        logger.error(f"Warning: invalid line in {input_file.name}: {line.strip()}")

    def refresh_cookies_list(self):
        """Refresh the list of available cookie files"""
        self.cookies_files = []
        if os.path.isdir(self.cookies_dir):
            for file in os.listdir(self.cookies_dir):
                if file.endswith('.txt'):
                    cookie_path = os.path.join(self.cookies_dir, file)
                    
    
                    with open(cookie_path, 'r', encoding='utf-8') as input_file:
                        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as temp_file:
                            self.fix_cookie_file(input_file, temp_file)
                        temp_filename = temp_file.name
                    shutil.move(temp_filename, cookie_path)
                    logger.info(f"Processed {cookie_path}")
                    
                    # Verify the file is readable and not empty
                    if os.path.getsize(cookie_path) > 0:
                        self.cookies_files.append(cookie_path)
        
        # Add the root cookies.txt if it exists and is not empty
        if os.path.exists('cookies.txt') and os.path.getsize('cookies.txt') > 0:
            self.cookies_files.append('cookies.txt')
            
        logger.info(f"Found {len(self.cookies_files)} valid cookie files")
    
    async def get_cookie_file(self) -> Optional[str]:
        """Get the next cookie file to use based on rotation policy"""
        async with self._lock:
            now = time.time()
            
            # If no cookies available, return None
            if not self.cookies_files:
                # Try refreshing once more in case new cookies were added
                self.refresh_cookies_list()
                if not self.cookies_files:
                    logger.warning("No cookie files available")
                    return None
                
            # Filter cookies that aren't in cooldown
            available_cookies = [
                cookie for cookie in self.cookies_files
                if now - self.cookie_usage_history.get(cookie, 0) >= COOKIE_ROTATION_COOLDOWN
            ]
            
            # If all cookies are in cooldown, use the least recently used one
            if not available_cookies:
                cookie = min(self.cookies_files, key=lambda x: self.cookie_usage_history.get(x, 0))
                logger.debug(f"All cookies in cooldown, using least recently used: {os.path.basename(cookie)}")
            else:
                cookie = random.choice(available_cookies)
                
            # Update usage history
            self.cookie_usage_history[cookie] = now
            logger.debug(f"Using cookie file: {os.path.basename(cookie)}")
            return cookie

# Singleton instance
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
        self.progress_data.update(progress)
        
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

async def search_youtube(
    query: str, 
    max_results: int = 1,  # Changed to 1 to return top result only
    include_playlists: bool = False,
    language: str = None,
    timeout: int = 15,
    use_cookie: bool = True
) -> List[Dict[str, Any]]:
    """
    Search YouTube for videos matching a query and return the top result with info
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return (default: 1 for top result)
        include_playlists: Whether to include playlists in results
        search_region: Region code to use for search (e.g., 'US', 'GB')
        language: Language preference (e.g., 'en', 'es')
        timeout: Socket timeout in seconds
        use_cookie: Whether to use cookie rotation system
        
    Returns:
        List of video information dictionaries, with top result containing detailed info
    """
    # Get a cookie file if requested
    cookie_file = await cookie_manager.get_cookie_file() if use_cookie else None
    
    # Common user agent to avoid 403 errors
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',  # Changed to get more info while keeping playlist structure
        'default_search': 'ytsearch',
        "geo_bypass": True,
        'noplaylist': not include_playlists,
        'socket_timeout': timeout,
        'ignoreerrors': True,
        'skip_download': True,
        "cache-dir": "/tmp/",
        'writeinfojson': False,
        'playlist_items': f'1-{max_results}',
        'user_agent': user_agent,
    }
    
    if language:
        ydl_opts['extractor_args'] = {'youtube': {'lang': [language]}}
    
    # Add cookie file if available
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file
    
    try:
        def search_fn():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Prefix query with search prefix and limit
                search_query = f"ytsearch{max_results}:{query}"
                return ydl.extract_info(search_query, download=False)
        
        # Run search in thread pool with timeout protection
        try:
            search_results = await asyncio.wait_for(
                download_pool.run_download(search_fn),
                timeout=timeout + 5  # Add 5 seconds buffer to the socket timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Search timed out for query: {query}")
            return []
        
        if not search_results or 'entries' not in search_results:
            logger.warning(f"No results found for query: {query}")
            return []
            
        # Process and return search results
        results = []
        for entry in search_results.get('entries', []):
            if not entry:
                continue
                
            # Handle playlist entries
            if entry.get('_type') == 'playlist' and include_playlists:
                result = {
                    'id': entry.get('id'),
                    'title': entry.get('title', 'Unknown Playlist'),
                    'url': entry.get('url', f"https://www.youtube.com/playlist?list={entry.get('id')}"),
                    'thumbnail': entry.get('thumbnail', None),
                    'type': 'playlist',
                    'entries_count': entry.get('entries_count', 0),
                    'uploader': entry.get('uploader', 'Unknown'),
                }
                results.append(result)
            else:
                # Extract relevant information for videos
                result = {
                    'id': entry.get('id'),
                    'title': entry.get('title', 'Unknown Title'),
                    'url': entry.get('url', f"https://www.youtube.com/watch?v={entry.get('id')}"),
                    'thumbnail': entry.get('thumbnail', None),
                    'duration': entry.get('duration', 0),
                    'duration_string': format_duration(entry.get('duration', 0)),
                    'uploader': entry.get('uploader', 'Unknown'),
                    'uploader_id': entry.get('uploader_id', 'Unknown'),
                    'description': entry.get('description', ''),
                    'view_count': entry.get('view_count', 0),
                    'upload_date': format_upload_date(entry.get('upload_date', '')),
                    'type': 'video',
                    'live_status': entry.get('live_status', None)
                }
                
                # Check for videos that exceed maximum length
                if MAX_VIDEO_LENGTH_MINUTES > 0 and entry.get('duration', 0) > MAX_VIDEO_LENGTH_MINUTES * 60:
                    result['exceeds_max_length'] = True
                
                # If this is the top result, get additional info like fetch_youtube_info would
                if max_results == 1:
                    try:
                        additional_info = await fetch_youtube_info(entry.get('id'))
                        if additional_info:
                            # Merge additional format info
                            result['formats'] = additional_info.get('formats', [])
                            result['all_formats'] = additional_info.get('all_formats', [])
                            result['video_formats'] = additional_info.get('video_formats', [])
                            result['audio_formats'] = additional_info.get('audio_formats', [])
                            result['combined_formats'] = additional_info.get('combined_formats', [])
                    except Exception as e:
                        logger.warning(f"Could not fetch additional info for top result: {str(e)}")
                
                results.append(result)
        
        return results
    except Exception as e:
        logger.error(f"Error searching YouTube: {str(e)}", exc_info=True)
        return []

def format_duration(seconds: int) -> str:
    """Format duration in seconds to a readable string"""
    if not seconds:
        return "Unknown"
        
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours:
        return f"{hours}:{int(minutes):02d}:{int(seconds):02d}"
    else:
        return f"{minutes}:{int(seconds):02d}"

def format_upload_date(date_str: str) -> str:
    """Format upload date from YYYYMMDD to a readable format"""
    if not date_str or len(date_str) != 8:
        return date_str
        
    try:
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{year}-{month}-{day}"
    except:
        return date_str
        
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
    
    # Common user agent to avoid 403 errors
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    
    ydl_opts = {
        'quiet': True,
        'simulate': True,
        'skip_download': True,
        "nocheckcertificate": True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        "cache-dir": "/tmp/",
        'extract_flat': False,  # Changed to get full info
        'ignoreerrors': True,
        'user_agent': user_agent,
    }
    
    # Add cookie file if available
    if cookie_file:
        ydl_opts['cookiefile'] = cookie_file
    
    # Implement retries
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            
            # Run extraction in thread pool
            info = await download_pool.run_download(extract_info)
            
            if not info:
                retry_count += 1
                logger.warning(f"Failed to fetch info for video {video_id} (attempt {retry_count}/{max_retries})")
                if retry_count < max_retries:
                    # Get a different cookie file for the next attempt
                    cookie_file = await cookie_manager.get_cookie_file()
                    ydl_opts['cookiefile'] = cookie_file
                    await asyncio.sleep(1)  # Short delay before retry
                    continue
                return None
            
            # Successfully got info, break out of retry loop
            break
            
        except Exception as e:
            retry_count += 1
            logger.warning(f"Error fetching YouTube info for {video_id} (attempt {retry_count}/{max_retries}): {str(e)}")
            if retry_count < max_retries:
                # Get a different cookie file for the next attempt
                cookie_file = await cookie_manager.get_cookie_file()
                ydl_opts['cookiefile'] = cookie_file
                await asyncio.sleep(1)  # Short delay before retry
                continue
            logger.error(f"All attempts to fetch info for {video_id} failed: {str(e)}")
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
        "cache-dir": "/tmp/",
        'upload_date': format_upload_date(info.get('upload_date', '')),
        'description': info.get('description', ''),
        'formats': formats,
        'all_formats': formats,
        'video_formats': video_formats,
        'audio_formats': audio_formats,
        'combined_formats': combined_formats
    }
    
    return result

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
    
    progress_bar = '▰' * completed_length + '▱' * remaining_length
    
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
    progress_callback: Callable[[Dict[str, Any]], Coroutine],
    bestflac: bool = False, 
    bestVideo: bool = False,
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
    output_template = f'{CATCH_PATH}/%(id)s.%(ext)s'
    
    # Common user agent to avoid 403 errors
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    
    common_opts = {
        "nocheckcertificate": True,
        "addmetadata": True,
        "geo_bypass": True,
        'quiet': True,
        "cache-dir": "/tmp/",
        'no_warnings': True,
        'outtmpl': output_template,
        'socket_timeout': 30,
        'retries': 2,
        'fragment_retries': 5,
        'user_agent': user_agent,
    }
    
    # Start with the common options
    ydl_opts = common_opts.copy()

    if bestflac:
        # Specific options for bestflac
        ydl_opts['format'] = "bestaudio"
        ydl_opts["prefer_ffmpeg"] = False
        ydl_opts["postprocessors"] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'flac', 'preferredquality': '693'}]
    elif bestVideo:
        # Specific options for bestVideo
        ydl_opts['format'] ='bestvideo+bestaudio/best[ext=mp4]/best'
    else:
        # Default case
        ydl_opts['format'] = format_id


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
    
    # Implement retries
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
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
            
            if not info or 'error' in info:
                error_msg = info.get('error', 'Failed to download video') if info else 'Failed to download video'
                retry_count += 1
                logger.warning(f"Download failed for video {video_id} (attempt {retry_count}/{max_retries}): {error_msg}")
                
                if retry_count < max_retries:
                    # Send progress update about retry
                    retry_update = {
                        'status': 'retry',
                        'retry_count': retry_count,
                        'max_retries': max_retries,
                        'error': error_msg
                    }
                    await progress_queue.put(retry_update)
                    
                    # Get a different cookie file for next attempt
                    cookie_file = await cookie_manager.get_cookie_file()
                    ydl_opts['cookiefile'] = cookie_file
                    await asyncio.sleep(2)  # Delay before retry
                    continue
                
                # All retries failed
                stop_event.set()
                await progress_task
                
                return {
                    'success': False,
                    'error': error_msg
                }
            
            # Successfully downloaded, break out of retry loop
            break
            
        except Exception as e:
            retry_count += 1
            logger.warning(f"Error downloading YouTube video {video_id} (attempt {retry_count}/{max_retries}): {str(e)}")
            
            if retry_count < max_retries:
                # Send progress update about retry
                retry_update = {
                    'status': 'retry',
                    'retry_count': retry_count,
                    'max_retries': max_retries,
                    'error': str(e)
                }
                await progress_queue.put(retry_update)
                
                # Get a different cookie file for next attempt
                cookie_file = await cookie_manager.get_cookie_file()
                ydl_opts['cookiefile'] = cookie_file
                await asyncio.sleep(2)  # Delay before retry
                continue
            
            # All retries failed
            stop_event.set()
            try:
                await progress_task
            except:
                pass
            
            return {
                'success': False,
                'error': str(e)
            }
    
    # Stop the progress processing
    stop_event.set()
    await progress_task
    
    file_path = get_final_file_path(info, video_id, bestflac,bestVideo)
    
    ext = file_path.split('.')[-1] if '.' in file_path else ''
    
    
    if os.path.exists(file_path):
        return {
            'success': True,
            'id':info.get('id'),
            'url':info.get('webpage_url'),
            'file_path': file_path,
            'title': info.get('title', 'Unknown Title'),
            'performer': info.get('uploader', 'Unknown Channel'),
            'thumbnail': info.get('thumbnail', ''),
            'ext': ext,
            'filesize': os.path.getsize(file_path),
            'duration': info.get('duration', 0)
        }
    else:
        return {
            'success': False,
            'error': "Download completed but file not found at expected location"
        }

def get_final_file_path(info, video_id: str, bestflac:bool =False,bestVideo: bool = False):
    """
    Robustly determine the final downloaded file path.
    
    Args:
        info: YouTube download info dictionary
        video_id: Video identifier
        bestflac: Whether FLAC conversion was requested
    
    Returns:
        Detected file path
    """
    
    # Check postprocessed files
    if bestflac:
        possible_paths = [
            os.path.join(CATCH_PATH, f"{video_id}.flac"),
            os.path.join(CATCH_PATH, f"{video_id}.m4a"),  # Alternate audio formats
            os.path.join(CATCH_PATH, f"{video_id}.webm")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Found file for FLAC conversion: {path}")
                return path
    elif bestVideo:
        possible_paths = [
            os.path.join(CATCH_PATH, f"{video_id}.mp4"),
            os.path.join(CATCH_PATH, f"{video_id}.webm"),  # Alternate Video formats
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"Found file for FLAC conversion: {path}")
                return path

     # Check requested downloads first
    if 'requested_downloads' in info and info['requested_downloads']:
        file_path = info['requested_downloads'][0]['filepath']
        if os.path.exists(file_path):
            return file_path
    # Fallback filename construction
    ext = 'flac' if bestflac else 'mp4'
    fallback_path = os.path.join(CATCH_PATH, f"{video_id}.{ext}")
    
    return fallback_path,ext


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