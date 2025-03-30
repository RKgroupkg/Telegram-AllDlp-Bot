import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
import shutil
from datetime import timedelta
import random
import time
import tempfile
from typing import Dict, Any, Callable, Coroutine, Optional


from src.config import(
    COOKIE_ROTATION_COOLDOWN, # seconds between using the same cookie file
    DEFAULT_COOKIES_DIR,
    YT_PROGRESS_UPDATE_INTERVAL,
)



from src.logging import LOGGER
logger = LOGGER(__name__)

# Cookie rotation management
class CookieManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CookieManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self,cookies_dir: str=DEFAULT_COOKIES_DIR):
        if self._initialized:
            return
            
        self.cookies_dir = cookies_dir
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

    async def refresh_cookies(self):
        """
        Thread-safe method to refresh the list of available cookie files.
        Can be called by multiple modules safely.
        
        Returns:
            int: Number of cookie files found after refresh
        """
        async with self._lock:
            # Refresh the cookies list
            self.refresh_cookies_list()
            
            # Log the refresh operation
            logger.info(f"Cookies refreshed. Total cookie files: {len(self.cookies_files)}")
            
            return len(self.cookies_files)
        
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


download_pool = DownloadPool()

# Singleton instance
cookie_manager = CookieManager()

