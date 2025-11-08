#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.

"""
Spotify Storage Forwarder Module
Forwards uploaded Spotify tracks to storage channel and returns file_id for reuse.
Integrates seamlessly with existing spotify_dl.py module.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError

from src.config import STORAGE_CHANNEL_ID
from src.logging import LOGGER

logger = LOGGER(__name__)


class SpotifyStorageForwarder:
    """
    Handles forwarding of Spotify downloads to storage channel.
    Maintains a cache of file_ids for quick redelivery.
    """
    
    def __init__(self, bot: Client, storage_channel_id: int):
        self.bot = bot
        self.storage_channel_id = storage_channel_id
        self.file_id_cache: Dict[str, str] = {}  # track_id -> file_id mapping
        self._forwarding_tasks = set()
        
    async def forward_and_cache(
        self,
        uploaded_message: Message,
        track_id: str,
        track_title: str,
        artist: str,
        source: str
    ) -> Optional[str]:
        """
        Forward uploaded track to storage channel and cache file_id.
        
        Args:
            uploaded_message: The message with uploaded audio
            track_id: Spotify track ID
            track_title: Track title
            artist: Artist name
            source: Download source (Tidal/Deezer/YouTube)
            
        Returns:
            file_id string if successful, None if failed
        """
        try:
            # Check if already cached
            if track_id in self.file_id_cache:
                logger.info(f"♻️ Using cached file_id for: {track_title}")
                return self.file_id_cache[track_id]
            
            # Get the audio file from the message
            if not uploaded_message.audio:
                logger.warning(f"⚠️ No audio in message for {track_title}")
                return None
            
            file_id = uploaded_message.audio.file_id
            
            # Create storage caption with metadata
            storage_caption = (
                f"🎵 {track_title}\n"
                f"👤 {artist}\n"
                f"📦 Source: {source}\n"
                f"🆔 Track ID: {track_id}\n"
                f"📅 Stored: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            
            # Forward to storage channel with retry logic
            max_retries = 3
            storage_message = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        f"📤 Forwarding to storage: {track_title} "
                        f"(Attempt {attempt}/{max_retries})"
                    )
                    
                    storage_message = await self.bot.send_audio(
                        chat_id=self.storage_channel_id,
                        audio=file_id,
                        caption=storage_caption,
                        title=track_title,
                        performer=artist,
                        duration=uploaded_message.audio.duration,
                        thumb=uploaded_message.audio.thumbs[0].file_id 
                              if uploaded_message.audio.thumbs else None
                    )
                    
                    logger.info(
                        f"✅ Forwarded to storage: {track_title} "
                        f"(Message ID: {storage_message.id})"
                    )
                    break
                    
                except FloodWait as e:
                    if attempt == max_retries:
                        logger.error(f"❌ FloodWait exceeded retries: {e.value}s")
                        return None
                    logger.warning(f"⏳ FloodWait: {e.value}s, waiting...")
                    await asyncio.sleep(e.value)
                    
                except RPCError as e:
                    logger.error(f"❌ RPC error forwarding {track_title}: {e}")
                    if attempt == max_retries:
                        return None
                    await asyncio.sleep(2 ** attempt)
                    
                except Exception as e:
                    logger.exception(f"❌ Unexpected error forwarding {track_title}: {e}")
                    if attempt == max_retries:
                        return None
                    await asyncio.sleep(2 ** attempt)
            
            if storage_message and storage_message.audio:
                # Cache the file_id for future use
                cached_file_id = storage_message.audio.file_id
                self.file_id_cache[track_id] = cached_file_id
                logger.info(f"💾 Cached file_id for {track_id}")
                return cached_file_id
            
            return None
            
        except Exception as e:
            logger.exception(f"❌ Critical error in forward_and_cache: {e}")
            return None
    
    def forward_in_background(
        self,
        uploaded_message: Message,
        track_id: str,
        track_title: str,
        artist: str,
        source: str,
        callback=None
    ) -> asyncio.Task:
        """
        Forward to storage in background without blocking.
        
        Args:
            uploaded_message: The message with uploaded audio
            track_id: Spotify track ID
            track_title: Track title
            artist: Artist name
            source: Download source
            callback: Optional async callback(file_id: str or None)
            
        Returns:
            asyncio.Task object
        """
        async def _task():
            result = await self.forward_and_cache(
                uploaded_message, track_id, track_title, artist, source
            )
            if callback:
                try:
                    await callback(result)
                except Exception as e:
                    logger.exception(f"❌ Error in forward callback: {e}")
            return result
        
        task = asyncio.create_task(_task())
        self._forwarding_tasks.add(task)
        task.add_done_callback(self._forwarding_tasks.discard)
        
        return task
    
    async def get_cached_file_id(self, track_id: str) -> Optional[str]:
        """
        Retrieve cached file_id for a track.
        
        Args:
            track_id: Spotify track ID
            
        Returns:
            file_id string if cached, None otherwise
        """
        return self.file_id_cache.get(track_id)
    
    async def cleanup(self):
        """Wait for all forwarding tasks to complete."""
        if self._forwarding_tasks:
            logger.info(f"⏳ Waiting for {len(self._forwarding_tasks)} forwarding tasks...")
            await asyncio.gather(*self._forwarding_tasks, return_exceptions=True)
            logger.info("✅ All forwarding tasks completed")


# Global instance (lazy initialization)
_forwarder_instance: Optional[SpotifyStorageForwarder] = None


def get_forwarder() -> Optional[SpotifyStorageForwarder]:
    """
    Get or create forwarder instance. Auto-configures from src.
    
    Returns:
        SpotifyStorageForwarder instance or None if not configured
    """
    global _forwarder_instance
    
    if _forwarder_instance is None:
        try:
            from src import bot
            
            if not STORAGE_CHANNEL_ID:
                logger.info("📦 STORAGE_CHANNEL_ID not configured - forwarding disabled")
                return None
            
            _forwarder_instance = SpotifyStorageForwarder(bot, STORAGE_CHANNEL_ID)
            logger.info(f"✅ Initialized Spotify forwarder for channel: {STORAGE_CHANNEL_ID}")
            
        except (ImportError, AttributeError) as e:
            logger.warning(f"⚠️ Forwarder not available: {e}")
            return None
    
    return _forwarder_instance


# Public API Functions

async def forward_spotify_track(
    uploaded_message: Message,
    track_id: str,
    track_title: str,
    artist: str,
    source: str
) -> Optional[str]:
    """
    Forward uploaded Spotify track to storage and get file_id.
    Blocks until forwarding completes.
    
    Args:
        uploaded_message: The message with uploaded audio
        track_id: Spotify track ID
        track_title: Track title
        artist: Artist name
        source: Download source (Tidal/Deezer/YouTube)
        
    Returns:
        file_id string if successful, None if failed
        
    Example:
        file_id = await forward_spotify_track(
            message, "3n3Ppam7vgaVa1iaRUc9Lp",
            "Song Title", "Artist Name", "Tidal HiFi FLAC"
        )
    """
    forwarder = get_forwarder()
    if not forwarder:
        logger.debug("📦 Forwarder not configured - skipping forward")
        return None
    
    return await forwarder.forward_and_cache(
        uploaded_message, track_id, track_title, artist, source
    )


def forward_spotify_track_background(
    uploaded_message: Message,
    track_id: str,
    track_title: str,
    artist: str,
    source: str,
    callback=None
) -> None:
    """
    Forward track to storage in background (fire-and-forget).
    
    Args:
        uploaded_message: The message with uploaded audio
        track_id: Spotify track ID
        track_title: Track title
        artist: Artist name
        source: Download source
        callback: Optional async callback(file_id: str or None)
        
    Example:
        forward_spotify_track_background(
            message, track_id, "Song", "Artist", "Tidal"
        )
        # Code continues immediately
    """
    forwarder = get_forwarder()
    if not forwarder:
        logger.debug("📦 Forwarder not configured - skipping forward")
        return
    
    forwarder.forward_in_background(
        uploaded_message, track_id, track_title, artist, source, callback
    )


async def get_stored_file_id(track_id: str) -> Optional[str]:
    """
    Retrieve cached file_id for a previously stored track.
    
    Args:
        track_id: Spotify track ID
        
    Returns:
        file_id string if cached, None otherwise
        
    Example:
        file_id = await get_stored_file_id("3n3Ppam7vgaVa1iaRUc9Lp")
        if file_id:
            # Send without re-downloading
            await bot.send_audio(chat_id, file_id)
    """
    forwarder = get_forwarder()
    if not forwarder:
        return None
    
    return await forwarder.get_cached_file_id(track_id)


async def send_from_storage_or_download(
    message: Message,
    track_id: str,
    download_callback
) -> bool:
    """
    Smart function: sends from storage if available, otherwise triggers download.
    
    Args:
        message: User's message
        track_id: Spotify track ID
        download_callback: Async function to call if not in storage
        
    Returns:
        True if sent from storage, False if download needed
        
    Example:
        sent = await send_from_storage_or_download(
            message, track_id,
            lambda: download_and_upload_audio(...)
        )
    """
    file_id = await get_stored_file_id(track_id)
    
    if file_id:
        try:
            logger.info(f"♻️ Sending from storage: {track_id}")
            await message.reply_audio(audio=file_id, quote=True)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to send from storage, re-downloading: {e}")
    
    # Not in storage or send failed, trigger download
    await download_callback()
    return False


async def wait_for_all_forwards():
    """
    Wait for all background forwarding tasks to complete.
    Call before bot shutdown.
    """
    if _forwarder_instance:
        await _forwarder_instance.cleanup()    """

    def __init__(
        self,
        bot: Client,
        storage_channel_id: int,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        self.bot = bot
        self.storage_channel_id = storage_channel_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._tasks = set()

    async def _upload_task(
        self,
        file_path: Union[str, Path],
        caption: Optional[str] = None,
        file_type: str = "document",
        callback=None,
    ) -> Optional[Message]:
        """
        Internal upload task that runs in background.

        Args:
            file_path: Path to the file to upload
            caption: Optional caption for the file
            file_type: Type of file ('document', 'photo', 'video', 'audio')
            callback: Optional callback function(result: Message or None)

        Returns:
            Message object if successful, None if failed
        """
        result = None
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                if callback:
                    await callback(None)
                return None

            if not file_path.is_file():
                logger.error(f"Path is not a file: {file_path}")
                if callback:
                    await callback(None)
                return None

            for attempt in range(1, self.max_retries + 1):
                try:
                    logger.info(
                        f"Background upload: {file_path.name} "
                        f"(Attempt {attempt}/{self.max_retries})"
                    )

                    # Select appropriate send method based on file type
                    send_method = {
                        "document": self.bot.send_document,
                        "photo": self.bot.send_photo,
                        "video": self.bot.send_video,
                        "audio": self.bot.send_audio,
                    }.get(file_type, self.bot.send_document)

                    message = await send_method(
                        chat_id=self.storage_channel_id,
                        **{file_type: str(file_path)},
                        caption=caption,
                    )

                    logger.info(
                        f"Successfully uploaded {file_path.name} to storage. "
                        f"Message ID: {message.id}"
                    )
                    result = message
                    break

                except FloodWait as e:
                    logger.warning(f"FloodWait: {e.value}s. Waiting...")
                    await asyncio.sleep(e.value)
                    continue

                except SlowmodeWait as e:
                    logger.warning(f"SlowmodeWait: {e.value}s. Waiting...")
                    await asyncio.sleep(e.value)
                    continue

                except (ChannelInvalid, ChannelPrivate, PeerIdInvalid) as e:
                    logger.error(f"Invalid channel: {e}")
                    break

                except ChatWriteForbidden as e:
                    logger.error(f"No write permission: {e}")
                    break

                except MediaEmpty as e:
                    logger.error(f"Media empty/corrupted: {e}")
                    break

                except RPCError as e:
                    logger.error(f"RPC error (Attempt {attempt}): {e}")
                    if attempt < self.max_retries:
                        delay = self.retry_delay * (2 ** (attempt - 1))
                        await asyncio.sleep(delay)
                        continue
                    break

                except Exception as e:
                    logger.exception(f"Unexpected error (Attempt {attempt}): {e}")
                    if attempt < self.max_retries:
                        delay = self.retry_delay * (2 ** (attempt - 1))
                        await asyncio.sleep(delay)
                        continue
                    break

            if result is None:
                logger.error(
                    f"Failed to upload {file_path.name} after {self.max_retries} attempts"
                )

        except Exception as e:
            logger.exception(f"Critical error in upload task: {e}")
        finally:
            # Execute callback if provided
            if callback:
                try:
                    await callback(result)
                except Exception as e:
                    logger.exception(f"Error in upload callback: {e}")

        return result

    def upload_in_background(
        self,
        file_path: Union[str, Path],
        caption: Optional[str] = None,
        file_type: str = "document",
        callback=None,
    ) -> asyncio.Task:
        """
        Upload file in background without blocking. Fire and forget.

        Args:
            file_path: Path to the file to upload
            caption: Optional caption for the file
            file_type: Type of file ('document', 'photo', 'video', 'audio')
            callback: Optional async callback function(result: Message or None)

        Returns:
            asyncio.Task object (can be ignored)
        """
        task = asyncio.create_task(
            self._upload_task(file_path, caption, file_type, callback)
        )

        # Keep reference to prevent garbage collection
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return task

    async def upload_and_get_file_id(
        self,
        file_path: Union[str, Path],
        caption: Optional[str] = None,
        file_type: str = "document",
    ) -> Optional[str]:
        """
        Upload file and return the file_id. Waits for upload to complete.

        Args:
            file_path: Path to the file to upload
            caption: Optional caption
            file_type: Type of file

        Returns:
            file_id string if successful, None if failed
        """
        result = await self._upload_task(file_path, caption, file_type)
        if result:
            # Get file_id based on file type
            if result.document:
                return result.document.file_id
            elif result.photo:
                return result.photo.file_id
            elif result.video:
                return result.video.file_id
            elif result.audio:
                return result.audio.file_id
        return None

    async def cleanup(self):
        """Wait for all background tasks to complete."""
        if self._tasks:
            logger.info(f"Waiting for {len(self._tasks)} upload tasks to complete...")
            await asyncio.gather(*self._tasks, return_exceptions=True)
            logger.info("All upload tasks completed")


# Lazy initialization - no setup required
_storage_instance: Optional[BackgroundStorageHelper] = None


def _get_storage() -> Optional[BackgroundStorageHelper]:
    """
    Get or create storage instance. Auto-configures from src.
    No manual initialization needed. Returns None if config missing.
    """
    global _storage_instance

    if _storage_instance is None:
        try:
            # Import here to avoid circular imports
            from src import bot
            from src.config import STORAGE_CHANNEL_ID  # Add this to your config

            if not STORAGE_CHANNEL_ID:
                logger.info("STORAGE_CHANNEL_ID not configured - storage disabled")
                return None

            _storage_instance = BackgroundStorageHelper(bot, STORAGE_CHANNEL_ID)
            logger.info(f"Auto-initialized storage for channel: {STORAGE_CHANNEL_ID}")
        except (ImportError, AttributeError) as e:
            logger.warning(f"Storage not available: {e}")
            return None

    return _storage_instance


# Public API - Simple fire-and-forget functions


def backup_file(
    file_path: Union[str, Path],
    caption: Optional[str] = None,
    file_type: str = "document",
    callback=None,
) -> None:
    """
    Upload file to storage channel in background. Non-blocking, fire-and-forget.

    Args:
        file_path: Path to the file to upload
        caption: Optional caption
        file_type: Type ('document', 'photo', 'video', 'audio')
        callback: Optional async callback(result: Message or None)

    Example:
        backup_file("downloads/song.mp3", "Backup of song", "audio")
        # Code continues immediately without waiting
    """
    try:
        storage = _get_storage()
        if storage is None:
            logger.debug(f"Storage not configured - skipping backup of {file_path}")
            return
        
        storage.upload_in_background(file_path, caption, file_type, callback)
        logger.debug(f"Queued background upload: {file_path}")
    except Exception as e:
        logger.error(f"Failed to queue upload: {e}")


async def backup_and_get_file_id(
    file_path: Union[str, Path],
    caption: Optional[str] = None,
    file_type: str = "document",
) -> Optional[str]:
    """
    Upload file and return file_id. Waits for upload to complete.

    Args:
        file_path: Path to the file to upload
        caption: Optional caption
        file_type: Type of file

    Returns:
        file_id string if successful, None if failed

    Example:
        file_id = await backup_and_get_file_id("song.mp3", "Backup", "audio")
        if file_id:
            # Use file_id to send to user without re-uploading
            await bot.send_audio(chat_id, file_id)
    """
    try:
        storage = _get_storage()
        if storage is None:
            logger.debug(f"Storage not configured - cannot get file_id for {file_path}")
            return None
        
        return await storage.upload_and_get_file_id(file_path, caption, file_type)
    except Exception as e:
        logger.error(f"Failed to upload and get file_id: {e}")
        return None


def backup_photo(
    photo_path: Union[str, Path], caption: Optional[str] = None, callback=None
) -> None:
    """Convenience function to backup photos."""
    backup_file(photo_path, caption, "photo", callback)


def backup_audio(
    audio_path: Union[str, Path], caption: Optional[str] = None, callback=None
) -> None:
    """Convenience function to backup audio files."""
    backup_file(audio_path, caption, "audio", callback)


def backup_video(
    video_path: Union[str, Path], caption: Optional[str] = None, callback=None
) -> None:
    """Convenience function to backup videos."""
    backup_file(video_path, caption, "video", callback)


async def wait_for_all_uploads():
    """
    Wait for all background uploads to complete.
    Call this before shutting down the bot.
    """
    if _storage_instance:
        await _storage_instance.cleanup()
