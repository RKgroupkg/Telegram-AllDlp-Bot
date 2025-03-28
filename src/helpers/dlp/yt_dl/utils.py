# src/helpers/dlp/yt_dl/utils.py
#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

import re
from typing import List, Dict, Any, Optional
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.helpers.dlp.yt_dl.catch import store_callback_data

YT_LINK_REGEX = r"(?:https?:\/\/)?(?:www\.|m\.|music\.)?" + \
                r"(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|playlist\?(?:.*&)?list=|" + \
                r"embed\/|v\/|channel\/|user\/|" + \
                r"attribution_link\?(?:.*&)?u=\/watch\?(?:.*&)?v=)|" + \
                r"youtu\.be\/|youtube\.com\/clip\/|youtube\.com\/live\/)([a-zA-Z0-9_-]{11}|" + \
                r"[a-zA-Z0-9_-]{12,}(?=&|\?|$))"


def extract_video_id(text: str) -> Optional[str]:
    """
    Extract YouTube video ID from a URL
    
    Args:
        text: Text containing a YouTube URL
        
    Returns:
        YouTube video ID or None if not found
    """
    match = re.search(YT_LINK_REGEX, text)
    if match:
        return match.group(1)
    return None

def generate_format_buttons(formats: List[Dict[str, Any]], page: int = 0, items_per_page: int = 5) -> List[List[InlineKeyboardButton]]:
    """
    Generate paginated format selection buttons
    
    Args:
        formats: List of format dictionaries
        page: Current page number (zero-based)
        items_per_page: Number of items to show per page
        
    Returns:
        List of button rows for keyboard markup
    """
    if not formats:
        return []
    
    total_pages = (len(formats) + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(formats))
    
    buttons = []
    # Add format buttons for current page
    for idx in range(start_idx, end_idx):
        fmt = formats[idx]
        if fmt.get('acodec') != 'none' and fmt.get('vcodec') != 'none':
            # Both audio and video
            quality = fmt.get('height', 'N/A')
            file_size = fmt.get('filesize', fmt.get('filesize_approx', 0))
            size_text = f"{file_size / (1024 * 1024):.1f}MB" if file_size else "Unknown"
            label = f"≡ {quality}p • {fmt.get('ext')} • {size_text}"
        elif fmt.get('vcodec') != 'none':
            # Video only
            quality = fmt.get('height', 'N/A')
            file_size = fmt.get('filesize', fmt.get('filesize_approx', 0))
            size_text = f"{file_size / (1024 * 1024):.1f}MB" if file_size else "Unknown"
            label = f"⌬ {quality}p • {fmt.get('ext')} • {size_text}"
        else:
            # Audio only
            file_size = fmt.get('filesize', fmt.get('filesize_approx', 0))
            size_text = f"{file_size / (1024 * 1024):.1f}MB" if file_size else "Unknown"
            label = f"∻ {fmt.get('asr', 'N/A')}kHz • {fmt.get('ext')} • {size_text}"
        
        # Store format selection data in cache and get a callback ID
        format_data = {
            'type': 'format',
            'video_id': formats[idx].get('video_id'),
            'format_id': fmt['format_id']
        }
        format_callback_id = store_callback_data(format_data)
        
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"ytdl_{format_callback_id}"
            )
        ])
    
    # Add pagination controls
    pagination_buttons = []
    
    # Store page data for previous button
    if page > 0:
        prev_page_data = {
            'type': 'page',
            'video_id': formats[0].get('video_id') if formats else None,
            'page': page - 1
        }
        prev_callback_id = store_callback_data(prev_page_data)
        pagination_buttons.append(
            InlineKeyboardButton(
                text="◄ Previous",
                callback_data=f"ytpage_{prev_callback_id}"
            )
        )
    
    # Store video info data
    if formats:
        info_data = {
            'type': 'info',
            'video_id': formats[0].get('video_id')
        }
        info_callback_id = store_callback_data(info_data)
        pagination_buttons.append(
            InlineKeyboardButton(
                text=f"▢ {page+1}/{total_pages}",
                callback_data=f"ytinfo_{info_callback_id}"
            )
        )
    
    # Store page data for next button
    if page < total_pages - 1:
        next_page_data = {
            'type': 'page',
            'video_id': formats[0].get('video_id') if formats else None,
            'page': page + 1
        }
        next_callback_id = store_callback_data(next_page_data)
        pagination_buttons.append(
            InlineKeyboardButton(
                text="Next ►",
                callback_data=f"ytpage_{next_callback_id}"
            )
        )
    
    buttons.append(pagination_buttons)
    
    # Add category filter buttons
    if formats:
        # Store filter data for each category
        all_filter_data = {
            'type': 'filter',
            'video_id': formats[0].get('video_id'),
            'filter_type': 'all',
            'page': 0
        }
        video_filter_data = {
            'type': 'filter',
            'video_id': formats[0].get('video_id'),
            'filter_type': 'video',
            'page': 0
        }
        audio_filter_data = {
            'type': 'filter',
            'video_id': formats[0].get('video_id'),
            'filter_type': 'audio',
            'page': 0
        }
        
        
        all_callback_id = store_callback_data(all_filter_data)
        video_callback_id = store_callback_data(video_filter_data)
        audio_callback_id = store_callback_data(audio_filter_data)
        
        filter_buttons = [
            InlineKeyboardButton(
                text="∑ All",
                callback_data=f"ytfilter_{all_callback_id}"
            ),
            InlineKeyboardButton(
                text="⌬ Video",
                callback_data=f"ytfilter_{video_callback_id}"
            ),
            InlineKeyboardButton(
                text="∻ Audio",
                callback_data=f"ytfilter_{audio_callback_id}"
            )
        ]
        
        flac_filter_data = {
            'type': 'flac_filter',
            'video_id': formats[0].get('video_id'),
            'page': page
        }
        flac_callback_id = store_callback_data(flac_filter_data)
        
        best_filter_data = {
            'type': 'best_filter',
            'video_id': formats[0].get('video_id'),
            'page': page
        }
        best_callback_id = store_callback_data(best_filter_data)
        
        flac_button = [
            InlineKeyboardButton(
                text="♪ Flac Audio",
                callback_data=f"ytflac_{flac_callback_id}"  # Use consistent prefix
            ),
            InlineKeyboardButton(
                text="♛ Best Video",
                callback_data=f"ytbestVideo_{best_callback_id}"  # Use consistent prefix
            )
        ]
        buttons.append(filter_buttons)
        buttons.append(flac_button)
    # Add cancel button
    if formats:
        cancel_data = {
            'type': 'cancel',
            'video_id': formats[0].get('video_id')
        }
        cancel_callback_id = store_callback_data(cancel_data)
        buttons.append([
            InlineKeyboardButton(
                text="✖ Cancel",
                callback_data=f"ytcancel_{cancel_callback_id}"
            )
        ])
    
    return buttons

def create_format_selection_markup(formats: List[Dict[str, Any]], page: int = 0) -> InlineKeyboardMarkup:
    """
    Create an InlineKeyboardMarkup for format selection
    
    Args:
        formats: List of format dictionaries
        page: Current page number
        
    Returns:
        InlineKeyboardMarkup
    """
    buttons = generate_format_buttons(formats, page)
    return InlineKeyboardMarkup(buttons)