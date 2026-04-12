# File: src/plugins/sudo/admin.py

from pyrogram import filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from pyrogram.enums import ParseMode

from src import bot
from src.helpers.filters import sudo_cmd
from src.database.MongoDb import users

USERS_PER_PAGE = 8
AUTO_BAN_WARN = 3
AUTO_BAN_SPAM = 5


# ───────────────────────────────────────────── #
#               SAFE SEND                      #
# ───────────────────────────────────────────── #

async def safe_send(client, user_id, text):
    try:
        await client.send_message(user_id, text)
    except:
        pass


# ───────────────────────────────────────────── #
#               MAIN PANEL                     #
# ───────────────────────────────────────────── #

@bot.on_message(filters.command("users") & sudo_cmd)
async def admin_panel(_, message: Message):

    total = await users.collection.count_documents({})
    banned = await users.collection.count_documents({"banned": True})
    warned = await users.collection.count_documents({"warn_count": {"$gt": 0}})

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1. Browse Users", "adm_list_1")],
        [InlineKeyboardButton("2. Search User", "adm_search")],
        [InlineKeyboardButton("3. Statistics", "adm_stats")],
        [InlineKeyboardButton("4. Broadcast", "adm_bc")],
        [InlineKeyboardButton("Close", "adm_close")]
    ])

    await message.reply_text(
        "**[ User Management Panel ]**\n\n"
        "──────────────────────────────\n"
        f"Total Users  : {total}\n"
        f"Banned       : {banned}\n"
        f"Warned       : {warned}\n"
        "──────────────────────────────\n\n"
        "Select an option:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


# ───────────────────────────────────────────── #
#               USER LIST                      #
# ───────────────────────────────────────────── #

async def build_list(page):

    data = await users.collection.find({}).to_list(length=None)
    total = len(data)

    pages = max(1, (total + USERS_PER_PAGE - 1)//USERS_PER_PAGE)
    page = max(1, min(page, pages))

    subset = data[(page-1)*USERS_PER_PAGE: page*USERS_PER_PAGE]

    text = (
        "**[ User List ]**\n\n"
        f"Page {page}/{pages}\n"
        "──────────────────────────────"
    )

    buttons = []

    for u in subset:
        buttons.append([
            InlineKeyboardButton(
                f"{u.get('name','Unknown')} ({u['_id']})",
                callback_data=f"adm_view_{u['_id']}_{page}"
            )
        ])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ Prev", f"adm_list_{page-1}"))
    if page < pages:
        nav.append(InlineKeyboardButton("Next ▶", f"adm_list_{page+1}"))

    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("Back", "adm_home")])

    return text, InlineKeyboardMarkup(buttons)


# ───────────────────────────────────────────── #
#               USER PROFILE                   #
# ───────────────────────────────────────────── #

async def build_profile(client, uid, page):

    user = await users.read_document(uid)
    if not user:
        return "User not found.", None, None

    warns = user.get("warn_count", 0)
    spam = user.get("rate_limit", 0)

    text = (
        "**[ User Profile ]**\n\n"
        "──────────────────────────────\n"
        f"ID        : {uid}\n"
        f"Name      : {user.get('name','N/A')}\n"
        f"Username  : @{user.get('username','None')}\n"
        f"Warns     : {warns}\n"
        f"SpamHits  : {spam}\n"
        f"Banned    : {'Yes' if user.get('banned') else 'No'}\n"
        "──────────────────────────────"
    )

    buttons = [
        [
            InlineKeyboardButton("Warn", f"adm_warn_{uid}_{page}"),
            InlineKeyboardButton("Reset", f"adm_unwarn_{uid}_{page}")
        ],
        [
            InlineKeyboardButton("Ban", f"adm_ban_{uid}_{page}"),
            InlineKeyboardButton("Unban", f"adm_unban_{uid}_{page}")
        ],
        [
            InlineKeyboardButton("+Spam", f"adm_spamup_{uid}_{page}"),
            InlineKeyboardButton("-Spam", f"adm_spamdown_{uid}_{page}")
        ],
        [
            InlineKeyboardButton("Message", f"adm_msg_{uid}")
        ],
        [
            InlineKeyboardButton("Back", f"adm_list_{page}")
        ]
    ]

    # Try profile photo
    photo = None
    try:
        photos = await client.get_profile_photos(uid, limit=1)
        if photos:
            photo = photos[0].file_id
    except:
        pass

    return text, InlineKeyboardMarkup(buttons), photo


# ───────────────────────────────────────────── #
#               CALLBACKS                      #
# ───────────────────────────────────────────── #

@bot.on_callback_query(filters.regex("^adm_"))
async def callbacks(client, q: CallbackQuery):

    data = q.data

    # HOME
    if data == "adm_home":
        return await admin_panel(client, q.message)

    # LIST
    elif data.startswith("adm_list_"):
        page = int(data.split("_")[2])
        text, kb = await build_list(page)
        await q.message.edit_text(text, reply_markup=kb)

    # PROFILE
    elif data.startswith("adm_view_"):
        _, _, uid, page = data.split("_")
        text, kb, photo = await build_profile(client, int(uid), int(page))

        if photo:
            await q.message.reply_photo(photo, caption=text, reply_markup=kb)
            await q.message.delete()
        else:
            await q.message.edit_text(text, reply_markup=kb)

    # ACTIONS
    elif any(x in data for x in ["warn","unwarn","ban","unban","spamup","spamdown"]):

        _, action, uid, page = data.split("_")
        uid = int(uid)

        user = await users.read_document(uid)
        if not user:
            return await q.answer("User not found", True)

        update = {}

        if action == "warn":
            warns = user.get("warn_count", 0) + 1
            update["warn_count"] = warns

            await safe_send(client, uid,
                f"You have been warned.\nWarnings: {warns}")

            if warns >= AUTO_BAN_WARN:
                update["banned"] = True
                await safe_send(client, uid, "You are banned due to warnings.")

        elif action == "unwarn":
            update["warn_count"] = 0

        elif action == "ban":
            update["banned"] = True
            await safe_send(client, uid, "You are banned.")

        elif action == "unban":
            update["banned"] = False

        elif action == "spamup":
            spam = user.get("rate_limit", 0) + 1
            update["rate_limit"] = spam

            if spam >= AUTO_BAN_SPAM:
                update["banned"] = True
                await safe_send(client, uid, "You are banned for spam.")

        elif action == "spamdown":
            update["rate_limit"] = max(0, user.get("rate_limit", 0) - 1)

        await users.update_document(uid, update)

        text, kb, _ = await build_profile(client, uid, int(page))
        await q.message.edit_text(text, reply_markup=kb)

    # SEARCH PROMPT
    elif data == "adm_search":
        await q.message.edit_text(
            "**[ Search User ]**\n\nReply with name or username.",
            parse_mode=ParseMode.MARKDOWN
        )

    # BROADCAST PROMPT
    elif data == "adm_bc":
        await q.message.edit_text(
            "**[ Broadcast ]**\n\nReply with message to broadcast.",
            parse_mode=ParseMode.MARKDOWN
        )

    # MESSAGE USER PROMPT
    elif data.startswith("adm_msg_"):
        uid = int(data.split("_")[2])
        await q.message.edit_text(
            f"**[ Message User ]**\n\nReply to send message to `{uid}`",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_stats":
        total = await users.collection.count_documents({})
        banned = await users.collection.count_documents({"banned": True})

        await q.message.edit_text(
            "**[ Statistics ]**\n\n"
            "──────────────────────────────\n"
            f"Total Users : {total}\n"
            f"Banned      : {banned}\n"
            "──────────────────────────────",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "adm_close":
        await q.message.delete()


# ───────────────────────────────────────────── #
#           REPLY HANDLER (SAFE)               #
# ───────────────────────────────────────────── #

@bot.on_message(filters.reply & sudo_cmd)
async def reply_handler(client, msg: Message):

    if not msg.reply_to_message:
        return

    base = msg.reply_to_message.text or ""

    # SEARCH
    if "[ Search User ]" in base:

        query = msg.text.replace("@", "")

        user = await users.collection.find_one({
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"username": {"$regex": query, "$options": "i"}}
            ]
        })

        if not user:
            return await msg.reply("No user found.")

        text, kb, photo = await build_profile(client, user["_id"], 1)

        if photo:
            await msg.reply_photo(photo, caption=text, reply_markup=kb)
        else:
            await msg.reply(text, reply_markup=kb)

    # BROADCAST
    elif "[ Broadcast ]" in base:

        data = await users.collection.find({}).to_list(length=None)

        sent, fail = 0, 0

        for u in data:
            try:
                await msg.copy(u["_id"])
                sent += 1
            except:
                fail += 1

        await msg.reply(f"Done.\nSent: {sent}\nFailed: {fail}")

    # MESSAGE USER
    elif "[ Message User ]" in base:

        import re
        uid = int(re.findall(r"\d+", base)[0])

        try:
            await msg.copy(uid)
            await msg.reply("Message sent.")
        except:
            await msg.reply("Failed to send.")