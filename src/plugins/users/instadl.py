#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

import re
import asyncio
from typing import List, Optional, Dict, Any
import uuid

from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPrivileges,
    InputMediaPhoto,
    InputMediaVideo,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InlineQueryResultVideo,
    InputTextMessageContent
)
from src.helpers.filters import is_ratelimited,is_ratelimiter_dl
from src.helpers.dlp.Insta_dl.insta_dl import get_instagram_post_data
from src.helpers.decorators import catch_errors

from src.config import RAPID_API_KEYS
from src.helpers.start_constants import BOT_NAME  # bot name
from src.logging import LOGGER

# Instagram URL patterns
INSTAGRAM_URL_PATTERN = r"https?://(?:www\.)?instagram\.com/(?:share/)?(?:p|reel|tv)/([a-zA-Z0-9_-]+)(?:/[a-zA-Z0-9_-]+)?"

# Cache for storing recently processed Instagram media (to avoid repeated API calls)
MEDIA_CACHE = {}
CACHE_TTL = 3600  # Cache time-to-live in seconds (1 hour)


class InstagramDownloader:
    """
    A class to handle Instagram media downloading functionality.
    """
    
    @staticmethod
    async def extract_media_url(instagram_url: str) -> Optional[Dict[str, Any]]:
        """
        Extract media URLs from an Instagram post.
        
        Args:
            instagram_url: The Instagram post URL
            
        Returns:
            Dictionary containing media information or None if extraction failed
        """
        # Check cache first
        if instagram_url in MEDIA_CACHE:
            LOGGER(__name__).info(f"Using cached data for: {instagram_url}")
            return MEDIA_CACHE[instagram_url]
            
        try:
            LOGGER(__name__).info(f"Extracting media from: {instagram_url}")
            result = get_instagram_post_data(instagram_url, RAPID_API_KEYS)
            if result:
                # Cache the result
                MEDIA_CACHE[instagram_url] = result
                
                # Schedule cache cleanup
                asyncio.create_task(InstagramDownloader._cleanup_cache(instagram_url))
                
                return result
            else:
                LOGGER(__name__).error("No media URLs extracted")
                return None
        except Exception as e:
            LOGGER(__name__).error(f"Error extracting media URL: {e}")
            return None
    
    @staticmethod
    async def _cleanup_cache(url: str) -> None:
        """Clean up cached entries after TTL expires."""
        await asyncio.sleep(CACHE_TTL)
        if url in MEDIA_CACHE:
            del MEDIA_CACHE[url]
            LOGGER(__name__).debug(f"Removed {url} from cache")


# Function to extract all Instagram URLs from a message
def extract_instagram_urls(text: str) -> List[str]:
    """Extract all Instagram post URLs from the given text."""
    if not text:
        return []
    
    matches = re.finditer(INSTAGRAM_URL_PATTERN, text)
    return [match.group(0) for match in matches]


# Filter for messages containing Instagram links
def instagram_link_filter(_, __, message: Message) -> bool:
    """Filter to check if a message contains Instagram links."""
    if message.text:
        return bool(re.search(INSTAGRAM_URL_PATTERN, message.text))
    return False


# Register the custom filter
instagram_filter = filters.create(instagram_link_filter)


@Client.on_message(instagram_filter & ~filters.bot & ~filters.via_bot & filters.incoming & is_ratelimiter_dl)
@catch_errors
async def instagram_downloader_handler(client: Client, message: Message) -> None:
    """
    Handle messages containing Instagram links and download media.
    
    Args:
        client: The Pyrogram client instance
        message: The incoming message containing Instagram links
    """
    chat_id = message.chat.id
    message_id = message.id
    message_viaUser = message
    user_id = message.from_user.id if message.from_user else None
    username = message.from_user.mention if message.from_user else "Anonymous"

    # Get the bot's own user ID
    me = await client.get_me()
    bot_id = me.id
    bot_member = None 

    # Log the incoming request
    LOGGER(__name__).info(f"Instagram link detected from user {user_id} in chat {chat_id}")
    
    # Extract all Instagram URLs from the message
    instagram_urls = extract_instagram_urls(message.text or "")
    
    if not instagram_urls:
        return
    
    # Send "processing" message to inform the user
    processing_msg = await message.reply_text(
            f"≡ Processing Instagram link{'s' if len(instagram_urls) > 1 else ''}...",
            quote=True,
            disable_notification=True,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Open Instagram", url=instagram_urls[0])]  # Take the first URL
                ]
            )
        )
    
    try:
        # Get the last Instagram URL from the message
        instagram_url = instagram_urls[-1]
        
        # Check if message only contains the Instagram URL or has additional text
        only_instagram_link = message.text.strip() == instagram_url
        
        # Extract downloadable media data
        downloader = InstagramDownloader()
        media_data = await downloader.extract_media_url(instagram_url)
        
        # Prepare caption
        if message.chat.type == enums.ChatType.PRIVATE:
            # Case 1: Private chat
            caption = f"≡ Instagram media\n\n"
            if media_data.get("caption"):
                caption += f"Caption: <i>{media_data['caption'][:300]}</i>"
                if len(media_data['caption']) > 300:
                    caption += "..."
            caption += f"\n\nBy: {BOT_NAME}"
        else:
            # Case 2 & 3: Group/Supergroup chat
            try:
                # Get the bot's ChatMember object
                bot_member = await client.get_chat_member(chat_id=chat_id, user_id=bot_id)
            except Exception as e:
                LOGGER(__name__).error(f"An error occurred while getting my chat_member error: {e}")
            
            caption = f"≡ <i>Instagram media requested by:</i> {username}"
            
            # Add original msg if not just a link
            if not only_instagram_link:
                # Truncate original message if too long
                original_text = message.text.replace(instagram_url, f" ") # <i><a href='{instagram_url}'>Video</a></i>
                if len(original_text) > 200:
                    original_text = original_text[:97] + "..."
                caption = f"\n\n{username} : {original_text}"
        
        # Process and send media depending on type and number
        medias = media_data.get("medias", [])
        
        if not medias:
            await processing_msg.edit_text("✖ No media found in this Instagram post.")
            return
        

        insta_app_markup = InlineKeyboardMarkup(
                        [
                            [InlineKeyboardButton("◉ Open Instagram", url=instagram_url)]  # Take the first URL
                        ]
                    )
        

        # Special handling for the first media
        if len(medias) == 1:
            # Send single media file
            media_item = medias[0]
            media_url = media_item.get("link")
            
            if media_item.get("type") == "image":
                await message.reply_photo(
                    photo=media_url,
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML,
                    quote=True,
                    reply_markup=insta_app_markup
                )
                
            else:  # video or other type
                await message.reply_video(
                    video=media_url,
                    caption=caption,
                    parse_mode=enums.ParseMode.HTML,
                    quote=True,
                    reply_markup=insta_app_markup
                )
                
        else:     
            # If more than one media, send the rest (up to 10 items per group)
            if len(medias) > 1:
                # Maximum 10 media items per group in Telegram
                # Assuming this is part of a larger function or handler
                for i in range(0, len(medias), 10):  # Changed 1 to 0 to include the first item
                    media_group = []
                    batch = medias[i:i + 10]
                    
                    for item in batch:
                        media_url = item.get("link")
                        if item.get("type") == "image":
                            media_group.append(InputMediaPhoto(media=media_url))
                        else:  # video or other type
                            media_group.append(InputMediaVideo(media=media_url))
                    
                    if media_group:
                        try:
                            await client.send_media_group(
                                chat_id=chat_id,
                                media=media_group,
                                reply_to_message_id=message_id,
                                disable_notification=True,
                            )
                        except Exception as e:
                            LOGGER(__name__).error(f"Error sending media group: {e}")
                            # Try to send them individually if media group fails
                            for item in batch:
                                try:
                                    media_url = item.get("link")
                                    if item.get("type") == "image":
                                        await message.reply_photo(photo=media_url, quote=True)
                                    else:
                                        await message.reply_video(video=media_url, quote=True)
                                except Exception as e_inner:
                                    LOGGER(__name__).error(f"Error sending individual media: {e_inner}")
        
        # Delete the processing message
        await processing_msg.delete()
        # Try deleting user msg if perm is there in group for it.
        try:
            if bot_member:  # if it's None then likely it isn't in a group
                if bot_member.status == enums.ChatMemberStatus.ADMINISTRATOR and bot_member.privileges:
                    privileges: ChatPrivileges = bot_member.privileges
                    
                    # Check if the bot can delete messages
                    if privileges.can_delete_messages:
                        if only_instagram_link:  # Dont remove if has msg not just a link
                            await message_viaUser.delete()
                else:
                    LOGGER(__name__).debug("Bot doesn't have privilege to delete.")
        except Exception as e:
            LOGGER(__name__).error(f"An error occurred while trying to delete msg of user in grp/spgrp error: {e}")
        
    except Exception as e:
        LOGGER(__name__).error(f"Error processing Instagram link: {e}")
        await processing_msg.edit_text(f"✖ Error: {str(e)}")


# Alternative command to manually trigger download for a specific Instagram link
@Client.on_message(filters.command(["instagram", "insta", "igdl"]) & is_ratelimiter_dl)
@catch_errors
async def instagram_command_handler(client: Client, message: Message) -> None:
    """
    Command handler for manual Instagram downloads.
    Usage: /instagram [Instagram URL]
    """
    if len(message.command) < 2:
        await message.reply_text(
            "⚠ Please provide an Instagram link.\n"
            "Usage: `/instagram [Instagram URL]`",
            quote=True
        )
        return
    
    # Extract URL from command
    instagram_url = message.command[1]
    
    # Validate URL
    if not re.match(INSTAGRAM_URL_PATTERN, instagram_url):
        await message.reply_text("✖ Invalid Instagram URL format.", quote=True)
        return
    
    # Send processing message
    processing_msg = await message.reply_text("📥 Processing Instagram link...", quote=True)
    
    try:
        # Extract downloadable media data
        downloader = InstagramDownloader()
        media_data = await downloader.extract_media_url(instagram_url)
        
        if not media_data:
            await processing_msg.edit_text("✖ Failed to extract media from Instagram link.")
            return
        
        # Prepare caption
        caption = f"≡ Instagram media\n\n"
        if media_data.get("caption"):
            caption += f"Caption: {media_data['caption'][:300]}"
            if len(media_data['caption']) > 300:
                caption += "..."
        
        # Process and send media depending on type and number
        medias = media_data.get("medias", [])
        
        if not medias:
            await processing_msg.edit_text("✖ No media found in this Instagram post.")
            return
            
        # Special handling for the first media
        if len(medias) == 1:
            # Send single media file
            media_item = medias[0]
            media_url = media_item.get("link")
            
            if media_item.get("type") == "image":
                await message.reply_photo(
                    photo=media_url,
                    caption=caption,
                    quote=True
                )
            else:  # video or other type
                await message.reply_video(
                    video=media_url,
                    caption=caption,
                    quote=True
                )
        else:    
            # If more than one media, send the rest (up to 10 items per group)
            if len(medias) > 1:
                # Maximum 10 media items per group in Telegram
                # We already sent the first item, so start from the second
                for i in range(0, len(medias), 10):  # Start from 0 to include all media
                    media_group = []
                    batch = medias[i:i+10]
                    
                    for item in batch:
                        media_url = item.get("link")
                        if item.get("type") == "image":
                            media_group.append(InputMediaPhoto(media=media_url))
                        else:  # video or other type
                            media_group.append(InputMediaVideo(media=media_url))
                    
                    if media_group:
                        try:
                            await client.send_media_group(
                                chat_id=message.chat.id,
                                media=media_group,
                                reply_to_message_id=message.id
                            )
                        except Exception as e:
                            LOGGER(__name__).error(f"Error sending media group: {e}")
                            # Try to send them individually if media group fails
                            for item in batch:
                                try:
                                    media_url = item.get("link")
                                    if item.get("type") == "image":
                                        await message.reply_photo(photo=media_url, quote=True)
                                    else:
                                        await message.reply_video(video=media_url, quote=True)
                                except Exception as e_inner:
                                    LOGGER(__name__).error(f"Error sending individual media: {e_inner}")
        
        # Delete the processing message
        await processing_msg.delete()
        
    except Exception as e:
        LOGGER(__name__).error(f"Error processing Instagram link: {e}")
        await processing_msg.edit_text(f"✖ Error: {str(e)}")


# Help command to show information about Instagram downloader feature
@Client.on_message(filters.command(["ighelp"]) & is_ratelimited)
async def instagram_help_handler(client: Client, message: Message) -> None:
    """Provide help information about the Instagram downloader feature."""
    help_text = (
        "≡ **Instagram Downloader Help**\n\n"
        "This bot can extract and download media from Instagram links.\n\n"
        "**Automatic Detection:**\n"
        "Just send an Instagram post link, and I'll download it for you.\n\n"
        "**Manual Command:**\n"
        "`/instagram [Instagram URL]` - Download media from a specific Instagram link\n"
        "`/insta [Instagram URL]` - Shorthand for the above command\n"
        "`/igdl [Instagram URL]` - Another shorthand\n\n"
        "**Inline Usage:**\n"
        f"Type `{BOT_NAME} https://instagram.com/...` in any chat to share Instagram media directly.\n\n"
        "**Supported Link Types:**\n"
        "- Instagram posts: `instagram.com/p/...`\n"
        "- Instagram reels: `instagram.com/reel/...`\n"
        "- IGTV: `instagram.com/tv/...`\n\n"
        "**Note:** The bot works in private chats, groups, and inline mode."
    )
    
    await message.reply_text(
        help_text, 
        quote=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Try Inline Mode", switch_inline_query_current_chat="https://instagram.com/")]
        ])
    )

def instagram_inline_filter(_, __, query: InlineQuery):
    """
    Custom filter to check if an inline query contains an Instagram link.
    
    Args:
        query: The InlineQuery object
        
    Returns:
        bool: True if the query contains an Instagram link, False otherwise
    """
    if not query.query:
        return False
    
    # Check if the query matches the Instagram pattern
    return bool(re.search(INSTAGRAM_URL_PATTERN, query.query.strip()))

# Register the custom filter
instagram_inline = filters.create(instagram_inline_filter)


# New inline handler for Instagram content
@Client.on_inline_query(instagram_inline)
@catch_errors
async def instagram_inline_handler(client: Client, inline_query: InlineQuery) -> None:
    """
    Handle inline queries for Instagram links.
    
    This allows users to share Instagram content directly in any chat using inline mode.
    
    Args:
        client: The Pyrogram client instance
        inline_query: The inline query object
    """
    query = inline_query.query.strip()
    
    # Get bot username for later use
    try:
        bot_info = await client.get_me()
        bot_username = bot_info.username
    except Exception as e:
        LOGGER(__name__).error(f"Failed to get bot info: {e}")
        bot_username = "InstagramDLBot"  # Fallback value
    
    # # If no query or not an Instagram URL, show a helper message
    # if not query:
    #     await inline_query.answer(
    #         results=[
    #             InlineQueryResultArticle(
    #                 title="Instagram Downloader",
    #                 description=f"Paste an Instagram URL here to download",
    #                 input_message_content=InputTextMessageContent(
    #                     f"To use Instagram Downloader, type @{bot_username} followed by an Instagram URL"
    #                 ),
    #                 thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
    #                 id=str(uuid.uuid4())
    #             )
    #         ],
    #         cache_time=1
    #     )
    #     return
    
    # Extract all Instagram URLs from the query
    instagram_urls = extract_instagram_urls(query)
    
    if not instagram_urls:
        # If no Instagram URL found, try to see if it might be a partial URL
        if "instagram" in query.lower() or "/p/" in query or "/reel/" in query or "/tv/" in query:
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        title="Invalid Instagram URL",
                        description="Please enter a complete Instagram URL",
                        input_message_content=InputTextMessageContent(
                            "To use Instagram Downloader, enter a valid Instagram URL like:\n"
                            "https://www.instagram.com/p/XXXXX/\n"
                            "https://www.instagram.com/reel/XXXXX/"
                        ),
                        thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                        id=str(uuid.uuid4())
                    )
                ],
                cache_time=1
            )
        else:
            # Not an Instagram-related query, return empty results
            await inline_query.answer(
                results=[],
                cache_time=1
            )
        return
    
    # Get the first valid Instagram URL
    instagram_url = instagram_urls[0]
    LOGGER(__name__).info(f"Processing inline query for Instagram URL: {instagram_url}")
    
    # Extract downloadable media data
    try:
        downloader = InstagramDownloader()
        media_data = await downloader.extract_media_url(instagram_url)
        
        # Prepare results array - we'll construct this regardless of success
        inline_results = []
        
        # If media extraction failed or no media available
        if not media_data or not media_data.get("medias"):
            LOGGER(__name__).warning(f"No media found for URL: {instagram_url}")
            inline_results.append(
                InlineQueryResultArticle(
                    title="No Media Found",
                    description="Could not extract media from this Instagram URL",
                    input_message_content=InputTextMessageContent(
                        f"No media found at: {instagram_url}\n\nTry downloading directly in chat."
                    ),
                    thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                    id=str(uuid.uuid4())
                )
            )
        else:
            # Media extraction successful
            LOGGER(__name__).info(f"Successfully extracted {len(media_data.get('medias', []))} media items")
            
            # Get media items (limit to first 5 for inline mode)
            medias = media_data.get("medias", [])[:5]
            total_media_count = len(media_data.get("medias", []))
            
            # Process each media item
            for i, media_item in enumerate(medias):
                media_url = media_item.get("link")
                media_type = media_item.get("type")
                result_id = str(uuid.uuid4())
                
                # Basic caption without original caption to avoid issues
                caption = f" "
                
                # Add media item number if multiple items
                if total_media_count > 1:
                    caption += f" [Item {i+1}/{total_media_count}]"
                
                try:
                    if media_type == "image":
                        # Create photo result
                        inline_results.append(
                            InlineQueryResultPhoto(
                                photo_url=media_url,
                                thumb_url=media_url,
                                caption=caption,
                                id=result_id
                            )
                        )
                    else:  # video or other type
                        # Get thumbnail or use default
                        thumb_url = media_item.get("thumbnail", "https://static.poder360.com.br/2021/12/instagram-logo.jpg")
                        
                        # Create video result
                        inline_results.append(
                            InlineQueryResultVideo(
                                video_url=media_url,
                                thumb_url=thumb_url,
                                title=f"Instagram {'Video' if media_type == 'video' else 'Media'} {i+1}",
                                description="Tap to send",
                                caption=caption,
                                mime_type="video/mp4",
                                id=result_id
                            )
                        )
                except Exception as item_error:
                    # Log error and add fallback article result
                    LOGGER(__name__).error(f"Error creating result for media item {i+1}: {item_error}")
                    inline_results.append(
                        InlineQueryResultArticle(
                            title=f"Media {i+1} (View in chat)",
                            description="Unable to preview this media",
                            input_message_content=InputTextMessageContent(
                                f"Instagram media: {media_url}\n\n{caption}"
                            ),
                            thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                            id=result_id
                        )
                    )
            
            # Add "More items" note if needed
            if total_media_count > 5:
                inline_results.append(
                    InlineQueryResultArticle(
                        title=f"+ {total_media_count - 5} More Items Available",
                        description="Send link directly to chat to see all",
                        input_message_content=InputTextMessageContent(instagram_url),
                        thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                        id=str(uuid.uuid4())
                    )
                )
        
        # Always add a "Direct Link" option as fallback
        inline_results.append(
            InlineQueryResultArticle(
                title="Share Original Instagram Link",
                description=instagram_url,
                input_message_content=InputTextMessageContent(instagram_url),
                thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                id=str(uuid.uuid4())
            )
        )
        
        # Add a command option as well
        inline_results.append(
            InlineQueryResultArticle(
                title="Use Command Instead",
                description="/instagram or /igdl command",
                input_message_content=InputTextMessageContent(f"/instagram {instagram_url}"),
                thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                id=str(uuid.uuid4())
            )
        )
        
        # Ensure we have at least one result
        if not inline_results:
            inline_results.append(
                InlineQueryResultArticle(
                    title="Error Processing Request",
                    description="Try sending the link directly to chat",
                    input_message_content=InputTextMessageContent(instagram_url),
                    thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                    id=str(uuid.uuid4())
                )
            )
        
        # Answer the inline query with our results
        LOGGER(__name__).info(f"Answering inline query with {len(inline_results)} results")
        await inline_query.answer(
            results=inline_results,
            cache_time=3600  # Cache for 1 hour
        )
        
    except Exception as e:
        LOGGER(__name__).error(f"Error in Instagram inline handler: {e}")
        # Always provide some results, even in case of error
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    title="Error Processing Instagram URL",
                    description="Could not process this Instagram link",
                    input_message_content=InputTextMessageContent(
                        f"Could not process Instagram URL: {instagram_url}\n\nTry sending the link directly to chat."
                    ),
                    thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                    id=str(uuid.uuid4())
                ),
                InlineQueryResultArticle(
                    title="Share Original Instagram Link",
                    description=instagram_url,
                    input_message_content=InputTextMessageContent(instagram_url),
                    thumb_url="https://static.poder360.com.br/2021/12/instagram-logo.jpg",
                    id=str(uuid.uuid4())
                )
            ],
            cache_time=5  # Short cache time for errors
        )