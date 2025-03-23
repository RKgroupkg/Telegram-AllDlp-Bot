# TelegramBot/helpers/dlp/yt_dl/ytdl_core.py

import os
import time
import asyncio
import yt_dlp
from datetime import timedelta
from typing import Dict, Any, Callable, Coroutine, Optional, List

# Configuration constants
MAX_VIDEO_LENGTH_MINUTES = 15
DOWNLOAD_PATH = "./tmp"
PROGRESS_UPDATE_INTERVAL = 5  # seconds

# Ensure download directory exists
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

async def fetch_youtube_info(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch information about a YouTube video
    
    Args:
        video_id: The YouTube video ID
        
    Returns:
        Dictionary containing video information or None if an error occurred
    """
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
            
            # Save relevant info
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
            
            return result
    except Exception as e:
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
    ydl_opts = {
        'format': format_id,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'outtmpl': f'{DOWNLOAD_PATH}/%(id)s.%(ext)s',
        'cookiefile': 'cookies.txt',  # Add your cookies file here if needed
        'progress_hooks': [lambda d: asyncio.create_task(progress_callback(d))],
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
        return {
            'success': False,
            'error': str(e)
        }

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
    if filter_type == "all":
        return info['all_formats']
    elif filter_type == "video":
        return info['combined_formats'] + info['video_formats']
    elif filter_type == "audio":
        return info['audio_formats']
    else:
        return info['all_formats']

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
            return True
        return False
    except:
        return False