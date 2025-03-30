import os
import asyncio
import logging
import time
import json
import yt_dlp
from typing import Optional, Dict, Any, Callable, Coroutine, List, Tuple, Union
from functools import partial

# Import your existing cookie manager
from src.helpers.dlp._yt_dlp import (
    download_pool,
    cookie_manager,
)

# Configure logging
logger = logging.getLogger('instagram_downloader')

class InstagramDownloader:
    """
    Production-level Instagram video downloader that uses yt-dlp, cookie rotation,
    and FFmpeg for optimal quality.
    """
    
    def __init__(self, 
                 output_dir: str = './tmp',
                 max_retries: int = 3,
                 retry_delay: int = 5,
                 progress_interval: float = 0.5,
                 ffmpeg_location: Optional[str] = None):
        """
        Initialize the Instagram downloader with configuration options.
        
        Args:
            output_dir: Directory to save downloaded videos
            max_retries: Maximum number of download retry attempts
            retry_delay: Delay in seconds between retry attempts
            progress_interval: How often to update progress (in seconds)
            ffmpeg_location: Path to FFmpeg binary (if not in PATH)
        """
        self.output_dir = output_dir
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.progress_interval = progress_interval
        self.ffmpeg_location = ffmpeg_location
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

    async def download_video(self, 
                            url: str, 
                            output_template: str = '%(uploader)s/%(title)s.%(ext)s',
                            callback: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
                            quality: str = 'best',
                            format_preference: str = 'mp4') -> Dict[str, Any]:
        """
        Download an Instagram video with optimal settings.
        
        Args:
            url: The Instagram URL to download
            output_template: yt-dlp output template
            callback: Async callback function for progress updates
            quality: Video quality to download ('best', 'worst', or resolution like '720p')
            format_preference: Preferred video format ('mp4', 'webm', etc.)
            
        Returns:
            Dict containing download results with keys:
                - success: Boolean indicating success
                - filepath: Path to downloaded file (if successful)
                - error: Error message (if failed)
                - info: Video metadata (if available)
        """
        # Create a download tracker if callback is provided
        tracker = DownloadTracker(callback, self.progress_interval) if callback else None
        
        # Get a cookie file from the cookie manager
        cookie_file = await cookie_manager.get_cookie_file()
        if not cookie_file:
            logger.warning("No cookie file available for Instagram download")
        
        # Configure yt-dlp options with optimal settings
        ydl_opts = await self._get_ytdlp_options(
            output_template=output_template,
            cookie_file=cookie_file,
            tracker=tracker,
            quality=quality,
            format_preference=format_preference
        )
        
        # Initialize result
        result = {
            'success': False,
            'filepath': None,
            'error': None,
            'info': None
        }
        
        # Attempt download with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                # Update callback about retry attempt if available
                if tracker:
                    await tracker.update({
                        'status': 'downloading',
                        'attempt': attempt,
                        'max_attempts': self.max_retries
                    })
                
                # Run the download in the thread pool to avoid blocking
                info_dict = await download_pool.run_download(
                    self._run_ytdlp_download,
                    url=url,
                    ydl_opts=ydl_opts
                )
                
                # Handle successful download
                if info_dict:
                    filepath = self._get_filepath_from_info(info_dict)
                    result['success'] = True
                    result['filepath'] = filepath
                    result['info'] = info_dict
                    
                    # Final callback update
                    if tracker:
                        await tracker.update({
                            'status': 'finished',
                            'filepath': filepath,
                            'info': info_dict
                        })
                    
                    logger.info(f"Successfully downloaded Instagram video: {filepath}")
                    return result
                    
            except Exception as e:
                error_msg = f"Download attempt {attempt}/{self.max_retries} failed: {str(e)}"
                logger.error(error_msg)
                result['error'] = error_msg
                
                # Update callback about error if available
                if tracker:
                    await tracker.update({
                        'status': 'error',
                        'error': str(e),
                        'attempt': attempt,
                        'max_attempts': self.max_retries
                    })
                
                # If we have more retries, wait before next attempt
                if attempt < self.max_retries:
                    # Try to get a different cookie file for the next attempt
                    cookie_file = await cookie_manager.get_cookie_file()
                    if cookie_file:
                        ydl_opts['cookiefile'] = cookie_file
                    
                    # Wait before retrying
                    await asyncio.sleep(self.retry_delay)
                    
                    # Refresh cookies if we've failed multiple times
                    if attempt >= self.max_retries // 2:
                        await cookie_manager.refresh_cookies()
        
        # If we get here, all attempts failed
        logger.error(f"Failed to download Instagram video after {self.max_retries} attempts: {url}")
        return result

    async def _get_ytdlp_options(self, 
                               output_template: str, 
                               cookie_file: Optional[str], 
                               tracker: Optional['DownloadTracker'],
                               quality: str,
                               format_preference: str) -> Dict[str, Any]:
        """
        Configure optimal yt-dlp options for Instagram downloads.
        
        Args:
            output_template: yt-dlp output template
            cookie_file: Path to cookie file
            tracker: Download tracker for progress updates
            quality: Video quality preference
            format_preference: Video format preference
            
        Returns:
            Dict of yt-dlp options
        """
        # Build the full output path
        output_path = os.path.join(self.output_dir, output_template)
        
        # Configure format selection based on quality preference
        if quality == 'best':
            format_selection = f'bestvideo[ext={format_preference}]+bestaudio/best[ext={format_preference}]/best'
        elif quality == 'worst':
            format_selection = f'worstvideo[ext={format_preference}]+worstaudio/worst[ext={format_preference}]/worst'
        elif quality.endswith('p'):  # Resolution like '720p'
            resolution = quality[:-1]  # Remove the 'p'
            format_selection = f'bestvideo[height<={resolution}][ext={format_preference}]+bestaudio/best[height<={resolution}][ext={format_preference}]/best'
        else:
            # Default to best quality
            format_selection = f'bestvideo[ext={format_preference}]+bestaudio/best[ext={format_preference}]/best'
        
        # Define progress hook if tracker is provided
        progress_hooks = [self._create_progress_hook(tracker)] if tracker else []
        
        # Build complete options
        ydl_opts = {
            'format': format_selection,
            'outtmpl': output_path,
            'restrictfilenames': True,  # Avoid special characters in filenames
            'noplaylist': True,  # Only download single video, not playlist
            'quiet': True,  # Reduce console output
            'no_warnings': True,  # Suppress warnings
            'ignoreerrors': False,  # Don't ignore errors
            'nocheckcertificate': True,  # Ignore SSL cert verification
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
            },
            'socket_timeout': 30,  # Timeout for connections
            'retries': 5,  # Internal retries for the extractor
            'progress_hooks': progress_hooks,
            'merge_output_format': format_preference,  # Merge audio/video into this format
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': format_preference,
            }, {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }]
        }
        
        # Add FFmpeg location if specified
        if self.ffmpeg_location:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_location
        
        # Add cookie file if provided
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        
        return ydl_opts

    def _create_progress_hook(self, tracker: 'DownloadTracker') -> Callable:
        """
        Create a progress hook function for yt-dlp.
        
        Args:
            tracker: Download tracker for progress updates
            
        Returns:
            Progress hook function
        """
        loop = asyncio.get_event_loop()
        
        def progress_hook(d):
            """Progress hook that triggers the tracker's update method"""
            asyncio.run_coroutine_threadsafe(tracker.update(d), loop)
        
        return progress_hook

    def _run_ytdlp_download(self, url: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the actual yt-dlp download (runs in thread pool).
        
        Args:
            url: URL to download
            ydl_opts: yt-dlp options
            
        Returns:
            Dict containing download info
        """
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info first to validate URL
            info_dict = ydl.extract_info(url, download=False)
            
            # If this is a playlist (shouldn't happen with Instagram but just in case)
            if 'entries' in info_dict:
                # Just download the first video
                info_dict = info_dict['entries'][0]
            
            # Now download the validated URL
            info_dict = ydl.extract_info(url, download=True)
            return info_dict

    def _get_filepath_from_info(self, info_dict: Dict[str, Any]) -> str:
        """
        Extract the downloaded filepath from yt-dlp info dict.
        
        Args:
            info_dict: yt-dlp download info
            
        Returns:
            Path to downloaded file
        """
        if 'requested_downloads' in info_dict:
            # For yt-dlp newer versions
            return info_dict['requested_downloads'][0]['filepath']
        else:
            # Fallback for older versions
            return info_dict.get('filepath', info_dict.get('filename', ''))

    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """
        Extract information about an Instagram video without downloading.
        
        Args:
            url: Instagram URL
            
        Returns:
            Dict containing video metadata
        """
        # Get a cookie file
        cookie_file = await cookie_manager.get_cookie_file()
        
        # Configure minimal options
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': True,
        }
        
        # Add cookie file if available
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        
        try:
            # Run the info extraction in the thread pool
            info_dict = await download_pool.run_download(
                self._extract_info,
                url=url,
                ydl_opts=ydl_opts
            )
            
            return {
                'success': True,
                'info': info_dict
            }
        except Exception as e:
            logger.error(f"Failed to extract Instagram video info: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def _extract_info(self, url: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract info using yt-dlp (runs in thread pool).
        
        Args:
            url: URL to extract info from
            ydl_opts: yt-dlp options
            
        Returns:
            Dict containing video metadata
        """
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

# Use your existing download tracker class or define here if needed
class DownloadTracker:
    """Class to track download progress and manage callbacks"""
    def __init__(self, callback: Callable[[Dict[str, Any]], Coroutine], interval: float = 0.5):
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
            formatted_progress = self._format_progress(
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

    def _format_progress(self, downloaded_bytes: int, total_bytes: int, start_time: float) -> Dict[str, Any]:
        """Format download progress data for user-friendly display"""
        now = time.time()
        elapsed = now - start_time
        
        # Calculate percentage
        if total_bytes > 0:
            percent = downloaded_bytes * 100 / total_bytes
        else:
            percent = 0
        
        # Calculate speed
        if elapsed > 0:
            speed = downloaded_bytes / elapsed
        else:
            speed = 0
        
        # Calculate ETA
        if speed > 0 and total_bytes > downloaded_bytes:
            eta = (total_bytes - downloaded_bytes) / speed
        else:
            eta = 0
        
        # Format results
        return {
            'percent': round(percent, 1),
            'speed': self._format_bytes(speed),
            'speed_bytes': speed,
            'eta': self._format_time(eta),
            'eta_seconds': eta,
            'downloaded': self._format_bytes(downloaded_bytes),
            'downloaded_bytes': downloaded_bytes,
            'total': self._format_bytes(total_bytes),
            'total_bytes': total_bytes,
            'elapsed': self._format_time(elapsed),
            'elapsed_seconds': elapsed
        }
    
    def _format_bytes(self, bytes_num: float) -> str:
        """Format bytes into a readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_num < 1024:
                return f"{bytes_num:.1f} {unit}"
            bytes_num /= 1024
        return f"{bytes_num:.1f} PB"
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds into a readable time string"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{int(minutes)}m {int(seconds)}s"
        hours, minutes = divmod(minutes, 60)
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

# Helper function for using the downloader
async def download_instagram_video(
    url: str,
    output_dir: str = './tmp',
    output_template: str = '%(uploader)s/%(title)s.%(ext)s',
    callback: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
    quality: str = 'best',
    format_preference: str = 'mp4',
    ffmpeg_location: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: int = 5
) -> Dict[str, Any]:
    """
    Simple helper function to download an Instagram video without creating an instance.
    
    Args:
        url: Instagram URL to download
        output_dir: Directory to save downloads
        output_template: yt-dlp output template
        callback: Async callback function for progress updates
        quality: Video quality ('best', 'worst', or resolution like '720p')
        format_preference: Preferred video format ('mp4', 'webm', etc.)
        ffmpeg_location: Path to FFmpeg binary
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        Dict with download results
    """
    downloader = InstagramDownloader(
        output_dir=output_dir,
        max_retries=max_retries,
        retry_delay=retry_delay,
        ffmpeg_location=ffmpeg_location
    )
    
    return await downloader.download_video(
        url=url,
        output_template=output_template,
        callback=callback,
        quality=quality,
        format_preference=format_preference
    )