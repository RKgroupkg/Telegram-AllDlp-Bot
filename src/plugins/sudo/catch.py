#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

import datetime
import os
from typing import Any, Dict, List, Tuple

import humanize
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from src import bot
from src.config import CATCH_PATH
from src.helpers.filters import sudo_cmd


def get_file_details(file_path: str) -> Dict[str, Any]:
    """
    Retrieve comprehensive details about a file.

    Args:
        file_path (str): Full path to the file

    Returns:
        Dict containing file metadata
    """
    try:
        stat = os.stat(file_path)
        return {
            "name": os.path.basename(file_path),
            "full_path": file_path,
            "size": humanize.naturalsize(stat.st_size),
            "size_bytes": stat.st_size,
            "created": datetime.datetime.fromtimestamp(stat.st_ctime),
            "modified": datetime.datetime.fromtimestamp(stat.st_mtime),
            "accessed": datetime.datetime.fromtimestamp(stat.st_atime),
            "permissions": oct(stat.st_mode)[-3:],
            "is_directory": os.path.isdir(file_path),
            "extension": os.path.splitext(file_path)[1],
        }
    except Exception as e:
        return {"error": str(e)}


def paginate_files(
    files: List[str], page: int = 1, items_per_page: int = 10
) -> Tuple[List[str], int, int]:
    """
    Paginate file list with advanced handling.

    Args:
        files (List[str]): List of file paths
        page (int): Current page number
        items_per_page (int): Files per page

    Returns:
        Tuple of paginated files, total pages, current page
    """
    total_files = len(files)
    total_pages = max(1, (total_files + items_per_page - 1) // items_per_page)

    # Ensure page is within valid range
    page = max(1, min(page, total_pages))

    start_index = (page - 1) * items_per_page
    end_index = start_index + items_per_page

    paginated_files = files[start_index:end_index]

    return paginated_files, total_pages, page


def create_file_list_keyboard(
    files: List[str], current_page: int, total_pages: int, callback_prefix: str
) -> InlineKeyboardMarkup:
    """
    Create an intelligent, minimalist navigation keyboard.

    Args:
        files (List[str]): Current page files
        current_page (int): Current page number
        total_pages (int): Total page count
        callback_prefix (str): Callback data prefix

    Returns:
        Inline keyboard markup
    """
    keyboard = []

    # File selection buttons with compact representation
    for file in files:
        file_name = os.path.basename(file)
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"| {file_name[:30]}{'...' if len(file_name) > 30 else ''}",
                    callback_data=f"{callback_prefix}_fileinfo_{file}",
                )
            ]
        )

    # Minimalist navigation row
    nav_row = []
    if current_page > 1:
        nav_row.append(
            InlineKeyboardButton(
                "◄ Prev", callback_data=f"{callback_prefix}_page_{current_page-1}"
            )
        )

    nav_row.append(
        InlineKeyboardButton(f"[{current_page}/{total_pages}]", callback_data="noop")
    )

    if current_page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                "Next ►", callback_data=f"{callback_prefix}_page_{current_page+1}"
            )
        )

    if nav_row:
        keyboard.append(nav_row)

    # Minimalist additional options
    keyboard.append(
        [
            InlineKeyboardButton(
                "♤ Clear All", callback_data=f"{callback_prefix}_clear_all"
            )
        ]
    )

    return InlineKeyboardMarkup(keyboard)


@bot.on_message(filters.command("catch") & sudo_cmd)
async def catch_file_manager(client, message: Message):
    """
    Comprehensive catch file management interface.
    """
    catch_files = [
        os.path.join(CATCH_PATH, f)
        for f in os.listdir(CATCH_PATH)
        if os.path.isfile(os.path.join(CATCH_PATH, f))
    ]

    if not catch_files:
        return await message.reply_text("♚ No files in catch directory.")

    paginated_files, total_pages, current_page = paginate_files(catch_files)

    keyboard = create_file_list_keyboard(
        paginated_files, current_page, total_pages, "catch"
    )

    await message.reply_text(
        f"۩ Catch Files | {current_page}/{total_pages} pages", reply_markup=keyboard
    )


@bot.on_callback_query(filters.regex(r"^catch_"))
async def catch_callback_handler(client, callback_query):
    """
    Advanced callback handler for file management.
    """
    data = callback_query.data

    if data == "noop":
        await callback_query.answer("Current page")
        return

    if data.startswith("catch_page_"):
        page = int(data.split("_")[-1])
        catch_files = [
            os.path.join(CATCH_PATH, f)
            for f in os.listdir(CATCH_PATH)
            if os.path.isfile(os.path.join(CATCH_PATH, f))
        ]

        paginated_files, total_pages, current_page = paginate_files(catch_files, page)

        keyboard = create_file_list_keyboard(
            paginated_files, current_page, total_pages, "catch"
        )

        await callback_query.edit_message_text(
            f"۩ Catch Files | {current_page}/{total_pages} pages", reply_markup=keyboard
        )

    elif data.startswith("catch_fileinfo_"):
        file_path = data.split("catch_fileinfo_")[-1]
        file_details = get_file_details(file_path)

        details_text = "\n".join(
            [
                f"**File:** __{file_details['name']}__",
                f"**Path:** `{file_details['full_path']}`",
                f"**Size:** __{file_details['size']} ({file_details['size_bytes']} bytes)__",
                f"**Created:** __{file_details['created'].strftime('%Y-%m-%d %H:%M:%S')}__",
                f"**Modified:** __{file_details['modified'].strftime('%Y-%m-%d %H:%M:%S')}__",
                f"**Perms:** __{file_details['permissions']}__",
            ]
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "♧ Delete", callback_data=f"catch_delete_{file_path}"
                    )
                ],
                [InlineKeyboardButton("◄ Back", callback_data="catch_page_1")],
            ]
        )

        await callback_query.edit_message_text(details_text, reply_markup=keyboard)

    elif data.startswith("catch_delete_"):
        file_path = data.split("catch_delete_")[-1]
        try:
            os.unlink(file_path)
            await callback_query.answer(f"Deleted: {os.path.basename(file_path)}")

            catch_files = [
                os.path.join(CATCH_PATH, f)
                for f in os.listdir(CATCH_PATH)
                if os.path.isfile(os.path.join(CATCH_PATH, f))
            ]

            if not catch_files:
                await callback_query.edit_message_text("No files remaining.")
                return

            paginated_files, total_pages, current_page = paginate_files(catch_files)

            keyboard = create_file_list_keyboard(
                paginated_files, current_page, total_pages, "catch"
            )

            await callback_query.edit_message_text(
                f"۩ Catch Files | {current_page}/{total_pages} pages",
                reply_markup=keyboard,
            )

        except Exception as e:
            await callback_query.answer(f"Error: {e}")

    elif data == "catch_clear_all":
        catch_files = [
            os.path.join(CATCH_PATH, f)
            for f in os.listdir(CATCH_PATH)
            if os.path.isfile(os.path.join(CATCH_PATH, f))
        ]

        deleted_count = sum(
            1 for file_path in catch_files if os.unlink(file_path) is None
        )

        await callback_query.answer(f"♧ Cleared {deleted_count} files")
        await callback_query.edit_message_text("♧ All catch files cleared.")


# Requirements
# pyrogram
# humanize
# typing
