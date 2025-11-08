#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

"""
Storage Helper Module
Handles file uploads to a designated storage channel in background threads.
No initialization required - auto-configures from environment/config.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Union

from pyrogram import Client
from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    ChatWriteForbidden,
    FloodWait,
    MediaEmpty,
    PeerIdInvalid,
    RPCError,
    SlowmodeWait,
)
from pyrogram.types import Message

logger = logging.getLogger(__name__)


class BackgroundStorageHelper:
    """
    Helper class to upload files to storage channel in background without blocking.
    """

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
