#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.

import os
import re
import asyncio
from typing import Any, Dict, Optional, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

import spotipy
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from spotipy.oauth2 import SpotifyClientCredentials

from src import bot
from src.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, CATCH_PATH
from src.logging import LOGGER
from src.helpers.dlp._rex import (SPOTIFY_ALBUM_REGEX, SPOTIFY_PLAYLIST_REGEX,
                                  SPOTIFY_TRACK_REGEX)
from src.helpers.dlp.yt_dl.catch import (add_video_info_to_cache,
                                         clean_expired_cache)
from src.helpers.dlp.yt_dl.dataclass import SearchInfo
from src.helpers.dlp.yt_dl.utils import create_format_selection_markup
from src.helpers.dlp.yt_dl.ytdl_core import fetch_youtube_info, search_youtube
from src.helpers.filters import is_download_rate_limited
from src.helpers.dlp.api_dlp.deezerDL import DeezerDownloader
from src.helpers.dlp.api_dlp.tidalDL import TidalDownloader

logger = LOGGER(__name__)

# ==================== CONSTANTS ====================

class DownloadSource(Enum):
    """Enumeration of available download sources"""
    AUTO = "auto"
    TIDAL = "tidal"
    DEEZER = "deezer"
    YOUTUBE = "youtube"


class AudioFormat(Enum):
    """Audio file formats"""
    FLAC = ".flac"
    MP3 = ".mp3"
    M4A = ".m4a"


# UI Constants
class Emoji:
    """Consistent emoji set for UI"""
    MUSIC = "♪"           # Musical note
    SPARKLES = "✦"        # Sparkle
    DOWNLOAD = "↓"        # Down arrow
    CHECK = "✓"           # Check mark
    ERROR = "✗"           # X mark
    WARNING = "⚠"         # Warning
    INFO = "ⓘ"            # Info circle
    LOADING = "⌛"        # Hourglass
    SEARCH = "⌕"          # Search
    ALBUM = "◉"           # Disc
    ARTIST = "♬"          # Music notes
    CLOCK = "⏲"           # Timer
    STAR = "★"            # Star
    QUALITY = "◆"         # Diamond
    FILE = "▤"            # File
    CANCEL = "⊗"          # Cancel


# Download timeouts and retries
DOWNLOAD_TIMEOUT = 30
MAX_RETRIES = 2
CACHE_EXPIRY_MINUTES = 10
THUMBNAIL_SIZE = (320, 320)
MAX_FILENAME_LENGTH = 200

# File extensions
AUDIO_EXTENSIONS = (AudioFormat.FLAC.value, AudioFormat.MP3.value, AudioFormat.M4A.value)

# ==================== DATA CLASSES ====================

@dataclass
class TrackMetadata:
    """Structured track metadata"""
    title: str
    artist: str
    album: str
    release_date: str
    duration_ms: int
    duration_formatted: str
    spotify_url: str
    album_art: Optional[str]
    popularity: int
    isrc: Optional[str]
    cached_at: datetime
    track_id: str
    
    @property
    def has_high_quality_sources(self) -> bool:
        """Check if track has ISRC for high-quality downloads"""
        return bool(self.isrc)
    
    @property
    def quality_indicator(self) -> str:
        """Get quality indicator string"""
        return f"{Emoji.QUALITY} High-Quality Sources Available" if self.has_high_quality_sources else f"{Emoji.INFO} YouTube Only"


# ==================== INITIALIZATION ====================

# Initialize Spotify client
spotify_client = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID, 
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        spotify_client = spotipy.Spotify(auth_manager=auth_manager)
        logger.info("✓ Spotify client initialized successfully")
    except Exception as e:
        logger.error(f"✗ Failed to initialize Spotify client: {e}")
else:
    logger.warning("⚠ Spotify credentials not configured")

# Track cache with expiration
track_cache: Dict[str, TrackMetadata] = {}


# ==================== UTILITY FUNCTIONS ====================

def extract_spotify_id(text: str, pattern: str) -> Optional[str]:
    """Extract Spotify ID from URL using regex pattern"""
    match = re.search(pattern, text)
    return match.group(1) if match else None


def format_duration(ms: int) -> str:
    """Format milliseconds to MM:SS"""
    total_seconds = int(ms / 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def format_file_size(bytes: int) -> str:
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} TB"


def sanitize_filename(filename: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    """
    Sanitize filename for cross-platform compatibility
    
    Args:
        filename: Original filename
        max_length: Maximum allowed length
        
    Returns:
        Safe filename string
    """
    if not filename:
        return "Unknown"
    
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', str(filename))
    # Normalize whitespace
    sanitized = re.sub(r'\s+', ' ', sanitized).strip('. ')
    # Truncate if needed
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip('. ')
    
    return sanitized or "Unknown"


def normalize_text(text: str) -> str:
    """Normalize text for fuzzy matching"""
    normalized = re.sub(r'[^\w\s]', '', text.lower())
    return re.sub(r'\s+', ' ', normalized).strip()


def calculate_match_score(filename: str, title: str, artist: str) -> float:
    """
    Calculate fuzzy match score for file detection
    
    Returns:
        Match score (0-100)
    """
    norm_filename = normalize_text(filename)
    norm_title = normalize_text(title)
    norm_artist = normalize_text(artist)
    
    score = 0.0
    
    # Exact substring matches
    if norm_title in norm_filename:
        score += 50.0
    if norm_artist in norm_filename:
        score += 50.0
    
    # Word overlap scoring
    title_words = set(norm_title.split())
    artist_words = set(norm_artist.split())
    file_words = set(norm_filename.split())
    
    if title_words:
        title_overlap = len(title_words & file_words) / len(title_words)
        score += title_overlap * 30.0
    
    if artist_words:
        artist_overlap = len(artist_words & file_words) / len(artist_words)
        score += artist_overlap * 20.0
    
    return score


def find_downloaded_file(
    output_dir: str, 
    title: str, 
    artist: str,
    extensions: Tuple[str, ...] = AUDIO_EXTENSIONS
) -> Optional[str]:
    """
    Intelligently locate downloaded file with fuzzy matching
    
    Args:
        output_dir: Directory to search
        title: Expected track title
        artist: Expected artist name
        extensions: Valid file extensions
        
    Returns:
        Full path to file or None
    """
    if not os.path.exists(output_dir):
        logger.warning(f"Directory does not exist: {output_dir}")
        return None
    
    audio_files = [
        f for f in os.listdir(output_dir) 
        if f.lower().endswith(extensions)
    ]
    
    if not audio_files:
        logger.warning(f"No audio files found in {output_dir}")
        return None
    
    logger.debug(f"Searching for: '{title}' by '{artist}' among {len(audio_files)} files")
    
    # Strategy 1: Exact sanitized match
    safe_patterns = [
        f"{sanitize_filename(artist)} - {sanitize_filename(title)}",
        f"{sanitize_filename(title)} - {sanitize_filename(artist)}",
        f"{sanitize_filename(artist)}_{sanitize_filename(title)}",
    ]
    
    for pattern in safe_patterns:
        for ext in extensions:
            filename = f"{pattern}{ext}"
            if filename in audio_files:
                path = os.path.join(output_dir, filename)
                logger.info(f"{Emoji.CHECK} Found exact match: {filename}")
                return path
    
    # Strategy 2: Fuzzy matching with score threshold
    best_match = None
    best_score = 0.0
    
    for filename in audio_files:
        score = calculate_match_score(
            os.path.splitext(filename)[0], 
            title, 
            artist
        )
        
        logger.debug(f"  '{filename}' → score: {score:.1f}")
        
        if score > best_score:
            best_score = score
            best_match = filename
    
    # Accept if score meets threshold
    if best_match and best_score >= 60.0:
        path = os.path.join(output_dir, best_match)
        logger.info(f"{Emoji.CHECK} Found fuzzy match: {best_match} (score: {best_score:.1f})")
        return path
    
    # Strategy 3: Most recent file fallback
    if audio_files:
        most_recent = max(
            audio_files, 
            key=lambda f: os.path.getmtime(os.path.join(output_dir, f))
        )
        path = os.path.join(output_dir, most_recent)
        logger.warning(f"{Emoji.WARNING} Using most recent file: {most_recent}")
        return path
    
    logger.error(f"{Emoji.ERROR} No suitable file found")
    return None


async def download_thumbnail(url: str, output_path: str) -> Optional[str]:
    """
    Download and save thumbnail image
    
    Args:
        url: Image URL
        output_path: Destination path
        
    Returns:
        File path if successful
    """
    if not url:
        return None
    
    try:
        import requests
        response = await asyncio.to_thread(
            requests.get, url, timeout=10
        )
        
        if response.status_code == 200:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)
            logger.debug(f"Thumbnail saved: {output_path}")
            return output_path
        
        logger.warning(f"Failed to download thumbnail: HTTP {response.status_code}")
        return None
        
    except Exception as e:
        logger.warning(f"Thumbnail download error: {e}")
        return None


def cleanup_files(*file_paths: str) -> None:
    """Safely remove multiple files"""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.warning(f"Cleanup failed for {file_path}: {e}")


# ==================== SPOTIFY API ====================

async def get_spotify_track_info(track_id: str) -> Optional[TrackMetadata]:
    """
    Fetch comprehensive track information from Spotify
    
    Args:
        track_id: Spotify track ID
        
    Returns:
        TrackMetadata object or None
    """
    if not spotify_client:
        logger.error("Spotify client not initialized")
        return None

    try:
        track = await asyncio.to_thread(spotify_client.track, track_id)
        
        metadata = TrackMetadata(
            title=track["name"],
            artist=", ".join([artist["name"] for artist in track["artists"]]),
            album=track["album"]["name"],
            release_date=track["album"].get("release_date", "Unknown"),
            duration_ms=track["duration_ms"],
            duration_formatted=format_duration(track["duration_ms"]),
            spotify_url=track["external_urls"]["spotify"],
            album_art=track["album"]["images"][0]["url"] if track["album"]["images"] else None,
            popularity=track.get("popularity", 0),
            isrc=track.get("external_ids", {}).get("isrc"),
            cached_at=datetime.now(),
            track_id=track_id
        )
        
        logger.info(f"{Emoji.MUSIC} Fetched: {metadata.title} - {metadata.artist}")
        return metadata
        
    except Exception as e:
        logger.error(f"Error fetching Spotify track: {e}", exc_info=True)
        return None


# ==================== UI MARKUP CREATION ====================

def create_source_selection_markup(track_id: str, has_isrc: bool) -> InlineKeyboardMarkup:
    """
    Create inline keyboard for source selection
    
    Args:
        track_id: Spotify track ID
        has_isrc: Whether high-quality sources are available
        
    Returns:
        InlineKeyboardMarkup with download options
    """
    buttons = []
    
    if has_isrc:
        buttons.append([
            InlineKeyboardButton(
                f"{Emoji.SPARKLES} Auto (Best Quality)", 
                callback_data=f"spotify_dl:auto:{track_id}"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                f"{Emoji.QUALITY} Tidal FLAC", 
                callback_data=f"spotify_dl:tidal:{track_id}"
            ),
            InlineKeyboardButton(
                f"{Emoji.MUSIC} Deezer FLAC", 
                callback_data=f"spotify_dl:deezer:{track_id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            f"▶️ YouTube", 
            callback_data=f"spotify_dl:youtube:{track_id}"
        )
    ])
    
    return InlineKeyboardMarkup(buttons)


def format_track_info_message(metadata: TrackMetadata, include_source_hint: bool = True) -> str:
    """
    Format track information for display
    
    Args:
        metadata: Track metadata
        include_source_hint: Whether to include source selection hint
        
    Returns:
        Formatted message text
    """
    message = (
        f"<b>{metadata.title}</b>\n\n"
        f"{Emoji.ARTIST} <b>Artist:</b> <i>{metadata.artist}</i>\n"
        f"{Emoji.ALBUM} <b>Album:</b> <i>{metadata.album}</i>\n"
        f"📅 <b>Released:</b> <i>{metadata.release_date}</i>\n"
        f"{Emoji.CLOCK} <b>Duration:</b> <i>{metadata.duration_formatted}</i>\n"
        f"{Emoji.STAR} <b>Popularity:</b> <i>{metadata.popularity}/100</i>\n"
    )
    
    if include_source_hint:
        message += f"\n<b>{metadata.quality_indicator}</b>\n"
        message += f"<i>{Emoji.INFO} Choose your download source:</i>"
    
    return message


# ==================== DOWNLOAD HANDLERS ====================

async def try_tidal_download(metadata: TrackMetadata, output_dir: str) -> Optional[str]:
    """
    Attempt download from Tidal
    
    Returns:
        File path if successful
    """
    if not metadata.isrc:
        logger.warning("No ISRC available for Tidal")
        return None
    
    try:
        logger.info(f"[Tidal] Attempting ISRC: {metadata.isrc}")
        
        downloader = TidalDownloader(timeout=DOWNLOAD_TIMEOUT, max_retries=MAX_RETRIES)
        
        query = f"{sanitize_filename(metadata.title)} {sanitize_filename(metadata.artist)}"
        
        file_path = await asyncio.to_thread(
            downloader.download,
            query=query,
            isrc=metadata.isrc,
            output_dir=output_dir,
            quality="LOSSLESS",
            auto_fallback=True
        )
        
        if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            size = format_file_size(os.path.getsize(file_path))
            logger.info(f"[Tidal] {Emoji.CHECK} Success: {size}")
            return file_path
        
        logger.warning("[Tidal] Download failed or file empty")
        return None
        
    except Exception as e:
        logger.error(f"[Tidal] {Emoji.ERROR} Error: {e}", exc_info=True)
        return None


async def try_deezer_download(metadata: TrackMetadata, output_dir: str) -> Optional[str]:
    """
    Attempt download from Deezer
    
    Returns:
        File path if successful
    """
    if not metadata.isrc:
        logger.warning("No ISRC available for Deezer")
        return None
    
    try:
        logger.info(f"[Deezer] Attempting ISRC: {metadata.isrc}")
        
        # Capture files before download
        files_before = set(os.listdir(output_dir)) if os.path.exists(output_dir) else set()
        
        downloader = DeezerDownloader()
        success = await downloader.download_by_isrc(
            isrc=metadata.isrc,
            output_dir=output_dir
        )
        
        if not success:
            logger.warning("[Deezer] Download returned False")
            return None
        
        # Check for new files
        files_after = set(os.listdir(output_dir)) if os.path.exists(output_dir) else set()
        new_files = files_after - files_before
        
        # Prefer newly created files
        if new_files:
            for new_file in new_files:
                if new_file.lower().endswith(AUDIO_EXTENSIONS):
                    file_path = os.path.join(output_dir, new_file)
                    if os.path.getsize(file_path) > 0:
                        size = format_file_size(os.path.getsize(file_path))
                        logger.info(f"[Deezer] {Emoji.CHECK} Success: {size}")
                        return file_path
        
        # Fallback to intelligent file finder
        file_path = find_downloaded_file(
            output_dir, 
            metadata.title, 
            metadata.artist
        )
        
        if file_path and os.path.getsize(file_path) > 0:
            size = format_file_size(os.path.getsize(file_path))
            logger.info(f"[Deezer] {Emoji.CHECK} Found: {size}")
            return file_path
        
        logger.warning("[Deezer] No valid file found")
        return None
        
    except Exception as e:
        logger.error(f"[Deezer] {Emoji.ERROR} Error: {e}", exc_info=True)
        return None


async def find_youtube_match(metadata: TrackMetadata) -> Optional[SearchInfo]:
    """Find matching YouTube video"""
    search_query = f"{metadata.title} {metadata.artist} official audio"
    
    logger.info(f"[YouTube] {Emoji.SEARCH} Searching: {search_query}")
    
    try:
        results = await search_youtube(search_query, max_results=5)
        
        if not results:
            logger.warning("[YouTube] No results found")
            return None
        
        video_info = await fetch_youtube_info(results[0].id)
        
        if video_info:
            logger.info(f"[YouTube] {Emoji.CHECK} Found: {video_info.title}")
        
        return video_info
        
    except Exception as e:
        logger.error(f"[YouTube] Search error: {e}")
        return None


async def download_and_upload_audio(
    message: Message,
    metadata: TrackMetadata,
    source: str,
    status_msg: Message,
    selection_msg: Message = None
) -> bool:
    """
    Main download and upload orchestrator
    
    Args:
        message: Original message
        metadata: Track metadata
        source: Download source
        status_msg: Status message to update
        selection_msg: Source selection message to delete after completion
        
    Returns:
        True if successful
    """
    output_dir = CATCH_PATH
    os.makedirs(output_dir, exist_ok=True)
    
    file_path = None
    thumb_path = None
    source_name = None
    
    try:
        # Auto mode: Try all sources in priority order
        if source == DownloadSource.AUTO.value:
            logger.info(f"[Auto] {Emoji.SPARKLES} Trying all sources")
            
            # Try Tidal (best quality)
            if metadata.isrc:
                await status_msg.edit_text(
                    f"{Emoji.LOADING} <b>{metadata.title}</b>\n"
                    f"<i>→ Trying Tidal (Best Quality)...</i>"
                )
                file_path = await try_tidal_download(metadata, output_dir)
                if file_path:
                    source_name = "Tidal HiFi FLAC"
            
            # Try Deezer if Tidal failed
            if not file_path and metadata.isrc:
                await status_msg.edit_text(
                    f"{Emoji.LOADING} <b>{metadata.title}</b>\n"
                    f"<i>→ Trying Deezer...</i>"
                )
                file_path = await try_deezer_download(metadata, output_dir)
                if file_path:
                    source_name = "Deezer FLAC"
            
            # Fallback to YouTube
            if not file_path:
                await status_msg.edit_text(
                    f"{Emoji.LOADING} <b>{metadata.title}</b>\n"
                    f"<i>→ Trying YouTube...</i>"
                )
                source = DownloadSource.YOUTUBE.value
        
        elif source == DownloadSource.TIDAL.value:
            await status_msg.edit_text(
                f"{Emoji.LOADING} <b>{metadata.title}</b>\n"
                f"<i>→ Downloading from Tidal HiFi...</i>"
            )
            file_path = await try_tidal_download(metadata, output_dir)
            if file_path:
                source_name = "Tidal HiFi FLAC"
        
        elif source == DownloadSource.DEEZER.value:
            await status_msg.edit_text(
                f"{Emoji.LOADING} <b>{metadata.title}</b>\n"
                f"<i>→ Downloading from Deezer...</i>"
            )
            file_path = await try_deezer_download(metadata, output_dir)
            if file_path:
                source_name = "Deezer FLAC"
        
        # Handle YouTube or auto-mode fallback
        if source == DownloadSource.YOUTUBE.value or (
            source == DownloadSource.AUTO.value and not file_path
        ):
            await status_msg.edit_text(
                f"{Emoji.SEARCH} <b>{metadata.title}</b>\n"
                f"<i>→ Searching YouTube...</i>"
            )
            
            clean_expired_cache()
            youtube_info = await find_youtube_match(metadata)
            
            if not youtube_info:
                await status_msg.edit_text(
                    f"{Emoji.ERROR} <b>{metadata.title}</b>\n"
                    f"<i>No YouTube matches found</i>"
                )
                return False
            
            # Add to cache and show format selection
            add_video_info_to_cache(youtube_info.id, youtube_info)
            
            formats = youtube_info.all_formats
            if not formats:
                await status_msg.edit_text(
                    f"{Emoji.ERROR} <b>{metadata.title}</b>\n"
                    f"<i>No downloadable formats available</i>"
                )
                return False
            
            format_markup = create_format_selection_markup(formats)
            info_text = format_track_info_message(metadata, include_source_hint=False)
            info_text += f"\n▶️ <b>Source:</b> <i>YouTube</i>\n\n"
            info_text += f"<i>{Emoji.INFO} Select format to download:</i>"
            
            if metadata.album_art:
                await status_msg.delete()
                await message.reply_photo(
                    photo=metadata.album_art,
                    caption=info_text,
                    reply_markup=format_markup,
                    quote=True
                )
            else:
                await status_msg.edit_text(info_text, reply_markup=format_markup)
            
            logger.info(f"[YouTube] Format selection presented")
            return True
        
        # Upload FLAC file if downloaded from Tidal/Deezer
        if file_path and source_name:
            file_size = os.path.getsize(file_path)
            file_size_str = format_file_size(file_size)
            
            await status_msg.edit_text(
                f"{Emoji.DOWNLOAD} <b>{metadata.title}</b>\n\n"
                f"{Emoji.ARTIST} <i>{metadata.artist}</i>\n"
                f"{Emoji.QUALITY} <i>{source_name}</i>\n"
                f"{Emoji.FILE} <i>{file_size_str}</i>\n\n"
                f"<i>→ Uploading to Telegram...</i>"
            )
            
            # Download thumbnail for audio
            if metadata.album_art:
                thumb_filename = f"{sanitize_filename(metadata.title)}_thumb.jpg"
                thumb_path = os.path.join(output_dir, thumb_filename)
                thumb_path = await download_thumbnail(metadata.album_art, thumb_path)
            
            # Upload with metadata
            caption = (
                f"<b>{metadata.title}</b>\n"
                f"{Emoji.ARTIST} <i>{metadata.artist}</i>\n"
                f"{Emoji.ALBUM} <i>{metadata.album}</i>\n"
                f"{Emoji.CLOCK} <i>{metadata.duration_formatted}</i>\n"
                f"{Emoji.QUALITY} <i>{source_name}</i>"
            )
            
            await message.reply_audio(
                audio=file_path,
                caption=caption,
                title=metadata.title,
                performer=metadata.artist,
                duration=int(metadata.duration_ms / 1000),
                thumb=thumb_path,
                quote=True
            )
            
            await status_msg.delete()
            
            # Delete the source selection message
            if selection_msg:
                try:
                    await selection_msg.delete()
                except Exception as e:
                    logger.debug(f"Could not delete selection message: {e}")
            
            logger.info(f"{Emoji.CHECK} Upload complete: {metadata.title}")
            return True
        else:
            await status_msg.edit_text(
                f"{Emoji.ERROR} <b>{metadata.title}</b>\n"
                f"<i>Download failed from {source.title()}</i>"
            )
            
            # Delete the source selection message after failure too
            if selection_msg:
                try:
                    await selection_msg.delete()
                except Exception as e:
                    logger.debug(f"Could not delete selection message: {e}")
            
            logger.error(f"Download failed for {metadata.title} from {source}")
            return False
    
    except Exception as e:
        logger.error(f"Error in download_and_upload: {e}", exc_info=True)
        await status_msg.edit_text(
            f"{Emoji.ERROR} <b>Error occurred</b>\n"
            f"<i>{str(e)[:200]}</i>"
        )
        
        # Delete selection message even on error
        if selection_msg:
            try:
                await selection_msg.delete()
            except Exception:
                pass
        
        return False
    
    finally:
        # Always cleanup temporary files
        cleanup_files(file_path, thumb_path)


# ==================== MESSAGE HANDLERS ====================

@bot.on_message(
    filters.regex(SPOTIFY_TRACK_REGEX)
    | filters.command(["spt", "spotify", "sptdlp", "dlmusic"])
    & is_download_rate_limited
)
async def spotify_track_handler(_, message: Message):
    """Handle Spotify track links and present source selection"""
    
    if not spotify_client:
        await message.reply_text(
            f"{Emoji.WARNING} <b>Spotify Not Configured</b>\n\n"
            f"<i>Please contact administrator to enable Spotify integration.</i>",
            quote=True
        )
        return
    
    track_id = extract_spotify_id(message.text, SPOTIFY_TRACK_REGEX)
    if not track_id:
        logger.warning("Invalid Spotify track URL")
        return
    
    status_msg = await message.reply_text(
        f"{Emoji.LOADING} <b>Processing Spotify Track</b>\n\n"
        f"<i>→ Fetching track information...</i>", 
        quote=True
    )
    
    try:
        # Fetch track metadata
        metadata = await get_spotify_track_info(track_id)
        if not metadata:
            await status_msg.edit_text(
                f"{Emoji.ERROR} <b>Failed to fetch track information</b>\n\n"
                f"<i>Please try again or use a different link.</i>"
            )
            return
        
        # Cache metadata
        track_cache[track_id] = metadata
        logger.debug(f"Cached track: {track_id}")
        
        # Create source selection UI
        source_markup = create_source_selection_markup(
            track_id, 
            metadata.has_high_quality_sources
        )
        
        info_text = format_track_info_message(metadata, include_source_hint=True)
        
        # Display with album art if available
        if metadata.album_art:
            await status_msg.delete()
            await message.reply_photo(
                photo=metadata.album_art,
                caption=info_text,
                reply_markup=source_markup,
                quote=True
            )
        else:
            await status_msg.edit_text(info_text, reply_markup=source_markup)
        
        logger.info(f"{Emoji.CHECK} Source selection presented for: {metadata.title}")
    
    except Exception as e:
        await status_msg.edit_text(
            f"{Emoji.ERROR} <b>An error occurred</b>\n\n"
            f"<i>{str(e)[:200]}</i>"
        )
        logger.error(f"Track handler error: {e}", exc_info=True)


@bot.on_callback_query(filters.regex(r"^spotify_dl:"))
async def spotify_download_callback(_, callback_query: CallbackQuery):
    """Handle download source selection callbacks"""
    
    try:
        # Parse callback data
        _, source, track_id = callback_query.data.split(":", 2)
        
        logger.info(f"User selected: {source} for track: {track_id}")
        
        # Retrieve cached metadata
        metadata = track_cache.get(track_id)
        if not metadata:
            await callback_query.answer(
                f"{Emoji.WARNING} Session expired. Please send the link again.",
                show_alert=True
            )
            logger.warning(f"Cache miss for track: {track_id}")
            return
        
        # Acknowledge selection
        source_labels = {
            "auto": f"{Emoji.SPARKLES} Auto",
            "tidal": f"{Emoji.QUALITY} Tidal",
            "deezer": f"{Emoji.MUSIC} Deezer",
            "youtube": "▶️ YouTube"
        }
        await callback_query.answer(
            f"{source_labels.get(source, '')} Starting download..."
        )
        
        # Create progress message
        status_msg = await callback_query.message.reply_text(
            f"{Emoji.LOADING} <b>{metadata.title}</b>\n\n"
            f"<i>→ Initializing download from {source.upper()}...</i>",
            quote=True
        )
        
        # Start download process
        success = await download_and_upload_audio(
            callback_query.message,
            metadata,
            source,
            status_msg,
            callback_query.message  # Pass the selection message to delete it
        )
        
        # Cleanup cache after completion
        if success or source != DownloadSource.YOUTUBE.value:
            track_cache.pop(track_id, None)
            logger.info(f"{Emoji.CHECK} Completed: {metadata.title}")
    
    except Exception as e:
        await callback_query.answer(
            f"{Emoji.ERROR} Error: {str(e)[:180]}",
            show_alert=True
        )
        logger.error(f"Callback error: {e}", exc_info=True)


@bot.on_message(filters.regex(SPOTIFY_ALBUM_REGEX) & is_download_rate_limited)
async def spotify_album_handler(_, message: Message):
    """Handle Spotify album links (info only)"""
    
    if not spotify_client:
        await message.reply_text(
            f"{Emoji.WARNING} Spotify integration not configured.",
            quote=True
        )
        return
    
    album_id = extract_spotify_id(message.text, SPOTIFY_ALBUM_REGEX)
    if not album_id:
        return
    
    try:
        album = await asyncio.to_thread(spotify_client.album, album_id)
        
        info_text = (
            f"{Emoji.ALBUM} <b>{album['name']}</b>\n\n"
            f"{Emoji.ARTIST} <b>Artist:</b> <i>{album['artists'][0]['name']}</i>\n"
            f"📅 <b>Released:</b> <i>{album.get('release_date', 'Unknown')}</i>\n"
            f"{Emoji.MUSIC} <b>Tracks:</b> <i>{album.get('total_tracks', 0)}</i>\n\n"
            f"{Emoji.INFO} <i>Individual track downloads only.\nPlease send specific track links.</i>"
        )
        
        album_art = album["images"][0]["url"] if album["images"] else None
        if album_art:
            await message.reply_photo(photo=album_art, caption=info_text, quote=True)
        else:
            await message.reply_text(info_text, quote=True)
        
        logger.info(f"Album info: {album['name']}")
    
    except Exception as e:
        await message.reply_text(
            f"{Emoji.ERROR} Error: {str(e)}",
            quote=True
        )
        logger.error(f"Album handler error: {e}", exc_info=True)


@bot.on_message(filters.regex(SPOTIFY_PLAYLIST_REGEX) & is_download_rate_limited)
async def spotify_playlist_handler(_, message: Message):
    """Handle Spotify playlist links (info only)"""
    
    if not spotify_client:
        await message.reply_text(
            f"{Emoji.WARNING} Spotify integration not configured.",
            quote=True
        )
        return
    
    playlist_id = extract_spotify_id(message.text, SPOTIFY_PLAYLIST_REGEX)
    if not playlist_id:
        return
    
    try:
        playlist = await asyncio.to_thread(spotify_client.playlist, playlist_id)
        
        info_text = (
            f"📋 <b>{playlist['name']}</b>\n\n"
            f"👤 <b>By:</b> <i>{playlist['owner']['display_name']}</i>\n"
            f"{Emoji.MUSIC} <b>Tracks:</b> <i>{playlist['tracks']['total']}</i>\n\n"
            f"{Emoji.INFO} <i>Individual track downloads only.\nPlease send specific track links.</i>"
        )
        
        playlist_art = playlist["images"][0]["url"] if playlist["images"] else None
        if playlist_art:
            await message.reply_photo(photo=playlist_art, caption=info_text, quote=True)
        else:
            await message.reply_text(info_text, quote=True)
        
        logger.info(f"Playlist info: {playlist['name']}")
    
    except Exception as e:
        await message.reply_text(
            f"{Emoji.ERROR} Error: {str(e)}",
            quote=True
        )
        logger.error(f"Playlist handler error: {e}", exc_info=True)


# ==================== BACKGROUND TASKS ====================

async def cleanup_expired_track_cache():
    """Periodically clean expired cache entries"""
    
    while True:
        try:
            await asyncio.sleep(600)  # Run every 10 minutes
            
            current_time = datetime.now()
            expired = [
                track_id for track_id, metadata in track_cache.items()
                if (current_time - metadata.cached_at) > timedelta(minutes=CACHE_EXPIRY_MINUTES)
            ]
            
            for track_id in expired:
                track_cache.pop(track_id, None)
            
            if expired:
                logger.info(f"{Emoji.INFO} Cleaned {len(expired)} expired cache entries")
        
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")


# Start background cache cleanup
asyncio.create_task(cleanup_expired_track_cache())