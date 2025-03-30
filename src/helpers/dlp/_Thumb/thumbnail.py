# Copyright (c) 2025 Rkgroup.
# Quick Dl is an open-source Downloader bot licensed under MIT.
# All rights reserved where applicable.

import os
import uuid
import aiohttp
import asyncio
from typing import Optional, Tuple, Dict

from src.logging import LOGGER

logger = LOGGER(__name__)


class ThumbnailManager:
    def __init__(self, cache_dir: str = "/tmp", cache_size: int = 100):
        """
        Initialize the thumbnail manager.

        Args:
            cache_dir: Directory to store thumbnails
            cache_size: Maximum number of thumbnails to cache in memory
        """
        self.cache_dir = cache_dir
        self._ensure_cache_dir()
        self.thumbnails: Dict[str, str] = {}  # url -> filepath mapping

    def _ensure_cache_dir(self):
        """Ensure cache directory exists"""
        os.makedirs(self.cache_dir, exist_ok=True)

    async def get_thumbnail(
        self, thumbnail_url: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Downloads a thumbnail, caches it, and returns the filepath.
        Uses LRU cache to avoid redundant downloads.

        Args:
            thumbnail_url: URL to download the thumbnail

        Returns:
            Tuple of (success status, file path if successful or None if failed)
        """
        if not thumbnail_url:
            return False, None

        # Check if we already have this thumbnail
        if thumbnail_url in self.thumbnails:
            filepath = self.thumbnails[thumbnail_url]
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.debug(f"Using cached thumbnail: {filepath}")
                return True, filepath

        # Download new thumbnail
        success, filepath = await self._download_thumbnail(thumbnail_url)
        if success:
            self.thumbnails[thumbnail_url] = filepath
        return success, filepath

    async def _download_thumbnail(
        self, thumbnail_url: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Downloads a thumbnail from the provided URL with error handling and verification.

        Args:
            thumbnail_url: URL to download the thumbnail from

        Returns:
            Tuple of (success status, file path if successful or None if failed)
        """
        thumbnail_filename = os.path.join(self.cache_dir, f"{uuid.uuid4()}.jpg")

        try:
            # Use aiohttp with timeout and retries
            retry_count = 3
            for attempt in range(retry_count):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            thumbnail_url, timeout=10, raise_for_status=True
                        ) as response:
                            content = await response.read()

                            # Validate content
                            if not content or len(content) < 100:
                                logger.warning(
                                    f"Downloaded thumbnail too small: {len(content)} bytes"
                                )
                                await asyncio.sleep(1)  # Wait before retry
                                continue

                            # Write to file
                            with open(thumbnail_filename, "wb") as f:
                                f.write(content)

                            # Verify file
                            if (
                                os.path.exists(thumbnail_filename)
                                and os.path.getsize(thumbnail_filename) > 0
                            ):
                                logger.info(
                                    f"Successfully downloaded thumbnail to {thumbnail_filename}"
                                )
                                return True, thumbnail_filename

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(
                        f"Attempt {attempt+1}/{retry_count} failed: {str(e)}"
                    )
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff

            # All attempts failed
            logger.error(f"Failed to download thumbnail after {retry_count} attempts")
            return False, None

        except Exception as e:
            logger.error(
                f"Unexpected error during thumbnail download: {str(e)}", exc_info=True
            )
            self._safe_delete(thumbnail_filename)  # Clean up partial file
            return False, None

    def delete_thumbnail(self, thumbnail_path: Optional[str]) -> bool:
        """
        Safely delete a thumbnail file and remove from cache.

        Args:
            thumbnail_path: Path to the thumbnail file

        Returns:
            True if deletion was successful, False otherwise
        """
        if not thumbnail_path:
            return False

        # Remove from cache dict
        for url, path in list(self.thumbnails.items()):
            if path == thumbnail_path:
                del self.thumbnails[url]

        return self._safe_delete(thumbnail_path)

    def _safe_delete(self, file_path: str) -> bool:
        """
        Safely delete a file with error handling.

        Args:
            file_path: Path to the file to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Deleted thumbnail: {file_path}")
                return True
        except (IOError, PermissionError) as e:
            logger.error(f"Failed to delete thumbnail {file_path}: {str(e)}")
        return False

    def clear_all_thumbnails(self) -> int:
        """
        Delete all cached thumbnails.

        Returns:
            Number of thumbnails successfully deleted
        """
        deleted_count = 0
        for path in list(self.thumbnails.values()):
            if self._safe_delete(path):
                deleted_count += 1

        self.thumbnails.clear()
        return deleted_count


# Create a singleton instance
thumbnail_manager = ThumbnailManager()


# Simple wrapper function for backward compatibility
async def download_and_verify_thumbnail(
    thumbnail_url: Optional[str],
) -> Tuple[bool, Optional[str]]:
    """
    Downloads a thumbnail from the provided URL and verifies its existence.

    Args:
        thumbnail_url: URL to download the thumbnail from. Can be None.

    Returns:
        Tuple of (success status, file path if successful or None if failed)
    """
    return await thumbnail_manager.get_thumbnail(thumbnail_url)


# Helper function to easily delete thumbnails
def delete_thumbnail(thumbnail_path: Optional[str]) -> bool:
    """
    Delete a thumbnail file.

    Args:
        thumbnail_path: Path to the thumbnail file

    Returns:
        True if deletion was successful, False otherwise
    """
    return thumbnail_manager.delete_thumbnail(thumbnail_path)
