# File: src/plugins/sudo/users.py
#  Copyright (c) 2026 Rkgroup.
#  Quick Dl - Robust Admin Management System
#  All-in-one file implementation

import math
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from src.helpers.filters import sudo_cmd


# ─── DATABASE IMPORTS ──────────────────────────────────────────────────────────
# Ensure these imports point correctly to your existing Mongo setup
try:
    from src.database.MongoDb import users, chats
except ImportError:
    # Fallback/Placeholder if imports fail
    users = None 

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────
USERS_PER_PAGE = 8


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def get_status_emoji(db_user: dict) -> str:
    if db_user.get("banned"): return "🔴"
    if db_user.get("warn_count", 0) > 0: return "🟡"
    return "🟢"
async def build_main_menu(page: int = 1):
    """Fetches users from DB and builds the paginated list."""
    # Try accessing the collection via .get_all() or .col (common in wrappers)
    # If your wrapper has a 'find' method inside a 'col' attribute:
    try:
        # Check if your wrapper uses .collection or .col
        coll = getattr(users, "collection", getattr(users, "col", None))
        
        if coll:
            all_users = await coll.find({}).to_list(length=None)
        else:
            # If it's the wrapper from your 'save_user' snippet, 
            # you might need to use its specific fetch method
            all_users = await users.get_all_users() # Adjust to your actual method name
    except Exception as e:
        print(f"Database Fetch Error: {e}")
        return "❌ **Database Error.**", None

    if not all_users:
        return "📭 **No users found in database.**", None
    
    total_pages = math.ceil(len(all_users) / USERS_PER_PAGE)
    start = (page - 1) * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    subset = all_users[start:end]

    text = (
        f"♚ **𝚄𝚜𝚎𝚛 𝙼𝚊𝚗𝚊𝚐𝚎𝚖𝚎𝚗𝚝 𝙿𝚊𝚗𝚎𝚕**\n"
        f"⟢ Total Users: `{len(all_users)}`\n"
        f"⟢ Page: `{page}/{total_pages}`\n\n"
        f"Select a user below to manage their permissions:"
    )

    buttons = []
    for u in subset:
        u_id = u.get("_id")
        name = u.get("name", "Unknown User")[:15]
        status = get_status_emoji(u)
        buttons.append([
            InlineKeyboardButton(f"{status} {name} ({u_id})", callback_data=f"adm_view_{u_id}")
        ])

    # Navigation Row
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm_page_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_page_{page+1}"))
    
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton("🗑 Close", callback_data="adm_close")])

    return text, InlineKeyboardMarkup(buttons)

# ─── COMMAND HANDLER ───────────────────────────────────────────────────────────

@Client.on_message(filters.command("users") & sudo_cmd)
async def admin_users_list(client: Client, message: Message):
    text, markup = await build_main_menu(page=1)
    await message.reply_text(text, reply_markup=markup)

# ─── CALLBACK HANDLERS ────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^adm_"))
async def admin_callback_handler(client: Client, cb: CallbackQuery):
    data = cb.data
    
    # 1. Pagination
    if data.startswith("adm_page_"):
        page = int(data.split("_")[2])
        text, markup = await build_main_menu(page)
        await cb.message.edit_text(text, reply_markup=markup)

    # 2. View Individual User
    elif data.startswith("adm_view_"):
        u_id = int(data.split("_")[2])
        db_user = await users.find_one({"_id": u_id})
        
        if not db_user:
            return await cb.answer("User not found in DB.", show_alert=True)

        joined = db_user.get("date", "Unknown")
        if isinstance(joined, datetime): joined = joined.strftime("%Y-%m-%d")

        profile_text = (
            f"👤 **𝚄𝚜𝚎𝚛 𝙳𝚎𝚝𝚊𝚒𝚕𝚜: {u_id}**\n\n"
            f"⟢ **Name:** `{db_user.get('name')}`\n"
            f"⟢ **Username:** @{db_user.get('username', 'None')}\n"
            f"⟢ **Joined:** `{joined}`\n"
            f"⟢ **Warnings:** `{db_user.get('warn_count', 0)}`\n"
            f"⟢ **Banned:** `{'Yes' if db_user.get('banned') else 'No'}`\n"
        )

        buttons = [
            [
                InlineKeyboardButton("➕ Warn", callback_data=f"adm_warn_{u_id}"),
                InlineKeyboardButton("➖ Unwarn", callback_data=f"adm_unwarn_{u_id}")
            ],
            [
                InlineKeyboardButton("🚫 Ban", callback_data=f"adm_ban_{u_id}"),
                InlineKeyboardButton("✅ Unban", callback_data=f"adm_unban_{u_id}")
            ],
            [InlineKeyboardButton("🔙 Back to List", callback_data="adm_page_1")]
        ]
        await cb.message.edit_text(profile_text, reply_markup=InlineKeyboardMarkup(buttons))

    # 3. Action Logic (Warn/Ban)
    elif "_warn_" in data or "_ban_" in data or "_un" in data:
        action, target_id = data.split("_")[1], int(data.split("_")[2])
        
        if action == "warn":
            await users.update_one({"_id": target_id}, {"$inc": {"warn_count": 1}})
            await cb.answer("User Warned! ⚠️", show_alert=False)
        elif action == "unwarn":
            await users.update_one({"_id": target_id}, {"$set": {"warn_count": 0}})
            await cb.answer("Warnings Reset! ✅")
        elif action == "ban":
            await users.update_one({"_id": target_id}, {"$set": {"banned": True}})
            await cb.answer("User Banned! 🚫", show_alert=True)
        elif action == "unban":
            await users.update_one({"_id": target_id}, {"$set": {"banned": False}})
            await cb.answer("User Unbanned! 🔓")

        # Refresh the view
        cb.data = f"adm_view_{target_id}"
        await admin_callback_handler(client, cb)

    # 4. Close
    elif data == "adm_close":
        await cb.message.delete()

    await cb.answer()