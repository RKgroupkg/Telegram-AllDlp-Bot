#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

import asyncio
import os
import uuid
from urllib.parse import urlparse
import base64
import aiofiles
import aiohttp

from src.logging import LOGGER

logger = LOGGER(__name__)


async def fetch_content(session: aiohttp.ClientSession, url: str) -> str | None:
    paste_id = url.strip("/").split("/")[-1]
    raw_url = f"https://batbin.me/raw/{paste_id}"

    try:
        async with session.get(raw_url) as response:
            if response.status == 200:
                content_type = response.headers.get("Content-Type", "")
                if "text/plain" in content_type:
                    return await response.text()
                logger.error(f"Unexpected Content-Type ({content_type}) from {raw_url}")
            else:
                logger.error(f"Failed to download {raw_url}: {response.status}")
    except Exception as e:
        logger.error(f"Error fetching {raw_url}: {e}")

    return None


async def save_bin_content(session: aiohttp.ClientSession, url: str) -> str | None:
    """Downloads content from BatBin and saves it as a .txt file."""
    parsed = urlparse(url)
    filename = (
        (parsed.path.strip("/").split("/")[-1] or str(uuid.uuid4()).split("-")[0])
        .split("?")[0]
        .split("#")[0]
    )
    filename += ".txt"
    filepath = os.path.join("cookies", filename)

    content = await fetch_content(session, url)

    content = base64.b64decode(content + "==").decode("utf-8")

    if content:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            async with aiofiles.open(filepath, "w") as f:
                await f.write(content)
            return filepath
        except Exception as e:
            logger.error(f"Error saving file {filepath}: {e}")

    return None


async def save_all_cookies(cookie_urls: list[str]) -> list[str]:
    """Processes multiple URLs concurrently and returns saved file paths."""
    async with aiohttp.ClientSession() as session:
        tasks = [save_bin_content(session, url) for url in cookie_urls]
        results = await asyncio.gather(*tasks)

    return [res for res in results if res]
