#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

import re
from time import time
from typing import Dict, Any, Optional, Tuple

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from pyrogram import filters
from pyrogram.types import Message

from src import bot
from src.helpers.filters import is_ratelimiter_dl
from src.helpers.dlp.yt_dl.ytdl_core import search_youtube, fetch_youtube_info
from src.helpers.dlp.yt_dl.utils import create_format_selection_markup
from src.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

from src.helpers.dlp.yt_dl.dataclass import (
    SearchInfo,
)
from src.helpers.dlp.yt_dl.catch import (
    get_callback_data, get_video_info_from_cache, add_video_info_to_cache,
    clear_video_info_cache, clean_expired_cache
)

# Regex patterns for Spotify links
SPOTIFY_TRACK_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/track/([a-zA-Z0-9]+)"
SPOTIFY_ALBUM_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/album/([a-zA-Z0-9]+)"
SPOTIFY_PLAYLIST_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/playlist/([a-zA-Z0-9]+)"

# Initialize Spotify client
spotify_client = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    auth_manager = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID, 
        client_secret=SPOTIFY_CLIENT_SECRET
    )
    spotify_client = spotipy.Spotify(auth_manager=auth_manager)


def extract_spotify_id(text: str, pattern: str) -> Optional[str]:
    """
    Extract Spotify ID from a URL based on the provided regex pattern
    
    Args:
        text: Text containing a Spotify URL
        pattern: Regex pattern to use for extraction
        
    Returns:
        Spotify ID or None if not found
    """
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    return None


def format_duration(ms: int) -> str:
    """
    Format duration in milliseconds to a readable format
    
    Args:
        ms: Duration in milliseconds
        
    Returns:
        Formatted duration string (mm:ss)
    """
    total_seconds = int(ms / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


async def get_spotify_track_info(track_id: str) -> Optional[Dict[str, Any]]:
    """
    Get track information from Spotify API
    
    Args:
        track_id: Spotify track ID
        
    Returns:
        Dictionary with track information or None if not found
    """
    if not spotify_client:
        return None
        
    try:
        track = spotify_client.track(track_id)
        
        # Extract relevant information
        track_info = {
            'title': track['name'],
            'artist': ', '.join([artist['name'] for artist in track['artists']]),
            'album': track['album']['name'],
            'release_date': track['album'].get('release_date', 'Unknown'),
            'duration_ms': track['duration_ms'],
            'duration_formatted': format_duration(track['duration_ms']),
            'preview_url': track['preview_url'],
            'spotify_url': track['external_urls']['spotify'],
            'album_art': track['album']['images'][0]['url'] if track['album']['images'] else None,
            'popularity': track.get('popularity', 0)
        }
        
        return track_info
    except Exception as e:
        print(f"Error fetching Spotify track info: {str(e)}")
        return None


async def find_youtube_match(track_info: Dict[str, Any]) -> Optional[SearchInfo]:
    """
    Find a matching YouTube video for a Spotify track
    
    Args:
        track_info: Spotify track information
        
    Returns:
        Tuple of (YouTube video info, video_id) or (None, None) if no match found
    """
    search_query = f"{track_info['title']} {track_info['artist']} official audio"
    
    # Search for the track on YouTube
    search_results = await search_youtube(search_query, max_results=5)
    
    if not search_results:
        return None
    
    video_info = await fetch_youtube_info(search_results[0].id)
    
    return video_info


@bot.on_message(filters.regex(SPOTIFY_TRACK_REGEX)|filters.command(["spt","spotify","sptdlp","dlmusic"]) & is_ratelimiter_dl)
async def spotify_track_handler(_, message: Message):
    """Handle Spotify track links and convert to YouTube download options"""
    
    # Check if Spotify client is configured
    if not spotify_client:
        await message.reply_text(
            "︎︎⚠ Spotify integration not configured. Contact administrator to set up API credentials.",
            quote=True
        )
        return
    
    # Extract Spotify track ID
    track_id = extract_spotify_id(message.text, SPOTIFY_TRACK_REGEX)
    if not track_id:
        return
    
    # Send initial processing message
    status_msg = await message.reply_text(
        "♪ <b>Spotify track detected</b>\n\n<i>Fetching information...</i>",
        quote=True
    )
    
    try:
        # Get track info from Spotify
        track_info = await get_spotify_track_info(track_id)
        if not track_info:
            await status_msg.edit_text("✖ Failed to fetch track information from Spotify.")
            return
        
        # Update status message
        await status_msg.edit_text(
            f"♪ <b>Found:</b> <i>{track_info['title']}</i>\n"
            f"♫ <i>Searching on YouTube...</i>"
        )

        # Run cache cleanup
        clean_expired_cache()

        # Find YouTube match
        youtube_info = await find_youtube_match(track_info)
        if not youtube_info:
            await status_msg.edit_text(
                f"♪ <b>{track_info['title']}</b>\n"
                f"✖ <i>No YouTube match found</i>"
            )
            return
        
        try:
            if youtube_info:
                # Add to cache
                add_video_info_to_cache(youtube_info.id, youtube_info)
        except Exception as e:
            raise e
        
        # Create format selection markup
        formats = youtube_info.all_formats
        
        if not formats:
            await status_msg.edit_text(
                f"♪ <b>{track_info['title']}</b>\n"
                f"✖ <i>No downloadable formats found</i>"
            )
            return
        
        # Show available formats
        format_markup = create_format_selection_markup(formats)
        
        # Delete status message if album art exists
        if track_info['album_art']:
            await status_msg.delete()
            
            # Create rich info message with minimal design
            info_text = (
                f"<i>{track_info['title']}</i>\n\n"
                f"♪ <b>Artist:</b> <i>{track_info['artist']}</i>\n"
                f"◉ <b>Album:</b> <i>{track_info['album']}</i>\n"
                f"◈ <b>Released:</b> <i>{track_info['release_date']}</i>\n"
                f"◷ <b>Length:</b> <i>{track_info['duration_formatted']}</i>\n"
                f"✧ <b>Popularity:</b> <i>{track_info['popularity']}/100</i>\n\n"
                f"<i>Select format to download:</i>"
            )
            
            # Send as photo with caption and format selection buttons
            await message.reply_photo(
                photo=track_info['album_art'],
                caption=info_text,
                reply_markup=format_markup,
                quote=True
            )
        else:
            # Create minimal info message without photo
            info_text = (
                f"<b>{track_info['title']}</b>\n\n"
                f"♪ <b>Artist:</b> <i>{track_info['artist']}</i>\n"
                f"◉ <b>Album:</b> <i>{track_info['album']}</i>\n"
                f"◈ <b>Released:</b> <i>{track_info['release_date']}</i>\n"
                f"◷ <b>Length:</b> <i>{track_info['duration_formatted']}</i>\n"
                f"✧ <b>Popularity:</b> <i>{track_info['popularity']}/100</i>\n\n"
                f"<i>Select format to download:</i>"
            )
            
            await status_msg.edit_text(
                info_text,
                reply_markup=format_markup
            )
        
    except Exception as e:
        await status_msg.edit_text(f"✖ Error: {str(e)}")

@bot.on_message(filters.regex(SPOTIFY_ALBUM_REGEX) & is_ratelimiter_dl)
async def spotify_album_handler(_, message: Message):
    """Handle Spotify album links with minimal response"""
    
    # Check if Spotify client is configured
    if not spotify_client:
        await message.reply_text(
            "⚠ Spotify integration not configured. Contact administrator to set up API credentials.",
            quote=True
        )
        return
    
    # Extract Spotify album ID
    album_id = extract_spotify_id(message.text, SPOTIFY_ALBUM_REGEX)
    if not album_id:
        return
    
    try:
        # Get basic album info from Spotify
        album = spotify_client.album(album_id)
        
        album_name = album['name']
        artist_name = album['artists'][0]['name']
        release_date = album.get('release_date', 'Unknown')
        total_tracks = album.get('total_tracks', 0)
        album_art = album['images'][0]['url'] if album['images'] else None
        
        # Create minimal info message
        info_text = (
            f"◉ <b>{album_name}</b>\n\n"
            f"♪ <b>Artist:</b> <i>{artist_name}</i>\n"
            f"◈ <b>Released:</b> </i>{release_date}</i>\n"
            f"♫ <b>Tracks:</b> <i>{total_tracks}</i>\n\n"
            f"<i>Individual track download only. Please send specific track links.</i>"
        )
        
        if album_art:
            await message.reply_photo(
                photo=album_art,
                caption=info_text,
                quote=True
            )
        else:
            await message.reply_text(info_text, quote=True)
        
    except Exception as e:
        await message.reply_text(f"✖ Error: {str(e)}", quote=True)


@bot.on_message(filters.regex(SPOTIFY_PLAYLIST_REGEX) & is_ratelimiter_dl)
async def spotify_playlist_handler(_, message: Message):
    """Handle Spotify playlist links with minimal response"""
    
    # Check if Spotify client is configured
    if not spotify_client:
        await message.reply_text(
            "⚠ Spotify integration not configured. Contact administrator to set up API credentials.",
            quote=True
        )
        return
    
    # Extract Spotify playlist ID
    playlist_id = extract_spotify_id(message.text, SPOTIFY_PLAYLIST_REGEX)
    if not playlist_id:
        return
    
    try:
        # Get basic playlist info from Spotify
        playlist = spotify_client.playlist(playlist_id)
        
        playlist_name = playlist['name']
        owner_name = playlist['owner']['display_name']
        total_tracks = playlist['tracks']['total']
        playlist_art = playlist['images'][0]['url'] if playlist['images'] else None
        
        # Create minimal info message
        info_text = (
            f"≡ <b>{playlist_name}</b>\n\n"
            f"♫ <b>By:</b> <i>{owner_name}</i>\n"
            f"♪ <b>Tracks:</b> </i>{total_tracks}</i>\n\n"
            f"<i>Individual track download only. Please send specific track links.</i>"
        )
        
        if playlist_art:
            await message.reply_photo(
                photo=playlist_art,
                caption=info_text,
                quote=True
            )
        else:
            await message.reply_text(info_text, quote=True)
        
    except Exception as e:
        await message.reply_text(f"✖ Error: {str(e)}", quote=True)