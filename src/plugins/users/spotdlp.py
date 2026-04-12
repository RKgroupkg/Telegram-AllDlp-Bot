# File: src/plugins/users/spotdlp.py
#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.

import os
import re
import asyncio
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import time

from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from SpotiFLAC import SpotiFLAC

from src import bot
from src.config import CATCH_PATH
from src.logging import LOGGER
from src.helpers.dlp._rex import (SPOTIFY_ALBUM_REGEX, SPOTIFY_PLAYLIST_REGEX,
                                   SPOTIFY_TRACK_REGEX)
from src.helpers.dlp.yt_dl.catch import (add_video_info_to_cache,
                                          clean_expired_cache)
from src.helpers.dlp.yt_dl.dataclass import SearchInfo
from src.helpers.dlp.yt_dl.utils import create_format_selection_markup
from src.helpers.dlp.yt_dl.ytdl_core import fetch_youtube_info, search_youtube
from src.helpers.filters import is_download_rate_limited

logger = LOGGER(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

class DownloadSource(Enum):
    AUTO    = "auto"
    TIDAL   = "tidal"
    DEEZER  = "deezer"
    YOUTUBE = "youtube"


class AudioFormat(Enum):
    FLAC = ".flac"
    MP3  = ".mp3"
    M4A  = ".m4a"


class Emoji:
    MUSIC    = "♪"
    SPARKLES = "✦"
    DOWNLOAD = "↓"
    CHECK    = "✓"
    ERROR    = "✗"
    WARNING  = "⚠"
    INFO     = "ⓘ"
    LOADING  = "⌛"
    SEARCH   = "⌕"
    ALBUM    = "◉"
    ARTIST   = "♬"
    CLOCK    = "⏲"
    STAR     = "★"
    QUALITY  = "◆"
    FILE     = "▤"
    CANCEL   = "⊗"


CACHE_EXPIRY_MINUTES = 30
MAX_FILENAME_LENGTH  = 200
AUDIO_EXTENSIONS     = (AudioFormat.FLAC.value, AudioFormat.MP3.value, AudioFormat.M4A.value)

# SpotiFLAC service priority lists per user-chosen source
_SERVICE_MAP: Dict[str, List[str]] = {
    DownloadSource.TIDAL.value:   ["tidal"],
    DownloadSource.DEEZER.value:  ["deezer"],
    DownloadSource.AUTO.value:    ["tidal", "deezer", "qobuz", "spoti", "amazon", "youtube"],
    DownloadSource.YOUTUBE.value: ["youtube"],
}

# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TrackSession:
    """
    Lightweight session object stored in cache.
    Only holds what we need to drive the download — no Spotify API calls.
    """
    spotify_url:  str
    track_id:     str
    cached_at:    datetime = field(default_factory=datetime.now)

    # Optional display fields populated from SpotiFLAC metadata if available
    title:        str = "Unknown Title"
    artist:       str = "Unknown Artist"
    album:        str = "Unknown Album"
    duration:     str = "0:00"
    album_art:    Optional[str] = None
    has_isrc:     bool = True           # assume True; SpotiFLAC will sort it out

    @property
    def display_title(self) -> str:
        return f"{self.title} — {self.artist}"


# ══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def extract_spotify_id(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def format_file_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def sanitize_filename(name: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    if not name:
        return "Unknown"
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(name))
    clean = re.sub(r"\s+", " ", clean).strip(". ")
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip(". ")
    return clean or "Unknown"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def find_newest_audio_file(directory: str) -> Optional[str]:
    """Return the most recently modified audio file in *directory*, or None."""
    if not os.path.isdir(directory):
        return None
    candidates = [
        f for f in os.listdir(directory)
        if f.lower().endswith(AUDIO_EXTENSIONS)
    ]
    if not candidates:
        return None
    newest = max(candidates, key=lambda f: os.path.getmtime(os.path.join(directory, f)))
    return os.path.join(directory, newest)


def find_new_audio_files(before: set, directory: str) -> List[str]:
    """Return newly created audio files compared to *before* snapshot."""
    if not os.path.isdir(directory):
        return []
    after = set(os.listdir(directory))
    new   = after - before
    return [
        os.path.join(directory, f)
        for f in new
        if f.lower().endswith(AUDIO_EXTENSIONS)
    ]


def cleanup_files(*paths: str) -> None:
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception as e:
                logger.warning(f"Cleanup failed for {p}: {e}")


async def download_thumbnail(url: str, dest: str) -> Optional[str]:
    if not url:
        return None
    try:
        import requests
        resp = await asyncio.to_thread(requests.get, url, timeout=10)
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(resp.content)
            return dest
        return None
    except Exception as e:
        logger.warning(f"Thumbnail download failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SPOTIFLAC WRAPPER
# ══════════════════════════════════════════════════════════════════════════════

def _blocking_spotiflac(url: str, output_dir: str, services: List[str]) -> Optional[str]:
    """
    Synchronous SpotiFLAC call — must always be run via asyncio.to_thread().

    Takes a directory snapshot before and after, then returns the path of
    the largest new audio file created (or None if nothing was downloaded).
    """
    os.makedirs(output_dir, exist_ok=True)
    before = set(os.listdir(output_dir))

    try:
        SpotiFLAC(
            url=url,
            output_dir=output_dir,
            services=services,
            filename_format="{artist} - {title}",
        )
    except Exception as e:
        logger.error(f"[SpotiFLAC] Exception during download: {e}", exc_info=True)
        return None

    new_files = find_new_audio_files(before, output_dir)
    if not new_files:
        logger.warning("[SpotiFLAC] No new audio files detected after download")
        return None

    # Prefer the largest file (most likely the lossless one when multiple appear)
    new_files.sort(key=os.path.getsize, reverse=True)
    return new_files[0]


async def spotiflac_download(
    url: str,
    output_dir: str,
    source: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Async wrapper around SpotiFLAC.

    Returns (file_path, source_label) or (None, None) on failure.
    source_label is a human-readable string for the Telegram caption.
    """
    services = _SERVICE_MAP.get(source, _SERVICE_MAP[DownloadSource.AUTO.value])

    logger.info(f"[SpotiFLAC] source={source} | services={services} | url={url}")

    file_path = await asyncio.to_thread(_blocking_spotiflac, url, output_dir, services)

    if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        logger.warning(f"[SpotiFLAC] Download yielded no usable file for source={source}")
        return None, None

    # Derive a friendly label from the actual file extension
    ext = os.path.splitext(file_path)[1].lower()
    label_map = {
        DownloadSource.TIDAL.value:   "Tidal HiFi FLAC",
        DownloadSource.DEEZER.value:  "Deezer FLAC",
        DownloadSource.YOUTUBE.value: "YouTube Audio",
        DownloadSource.AUTO.value:    "HiFi FLAC" if ext == AudioFormat.FLAC.value else "Audio",
    }
    source_label = label_map.get(source, "Audio")

    size = format_file_size(os.path.getsize(file_path))
    logger.info(f"[SpotiFLAC] {Emoji.CHECK} {source_label} | {size} | {file_path}")
    return file_path, source_label


# ══════════════════════════════════════════════════════════════════════════════
# SESSION CACHE
# ══════════════════════════════════════════════════════════════════════════════

# track_id → TrackSession
_session_cache: Dict[str, TrackSession] = {}


def cache_session(session: TrackSession) -> None:
    _session_cache[session.track_id] = session


def get_session(track_id: str) -> Optional[TrackSession]:
    return _session_cache.get(track_id)


def evict_session(track_id: str) -> None:
    _session_cache.pop(track_id, None)


# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def build_source_markup(track_id: str) -> InlineKeyboardMarkup:
    """Inline keyboard shown after the user sends a Spotify track link."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"{Emoji.SPARKLES} Auto (Best Quality)",
                callback_data=f"spotify_dl:auto:{track_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"{Emoji.QUALITY} Tidal FLAC",
                callback_data=f"spotify_dl:tidal:{track_id}"
            ),
            InlineKeyboardButton(
                f"{Emoji.MUSIC} Deezer FLAC",
                callback_data=f"spotify_dl:deezer:{track_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                "▶️ YouTube",
                callback_data=f"spotify_dl:youtube:{track_id}"
            )
        ],
    ])


def build_track_caption(session: TrackSession, source_label: Optional[str] = None) -> str:
    lines = [f"<b>{session.title}</b>\n"]
    if session.artist != "Unknown Artist":
        lines.append(f"{Emoji.ARTIST} <i>{session.artist}</i>")
    if session.album != "Unknown Album":
        lines.append(f"{Emoji.ALBUM} <i>{session.album}</i>")
    if session.duration != "0:00":
        lines.append(f"{Emoji.CLOCK} <i>{session.duration}</i>")
    if source_label:
        lines.append(f"{Emoji.QUALITY} <i>{source_label}</i>")
    return "\n".join(lines)


def build_info_message(session: TrackSession) -> str:
    lines = [
        f"<b>{session.title}</b>\n",
        f"{Emoji.ARTIST} <b>Artist:</b> <i>{session.artist}</i>",
        f"{Emoji.ALBUM} <b>Album:</b> <i>{session.album}</i>",
        f"{Emoji.CLOCK} <b>Duration:</b> <i>{session.duration}</i>",
        f"\n{Emoji.QUALITY} <b>High-Quality Sources Available</b>",
        f"<i>{Emoji.INFO} Choose your download source:</i>",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# YOUTUBE FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

async def _youtube_format_selection(
    message: Message,
    session: TrackSession,
    status_msg: Message,
) -> bool:
    """
    Search YouTube and present format-selection markup.
    Returns True if the selection was presented successfully.
    """
    await status_msg.edit_text(
        f"{Emoji.SEARCH} <b>{session.title}</b>\n<i>→ Searching YouTube…</i>"
    )

    clean_expired_cache()
    query       = f"{session.title} {session.artist} official audio"
    results     = await search_youtube(query, max_results=5)

    if not results:
        await status_msg.edit_text(
            f"{Emoji.ERROR} <b>{session.title}</b>\n<i>No YouTube matches found.</i>"
        )
        return False

    youtube_info = await fetch_youtube_info(results[0].id)
    if not youtube_info or not youtube_info.all_formats:
        await status_msg.edit_text(
            f"{Emoji.ERROR} <b>{session.title}</b>\n<i>No downloadable formats available.</i>"
        )
        return False

    add_video_info_to_cache(youtube_info.id, youtube_info)
    markup = create_format_selection_markup(youtube_info.all_formats)

    caption  = build_info_message(session).replace(
        f"{Emoji.QUALITY} <b>High-Quality Sources Available</b>\n", ""
    )
    caption += f"\n▶️ <b>Source:</b> <i>YouTube</i>\n\n"
    caption += f"<i>{Emoji.INFO} Select format to download:</i>"

    if session.album_art:
        await status_msg.delete()
        await message.reply_photo(
            photo=session.album_art, caption=caption,
            reply_markup=markup, quote=True
        )
    else:
        await status_msg.edit_text(caption, reply_markup=markup)

    return True


# ══════════════════════════════════════════════════════════════════════════════
# MAIN DOWNLOAD + UPLOAD ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

async def download_and_upload(
    message: Message,
    session: TrackSession,
    source: str,
    status_msg: Message,
    selection_msg: Optional[Message] = None,
) -> bool:
    """
    Download the track via SpotiFLAC (or YouTube) and upload it to Telegram.

    Returns True when the audio has been sent (or format-selection presented
    for YouTube), False on unrecoverable failure.
    """
    output_dir = CATCH_PATH
    os.makedirs(output_dir, exist_ok=True)

    file_path   = None
    thumb_path  = None
    source_name = None

    async def _delete_selection():
        if selection_msg:
            try:
                await selection_msg.delete()
            except Exception:
                pass

    try:
        # ── HiFi path (auto / tidal / deezer) ────────────────────────────────
        if source in (DownloadSource.AUTO.value,
                      DownloadSource.TIDAL.value,
                      DownloadSource.DEEZER.value):

            hint = {
                DownloadSource.AUTO.value:   "→ Trying best quality (Tidal › Deezer › Qobuz › …)…",
                DownloadSource.TIDAL.value:  "→ Downloading from Tidal HiFi…",
                DownloadSource.DEEZER.value: "→ Downloading from Deezer…",
            }[source]

            await status_msg.edit_text(
                f"{Emoji.LOADING} <b>{session.title}</b>\n<i>{hint}</i>"
            )

            file_path, source_name = await spotiflac_download(
                session.spotify_url, output_dir, source
            )

            # AUTO mode: cascade to YouTube if all HiFi services failed
            if not file_path and source == DownloadSource.AUTO.value:
                logger.info("[Auto] All HiFi sources failed — falling back to YouTube")
                result = await _youtube_format_selection(message, session, status_msg)
                await _delete_selection()
                return result

        # ── Explicit YouTube ──────────────────────────────────────────────────
        elif source == DownloadSource.YOUTUBE.value:
            result = await _youtube_format_selection(message, session, status_msg)
            await _delete_selection()
            return result

        # ── Upload HiFi file ──────────────────────────────────────────────────
        if file_path and source_name:
            size_str = format_file_size(os.path.getsize(file_path))

            await status_msg.edit_text(
                f"{Emoji.DOWNLOAD} <b>{session.title}</b>\n\n"
                f"{Emoji.ARTIST} <i>{session.artist}</i>\n"
                f"{Emoji.QUALITY} <i>{source_name}</i>\n"
                f"{Emoji.FILE} <i>{size_str}</i>\n\n"
                f"<i>→ Uploading to Telegram…</i>"
            )

            # Thumbnail
            if session.album_art:
                thumb_path = os.path.join(
                    output_dir,
                    f"{sanitize_filename(session.title)}_thumb.jpg"
                )
                thumb_path = await download_thumbnail(session.album_art, thumb_path)

            await message.reply_audio(
                audio=file_path,
                caption=build_track_caption(session, source_name),
                title=session.title,
                performer=session.artist,
                thumb=thumb_path,
                quote=True,
            )

            await status_msg.delete()
            await _delete_selection()
            logger.info(f"{Emoji.CHECK} Upload complete: {session.title}")
            return True

        # ── Nothing worked ────────────────────────────────────────────────────
        await status_msg.edit_text(
            f"{Emoji.ERROR} <b>{session.title}</b>\n"
            f"<i>Download failed from {source.title()}. Try a different source.</i>"
        )
        await _delete_selection()
        return False

    except Exception as e:
        logger.error(f"download_and_upload error: {e}", exc_info=True)
        await status_msg.edit_text(
            f"{Emoji.ERROR} <b>Unexpected error</b>\n<i>{str(e)[:200]}</i>"
        )
        await _delete_selection()
        return False

    finally:
        cleanup_files(file_path, thumb_path)


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGE HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@bot.on_message(
    filters.regex(SPOTIFY_TRACK_REGEX)
    | filters.command(["spt", "spotify", "sptdlp", "dlmusic"])
    & is_download_rate_limited
)
async def spotify_track_handler(_, message: Message):
    """
    Intercepts Spotify track links.

    We no longer call the Spotify Web API at all — we only need the track ID
    to build the session and the URL to pass to SpotiFLAC later.
    The source-selection UI is shown immediately with no network round-trip.
    """
    track_id = extract_spotify_id(message.text, SPOTIFY_TRACK_REGEX)
    if not track_id:
        logger.warning("Could not extract track ID from message")
        return

    # Reconstruct a canonical Spotify URL (handles shortened/regional URLs)
    spotify_url = f"https://open.spotify.com/track/{track_id}"

    # Build a minimal session — no API call needed
    session = TrackSession(spotify_url=spotify_url, track_id=track_id)
    cache_session(session)

    markup   = build_source_markup(track_id)
    msg_text = (
        f"{Emoji.MUSIC} <b>Spotify Track</b>\n\n"
        f"<code>{track_id}</code>\n\n"
        f"{Emoji.QUALITY} <b>High-Quality Sources Available</b>\n"
        f"<i>{Emoji.INFO} Choose your download source:</i>"
    )

    await message.reply_text(msg_text, reply_markup=markup, quote=True)
    logger.info(f"Source selection presented for track: {track_id}")


@bot.on_callback_query(filters.regex(r"^spotify_dl:"))
async def spotify_download_callback(_, callback_query: CallbackQuery):
    """Handle the source-selection button taps."""
    try:
        _, source, track_id = callback_query.data.split(":", 2)
    except ValueError:
        await callback_query.answer("Invalid callback data.", show_alert=True)
        return

    session = get_session(track_id)
    if not session:
        await callback_query.answer(
            f"{Emoji.WARNING} Session expired. Please send the link again.",
            show_alert=True
        )
        return

    labels = {
        "auto":    f"{Emoji.SPARKLES} Auto",
        "tidal":   f"{Emoji.QUALITY} Tidal",
        "deezer":  f"{Emoji.MUSIC} Deezer",
        "youtube": "▶️ YouTube",
    }
    await callback_query.answer(f"{labels.get(source, source)} — starting download…")

    status_msg = await callback_query.message.reply_text(
        f"{Emoji.LOADING} <b>{session.title}</b>\n"
        f"<i>→ Initialising {source.upper()} download…</i>",
        quote=True
    )

    success = await download_and_upload(
        callback_query.message,
        session,
        source,
        status_msg,
        selection_msg=callback_query.message,
    )

    # Keep the session alive when YouTube format-selection is open
    if success and source != DownloadSource.YOUTUBE.value:
        evict_session(track_id)

    logger.info(f"{'OK' if success else 'FAIL'}: {session.title} via {source}")


# ── Album / Playlist handlers (info-only — unchanged logic) ──────────────────

@bot.on_message(filters.regex(SPOTIFY_ALBUM_REGEX) & is_download_rate_limited)
async def spotify_album_handler(_, message: Message):
    album_id = extract_spotify_id(message.text, SPOTIFY_ALBUM_REGEX)
    if not album_id:
        return

    await message.reply_text(
        f"{Emoji.ALBUM} <b>Spotify Album</b>\n\n"
        f"<code>{album_id}</code>\n\n"
        f"{Emoji.INFO} <i>Individual track downloads only.\n"
        f"Please send a specific track link.</i>",
        quote=True
    )


@bot.on_message(filters.regex(SPOTIFY_PLAYLIST_REGEX) & is_download_rate_limited)
async def spotify_playlist_handler(_, message: Message):
    playlist_id = extract_spotify_id(message.text, SPOTIFY_PLAYLIST_REGEX)
    if not playlist_id:
        return

    await message.reply_text(
        f"📋 <b>Spotify Playlist</b>\n\n"
        f"<code>{playlist_id}</code>\n\n"
        f"{Emoji.INFO} <i>Individual track downloads only.\n"
        f"Please send a specific track link.</i>",
        quote=True
    )


# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND TASK — SESSION CACHE GC
# ══════════════════════════════════════════════════════════════════════════════

async def _cache_gc():
    """Evict sessions older than CACHE_EXPIRY_MINUTES every 10 minutes."""
    while True:
        try:
            await asyncio.sleep(600)
            cutoff  = datetime.now() - timedelta(minutes=CACHE_EXPIRY_MINUTES)
            expired = [tid for tid, s in _session_cache.items() if s.cached_at < cutoff]
            for tid in expired:
                evict_session(tid)
            if expired:
                logger.info(f"{Emoji.INFO} GC: evicted {len(expired)} expired sessions")
        except Exception as e:
            logger.error(f"Cache GC error: {e}")


asyncio.create_task(_cache_gc())