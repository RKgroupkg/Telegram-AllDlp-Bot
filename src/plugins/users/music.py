from datetime import timedelta
from typing import List, Union
from src.helpers.dlp.yt_dl.dataclass import (
    VideoSearchResult,
    PlaylistSearchResult,
)


from pyrogram import filters
from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery, 
    Message
)

from src import bot
from src.helpers.filters import is_rate_limited,is_download_callback_rate_limited
from src.helpers.dlp.yt_dl.ytdl_core import search_youtube, fetch_youtube_info
from pyrogram.enums import ParseMode

from src.helpers.dlp.yt_dl.ytdl_core import (
    fetch_youtube_info,
    MAX_VIDEO_LENGTH_MINUTES
)
from src.helpers.dlp.yt_dl.catch import (
    get_video_info_from_cache,
    add_video_info_to_cache, 
    clean_expired_cache
)
from src.helpers.dlp.yt_dl.utils import create_format_selection_markup
from src.helpers.dlp._util import (
    truncate_text,
    format_duration
)
from src.logging import LOGGER
logger = LOGGER(__name__)

# Store search results temporarily 
MUSIC_SEARCH_CACHE = {}


@bot.on_message(filters.command(["music","search","play"]) & is_rate_limited)
async def music_search(_, message: Message):
    """
    Search YouTube for music tracks with enhanced presentation
    """
    try:
        # Extract search query
        query = message.text.split(" ", 1)
        if len(query) < 2:
            return await message.reply_text(
                "<b>[!] Invalid Search</b>\n"
                "Provide a music search query.\n"
                "Usage: <code>/music &lt;song name&gt;</code>",
                parse_mode=ParseMode.HTML
            )
        
        query = query[1]
        logger.info(f"Music search initiated by {message.from_user.id}: {query}")
        msg = await message.reply_text(
            f"⌕ <b>Searching</b> <i>{query[:50]}..</i>",
            quote = True,
            parse_mode = ParseMode.HTML 
        )
        # Perform YouTube search
        results = await search_youtube(query, max_results=20)
        
        if not results:
            return await message.reply_text(
                "<b>⚠ No Results</b>\n"
                "No music tracks found for your query.",
                parse_mode=ParseMode.HTML
            )
        
        # Store results in cache with user's message ID as key
        user_id = message.from_user.id
        MUSIC_SEARCH_CACHE[user_id] = results
        
        # Create initial results page
        await send_music_results(msg, results, page=0)
    
    except Exception as e:
        logger.error(f"⚠ Music search error: {str(e)}")
        await msg.edit_text(
            f"<b>⚠ Search Error</b>\n{str(e)}",
            parse_mode=ParseMode.HTML
        )

async def send_music_results(
    message: Message, 
    results: List[Union[VideoSearchResult, PlaylistSearchResult]], 
    page: int = 0, 
    results_per_page: int = 5
):
    """
    Send music search results with advanced pagination and minimalist design
    """
    try:
        # Calculate pagination details
        start_idx = page * results_per_page
        end_idx = start_idx + results_per_page
        current_page_results = results[start_idx:end_idx]
        
        # Prepare results message
        result_text = ["<i>✧ Music Search Results..</i>\n\n"]
        keyboard = []
        
        for idx, result in enumerate(current_page_results, 1):
            # Truncate and clean up track details
            title = truncate_text(result.title, 40)
            uploader = truncate_text(result.uploader, 25)
            duration = format_duration(result.duration)
            
            track_info = (
                f"<code>〔{start_idx + idx}〕.</code> "
                f"<b>{title}</b>\n"
                f"    -<i>{uploader} | {duration}</i>\n\n"
            )
            result_text.append(track_info)
            
            # Create compact callback button with shortened title
            short_title = truncate_text(result.title, 15)
            callback_data = f"music_select:{result.id}"
            keyboard.append([
                InlineKeyboardButton(
                    f"〔{start_idx + idx}〕 {short_title}", 
                    callback_data=callback_data
                )
            ])
        
        # Pagination buttons with minimalist design
        nav_buttons = []
        total_pages = (len(results) + results_per_page - 1) // results_per_page
        
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    "◄ Previous", 
                    callback_data=f"music_page:{page-1}"
                )
            )
        
        nav_buttons.append(
            InlineKeyboardButton(
                f"Page {page + 1}/{total_pages}", 
                callback_data="page_info"
            )
        )
        
        if end_idx < len(results):
            nav_buttons.append(
                InlineKeyboardButton(
                    "Next ►", 
                    callback_data=f"music_page:{page+1}"
                )
            )
        
        keyboard.append(nav_buttons)
        
        # Minimalist additional options
        keyboard.append([
            InlineKeyboardButton(
                "+ More", 
                callback_data="music_load_more"
            ),
            InlineKeyboardButton(
                "✖ Close", 
                callback_data="music_cancel"
            )
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send or edit message
        full_result_text = "\n".join(result_text)
        
        if isinstance(message, Message):
            await message.edit_text(
                full_result_text, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        elif isinstance(message, CallbackQuery):
            await message.edit_message_text(
                full_result_text, 
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        
      
    except Exception as e:
        logger.error(f"Error in sending music results: {str(e)}")
        await message.reply_text(
            f"<b>⚠ Display Error</b>\n{str(e)}",
            parse_mode=ParseMode.HTML
        )

@bot.on_callback_query(filters.regex("^music_select:")& is_download_callback_rate_limited)
async def music_select_handler(_, query: CallbackQuery):
    """
    Handle music track selection
    """
    try:
        # Run cache cleanup
        clean_expired_cache()


        # Extract music track ID
        video_id = query.data.split(":")[1]
        user_id = query.from_user.id
        msg = None


        if user_id != query.message.reply_to_message.from_user.id:
            return await query.answer(
                "This command is not initiated by you.", show_alert=True
            )
        
        await query.message.delete()
        # Retrieve cached results for the user
        results = MUSIC_SEARCH_CACHE.get(user_id, [])

         # Send a new message to the same chat and topic
        msg = await bot.send_message(
            chat_id=query.message.chat.id,
            text="<b>⌕ Getting more info..</b>", 
            message_thread_id=query.message.message_thread_id if query.message.is_topic_message else None,
            parse_mode=ParseMode.HTML
        )
        
        # Find the selected track
        selected_track = next((track for track in results if track.id == video_id), None)
        
        if selected_track:
            # Fetch video information with retries
            cached_info = get_video_info_from_cache(video_id)
            if cached_info:
                info = cached_info
                logger.info(f"Using cached info for video {video_id}")
            else:
                logger.info(f"Fetching info for video {video_id}")
                try:
                    info = await fetch_youtube_info(video_id)
                    if info.success:
                        add_video_info_to_cache(video_id, info)
                    else:
                        await msg.edit_text(
                            "<b>⚠ Sorry failed to get info for the selected video</b>", 
                            parse_mode=ParseMode.HTML
                        )
                        return

                except Exception as e:
                        raise e
            
             # Check video duration
            duration_minutes = info.duration / 60
            if duration_minutes > MAX_VIDEO_LENGTH_MINUTES:
                await msg.edit_text(
                    f"⚠ Video is too long ({int(duration_minutes)} minutes). Maximum allowed duration is {MAX_VIDEO_LENGTH_MINUTES} minutes."
                )
                return
            # Format duration
            duration_str = str(timedelta(seconds=info.duration))
            
                
            # Create format selection markup
            formats = info.all_formats
            if not formats:
                await msg.edit_text(
                    f"♪ <b>{info.thumbnail}</b>\n"
                    f"✖ <i>No downloadable formats found</i>"
                )
                return
            # Show available formats
            format_markup = create_format_selection_markup(formats)
            await msg.edit_text(
                f"≡ __{info.title[:30]}...__\n\n"
                f"𓇳 Uploader: __{info.uploader}__\n"
                f"⦿ Duration: __{duration_str}__\n"
                f"⌘ Views: __{info.view_count}__\n"
                f"[​]({info.thumbnail})\n"
                f"Please select a format to download:",
                reply_markup=format_markup
            )
            
        
        else:
            await msg.edit_text("Track not found.")
    
    except Exception as e:
        logger.error(f"Music selection error: {str(e)}")
        await msg.edit_text(f"**Please retry **\n\n Error: {str(e)}")


# Placeholder for additional callback handlers
@bot.on_callback_query(filters.regex("^music_")& is_download_callback_rate_limited)
async def music_callback_handler(_, query: CallbackQuery):
    """
    Handle music-related callback queries
    """
    try:
        # Extract callback type and data
        callback_data = query.data.split(":")
        callback_type = callback_data[0]
        
        # Route to appropriate handler based on callback type
        if callback_type == "music_page":
            # Handle pagination
            page = int(callback_data[1])
            user_id = query.from_user.id
            results = MUSIC_SEARCH_CACHE.get(user_id, [])
            
            if results:
                await send_music_results(query, results, page=page)
        
        # Add more callback handlers as needed
        
    except Exception as e:
        logger.error(f"Callback query error: {str(e)}")
        await query.answer(f"Error: {str(e)}", show_alert=True)