import uuid
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Configuration constants
CACHE_EXPIRY_HOURS = 1  # Cache expiry time in hours
VIDEO_CACHE_EXPIRY_HOURS = 2  # Video info cache expiry time in hours
CLEANUP_INTERVAL_SECONDS = 300  # Clean up every 5 minutes

# Cache structures
callback_cache: Dict[str, Dict[str, Any]] = {}
video_info_cache: Dict[str, Dict[str, Any]] = {}
last_cleanup_time = time.time()

def generate_callback_id() -> str:
    """
    Generate a short unique ID for callbacks
    
    Returns:
        A unique ID as string
    """
    # Using uuid4 for better uniqueness while keeping it relatively short
    return str(uuid.uuid4().int % 1000000).zfill(6)

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
    
    callback_id = generate_callback_id()
    callback_cache[callback_id] = {
        'data': data,
        'expires_at': datetime.now() + timedelta(hours=expiry_hours)
    }
    return callback_id

def get_callback_data(callback_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve data from cache if it exists and hasn't expired
    
    Args:
        callback_id: ID of the cached data
        
    Returns:
        Cached data or None if not found or expired
    """
    if callback_id not in callback_cache:
        return None
    
    cache_item = callback_cache[callback_id]
    if datetime.now() > cache_item['expires_at']:
        # Clean up expired item
        del callback_cache[callback_id]
        return None
    
    return cache_item['data']

def add_video_info_to_cache(video_id: str, info: Dict[str, Any]) -> None:
    """
    Add video information to cache
    
    Args:
        video_id: YouTube video ID
        info: Video information
    """
    info['cached_at'] = datetime.now()
    video_info_cache[video_id] = info

def get_video_info_from_cache(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Get video information from cache
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        Video information or None if not in cache or expired
    """
    if video_id not in video_info_cache:
        return None
        
    # Check if cache is still valid
    info = video_info_cache[video_id]
    cached_at = info.get('cached_at', datetime.min)
    if datetime.now() - cached_at > timedelta(hours=VIDEO_CACHE_EXPIRY_HOURS):
        del video_info_cache[video_id]
        return None
        
    return info

def clear_video_info_cache() -> int:
    """
    Clear only the video info cache, leaving the callback cache intact
    
    Returns:
        Number of video info items cleared
    """
    count = len(video_info_cache)
    video_info_cache.clear()
    return count

def clear_callback_cache() -> int:
    """
    Clear the callback cache
    
    Returns:
        Number of callback items cleared
    """
    count = len(callback_cache)
    callback_cache.clear()
    return count

def _check_and_perform_cleanup() -> None:
    """
    Check if cleanup is needed and perform it if necessary
    """
    global last_cleanup_time
    
    current_time = time.time()
    if current_time - last_cleanup_time > CLEANUP_INTERVAL_SECONDS:
        clean_expired_cache()
        last_cleanup_time = current_time

def clean_expired_cache() -> int:
    """
    Remove expired items from all caches
    
    Returns:
        Number of expired items removed
    """
    current_time = datetime.now()
    
    # Clean callback cache
    expired_callback_keys = [
        key for key, item in callback_cache.items()
        if current_time > item['expires_at']
    ]
    
    for key in expired_callback_keys:
        del callback_cache[key]
    
    # Clean video info cache
    video_expiry_time = current_time - timedelta(hours=VIDEO_CACHE_EXPIRY_HOURS)
    video_expired_keys = [
        key for key, info in video_info_cache.items()
        if info.get('cached_at', datetime.min) < video_expiry_time
    ]
    
    for key in video_expired_keys:
        del video_info_cache[key]
    
    return len(expired_callback_keys) + len(video_expired_keys)