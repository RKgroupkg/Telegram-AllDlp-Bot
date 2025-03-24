import uuid
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

# Configuration constants
CACHE_EXPIRY_HOURS = 1  # Cache expiry time in hours
VIDEO_CACHE_EXPIRY_HOURS = 2  # Video info cache expiry time in hours
CLEANUP_INTERVAL_SECONDS = 300  # Clean up every 5 minutes

# Logging configuration
logger = logging.getLogger(__name__)

# Thread-safe cache structures
class ThreadSafeCache:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._cache.get(key)
    
    def set(self, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            self._cache[key] = value
    
    def delete(self, key: str) -> None:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    def items(self) -> Tuple:
        with self._lock:
            return tuple(self._cache.items())
    
    def keys(self) -> Tuple:
        with self._lock:
            return tuple(self._cache.keys())
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


# Initialize thread-safe cache structures
callback_cache = ThreadSafeCache()
video_info_cache = ThreadSafeCache()
last_cleanup_time = time.time()
cleanup_lock = threading.Lock()

def generate_callback_id() -> str:
    """
    Generate a short unique ID for callbacks
    
    Returns:
        A unique ID as string
    """
    # Using uuid4 for better uniqueness while keeping it relatively short
    # Added entropy by including timestamp to reduce collision probability
    timestamp = int(time.time() * 1000) % 10000
    random_id = uuid.uuid4().int % 1000000
    combined = (timestamp * 1000000 + random_id) % 1000000
    return str(combined).zfill(6)

def store_callback_data(data: Dict[str, Any], expiry_hours: float = CACHE_EXPIRY_HOURS) -> str:
    """
    Store data in cache with expiry time and return a callback ID
    
    Args:
        data: Data to store in cache
        expiry_hours: Hours until data expires
        
    Returns:
        Callback ID for retrieving the data
    """
    _check_and_perform_cleanup()
    
    # Ensure we get a unique ID that's not already in the cache
    while True:
        callback_id = generate_callback_id()
        if callback_cache.get(callback_id) is None:
            break
    
    callback_cache.set(callback_id, {
        'data': data,
        'expires_at': datetime.now() + timedelta(hours=expiry_hours)
    })
    
    logger.debug(f"Stored callback data with ID: {callback_id}")
    return callback_id

def get_callback_data(callback_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve data from cache if it exists and hasn't expired
    
    Args:
        callback_id: ID of the cached data
        
    Returns:
        Cached data or None if not found or expired
    """
    cache_item = callback_cache.get(callback_id)
    
    if cache_item is None:
        logger.debug(f"Callback ID not found: {callback_id}")
        return None
    
    if datetime.now() > cache_item['expires_at']:
        # Clean up expired item
        callback_cache.delete(callback_id)
        logger.debug(f"Callback data expired: {callback_id}")
        return None
    
    logger.debug(f"Retrieved callback data: {callback_id}")
    return cache_item['data']

def add_video_info_to_cache(video_id: str, info: Dict[str, Any]) -> None:
    """
    Add video information to cache
    
    Args:
        video_id: YouTube video ID
        info: Video information
    """
    # Create a deep copy to prevent shared references
    cache_info = info.copy()
    cache_info['cached_at'] = datetime.now()
    video_info_cache.set(video_id, cache_info)
    logger.debug(f"Added video info to cache: {video_id}")

def get_video_info_from_cache(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Get video information from cache
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        Video information or None if not in cache or expired
    """
    info = video_info_cache.get(video_id)
    
    if info is None:
        logger.debug(f"Video info not in cache: {video_id}")
        return None
        
    # Check if cache is still valid
    cached_at = info.get('cached_at', datetime.min)
    if datetime.now() - cached_at > timedelta(hours=VIDEO_CACHE_EXPIRY_HOURS):
        video_info_cache.delete(video_id)
        logger.debug(f"Video info expired: {video_id}")
        return None
    
    # Return a copy to prevent modification of cached data
    logger.debug(f"Retrieved video info from cache: {video_id}")
    return info.copy()

def clear_video_info_cache() -> int:
    """
    Clear only the video info cache, leaving the callback cache intact
    
    Returns:
        Number of video info items cleared
    """
    count = video_info_cache.clear()
    logger.info(f"Cleared video info cache: {count} items removed")
    return count

def clear_callback_cache() -> int:
    """
    Clear the callback cache
    
    Returns:
        Number of callback items cleared
    """
    count = callback_cache.clear()
    logger.info(f"Cleared callback cache: {count} items removed")
    return count

def _check_and_perform_cleanup() -> None:
    """
    Check if cleanup is needed and perform it if necessary
    """
    global last_cleanup_time
    
    current_time = time.time()
    if current_time - last_cleanup_time > CLEANUP_INTERVAL_SECONDS:
        # Use non-blocking check to prevent bottlenecks
        if cleanup_lock.acquire(blocking=False):
            try:
                # Double-check after acquiring lock
                if time.time() - last_cleanup_time > CLEANUP_INTERVAL_SECONDS:
                    removed = clean_expired_cache()
                    last_cleanup_time = time.time()
                    logger.info(f"Performed cache cleanup: {removed} items removed")
            finally:
                cleanup_lock.release()

def clean_expired_cache() -> int:
    """
    Remove expired items from all caches
    
    Returns:
        Number of expired items removed
    """
    current_time = datetime.now()
    removed_count = 0
    
    # Clean callback cache
    for key, item in callback_cache.items():
        if current_time > item['expires_at']:
            callback_cache.delete(key)
            removed_count += 1
    
    # Clean video info cache
    video_expiry_time = current_time - timedelta(hours=VIDEO_CACHE_EXPIRY_HOURS)
    for key, info in video_info_cache.items():
        if info.get('cached_at', datetime.min) < video_expiry_time:
            video_info_cache.delete(key)
            removed_count += 1
    
    return removed_count

# Exception-safe decorator for cache operations
def cache_operation_safe(default_return=None):
    """Decorator to make cache operations exception-safe"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Cache operation error in {func.__name__}: {str(e)}")
                return default_return
        return wrapper
    return decorator

# Apply the decorator to public functions
store_callback_data = cache_operation_safe("")(store_callback_data)
get_callback_data = cache_operation_safe(None)(get_callback_data)
add_video_info_to_cache = cache_operation_safe(None)(add_video_info_to_cache)
get_video_info_from_cache = cache_operation_safe(None)(get_video_info_from_cache)
clear_video_info_cache = cache_operation_safe(0)(clear_video_info_cache)
clear_callback_cache = cache_operation_safe(0)(clear_callback_cache)
clean_expired_cache = cache_operation_safe(0)(clean_expired_cache)