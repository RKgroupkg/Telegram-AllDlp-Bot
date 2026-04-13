# File: src/plugins/sudo/admin.py
# ╔══════════════════════════════════════════════════════════╗
# ║              ADMIN PANEL  ·  admin.py                   ║
# ║   Full-featured sudo user-management for Pyrogram bot   ║
# ╚══════════════════════════════════════════════════════════╝

import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from pyrogram import filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from pyrogram.enums import ParseMode
from pyrogram.errors import (
    UserIsBlocked, InputUserDeactivated, PeerIdInvalid,
    FloodWait, BadRequest
)

from src import bot
from src.helpers.filters import sudo_cmd
from src.database.MongoDb import users

# ─── Logger ────────────────────────────────────────────────
log = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────
USERS_PER_PAGE  = 8
AUTO_BAN_WARN   = 3
AUTO_BAN_SPAM   = 5
BROADCAST_DELAY = 0.05   # seconds between sends (flood guard)
MAX_SEARCH_HITS = 5      # max results per search query

# ─── UI: typography constants ──────────────────────────────
DIV  = "─" * 30          # thin divider
HDR  = "═" * 30          # heavy divider
BULL = "·"               # neutral inline separator


# ════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════

async def safe_send(client, user_id: int, text: str) -> bool:
    """
    Deliver a message to a user silently.
    Returns True on success, False on any failure.
    Auto-retries once on FloodWait.
    """
    try:
        await client.send_message(user_id, text)
        return True
    except (UserIsBlocked, InputUserDeactivated):
        log.debug("safe_send: user %s unreachable (blocked/deactivated)", user_id)
    except PeerIdInvalid:
        log.debug("safe_send: invalid peer %s", user_id)
    except FloodWait as e:
        log.warning("safe_send: FloodWait %ss for user %s", e.value, user_id)
        await asyncio.sleep(e.value)
        return await safe_send(client, user_id, text)
    except Exception as exc:
        log.warning("safe_send: unexpected error for %s: %s", user_id, exc)
    return False


async def cb_answer(q: CallbackQuery, text: str, alert: bool = False) -> None:
    """Answer a callback query, silently swallowing stale-query errors."""
    try:
        await q.answer(text, show_alert=alert)
    except Exception:
        pass


async def edit_or_reply(
    q: CallbackQuery,
    text: str,
    kb: Optional[InlineKeyboardMarkup] = None,
    parse_mode: ParseMode = ParseMode.MARKDOWN,
) -> None:
    """Edit the current message; fall back to a new reply if editing fails."""
    try:
        await q.message.edit_text(text, reply_markup=kb, parse_mode=parse_mode)
    except BadRequest:
        pass  # message unchanged / too old – silent no-op
    except Exception as exc:
        log.debug("edit_or_reply fallback: %s", exc)
        try:
            await q.message.reply_text(text, reply_markup=kb, parse_mode=parse_mode)
        except Exception:
            pass


def fmt_dt(ts) -> str:
    """Format a Unix timestamp or datetime object to a concise UTC string."""
    if ts is None:
        return "—"
    try:
        if isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts, tz=timezone.utc)
        return ts.strftime("%Y-%m-%d  %H:%M UTC")
    except Exception:
        return str(ts)


def warn_bar(count: int, cap: int = AUTO_BAN_WARN) -> str:
    """Textual progress bar  e.g.  [██░]  2 / 3"""
    filled = min(count, cap)
    return f"[{'█' * filled}{'░' * (cap - filled)}]  {count} / {cap}"


def spam_bar(count: int, cap: int = AUTO_BAN_SPAM) -> str:
    filled = min(count, cap)
    return f"[{'█' * filled}{'░' * (cap - filled)}]  {count} / {cap}"


def back_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("« Back",  "adm_home"),
        InlineKeyboardButton("Close",   "adm_close"),
    ]])


# ════════════════════════════════════════════════════════════
#  PANEL BUILDER
# ════════════════════════════════════════════════════════════

async def _panel_text_and_kb() -> Tuple[str, InlineKeyboardMarkup]:
    total  = await users.collection.count_documents({})
    banned = await users.collection.count_documents({"banned": True})
    warned = await users.collection.count_documents({"warn_count": {"$gt": 0}})
    active = total - banned

    text = (
        f"**ADMIN PANEL**\n"
        f"`{HDR}`\n"
        f"`  Users       {total:>8,}`\n"
        f"`  Active      {active:>8,}`\n"
        f"`  Banned      {banned:>8,}`\n"
        f"`  Warned      {warned:>8,}`\n"
        f"`{HDR}`"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Browse Users",  "adm_list_1_all"),
            InlineKeyboardButton("Search",        "adm_search"),
        ],
        [
            InlineKeyboardButton("Statistics",    "adm_stats"),
            InlineKeyboardButton("Broadcast",     "adm_bc"),
        ],
        [InlineKeyboardButton("Close",            "adm_close")],
    ])

    return text, kb


# ════════════════════════════════════════════════════════════
#  /users  ENTRY COMMAND
# ════════════════════════════════════════════════════════════

@bot.on_message(filters.command("users") & sudo_cmd)
async def admin_panel(_, message: Message) -> None:
    text, kb = await _panel_text_and_kb()
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


# ════════════════════════════════════════════════════════════
#  LIST BUILDER
# ════════════════════════════════════════════════════════════

async def build_list(page: int, filter_key: str = "all") -> Tuple[str, InlineKeyboardMarkup]:
    """
    Paginated user list with inline filter tabs.
    filter_key: "all" | "banned" | "warned"
    """
    q_map = {
        "banned": {"banned": True},
        "warned": {"warn_count": {"$gt": 0}},
    }
    query  = q_map.get(filter_key, {})
    data   = await users.collection.find(query).to_list(length=None)
    total  = len(data)
    pages  = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    page   = max(1, min(page, pages))
    subset = data[(page - 1) * USERS_PER_PAGE : page * USERS_PER_PAGE]

    filter_label = {"all": "ALL", "banned": "BANNED", "warned": "WARNED"}.get(filter_key, "ALL")

    text = (
        f"**USER LIST  {BULL}  {filter_label}**\n"
        f"`{DIV}`\n"
        f"_Page {page} of {pages}  {BULL}  {total:,} records_"
    )

    buttons = []
    for u in subset:
        name = u.get("name") or "Unknown"
        uid  = u["_id"]

        if u.get("banned"):
            tag = "  [BANNED]"
        elif u.get("warn_count", 0):
            tag = f"  [WARN {u['warn_count']}]"
        else:
            tag = ""

        buttons.append([InlineKeyboardButton(
            f"{name[:22]}{tag}",
            callback_data=f"adm_view_{uid}_{page}_{filter_key}",
        )])

    # Navigation row
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("« Prev", f"adm_list_{page-1}_{filter_key}"))
    if page < pages:
        nav.append(InlineKeyboardButton("Next »", f"adm_list_{page+1}_{filter_key}"))
    if nav:
        buttons.append(nav)

    # Filter tabs — active tab is wrapped in brackets
    def tab(label: str, key: str) -> InlineKeyboardButton:
        display = f"[ {label} ]" if key == filter_key else label
        return InlineKeyboardButton(display, f"adm_list_1_{key}")

    buttons.append([tab("All", "all"), tab("Banned", "banned"), tab("Warned", "warned")])
    buttons.append([InlineKeyboardButton("« Back", "adm_home")])

    return text, InlineKeyboardMarkup(buttons)


# ════════════════════════════════════════════════════════════
#  PROFILE BUILDER
# ════════════════════════════════════════════════════════════

async def build_profile(
    client,
    uid: int,
    page: int,
    filter_key: str = "all",
) -> Tuple[str, Optional[InlineKeyboardMarkup], Optional[str]]:

    user = await users.read_document(uid)
    if not user:
        return "User not found.", None, None

    warns    = user.get("warn_count", 0)
    spam     = user.get("rate_limit", 0)
    banned   = user.get("banned", False)
    name     = (user.get("name") or "Unknown")[:17]
    username = (user.get("username") or "—")
    joined   = fmt_dt(user.get("joined_at"))[:17]
    last_act = fmt_dt(user.get("last_active"))[:17]
    status   = "BANNED" if banned else "Active"

    text = (
        f"**USER PROFILE**\n"
        f"`{HDR}`\n"
        f"`  ID          {str(uid):>16}`\n"
        f"`  Name        {name:>16}`\n"
        f"`  Username    {'@'+username[:14]:>16}`\n"
        f"`  Status      {status:>16}`\n"
        f"`  Joined      {joined:>16}`\n"
        f"`  Last Seen   {last_act:>16}`\n"
        + (f"`  Banned At   {fmt_dt(user.get('banned_at'))[:16]:>16}`\n" if banned else "")
        + f"`{DIV}`\n"
        f"Warnings  `{warn_bar(warns)}`\n"
        f"Spam      `{spam_bar(spam)}`"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Warn",         f"adm_warn_{uid}_{page}_{filter_key}"),
            InlineKeyboardButton("Reset Warns",  f"adm_unwarn_{uid}_{page}_{filter_key}"),
        ],
        [
            InlineKeyboardButton("Ban",          f"adm_ban_{uid}_{page}_{filter_key}"),
            InlineKeyboardButton("Unban",        f"adm_unban_{uid}_{page}_{filter_key}"),
        ],
        [
            InlineKeyboardButton("+ Spam",       f"adm_spamup_{uid}_{page}_{filter_key}"),
            InlineKeyboardButton("- Spam",       f"adm_spamdown_{uid}_{page}_{filter_key}"),
            InlineKeyboardButton("Reset Spam",   f"adm_spamreset_{uid}_{page}_{filter_key}"),
        ],
        [
            InlineKeyboardButton("Send Message", f"adm_msg_{uid}"),
            InlineKeyboardButton("Refresh",      f"adm_view_{uid}_{page}_{filter_key}"),
        ],
        [InlineKeyboardButton("« Back", f"adm_list_{page}_{filter_key}")],
    ])

    # Profile photo (best-effort; never fatal)
    photo: Optional[str] = None
    try:
        photos = await client.get_profile_photos(uid, limit=1)
        if photos:
            photo = photos[0].file_id
    except Exception:
        pass

    return text, kb, photo


# ════════════════════════════════════════════════════════════
#  STATISTICS BUILDER
# ════════════════════════════════════════════════════════════

async def build_stats() -> str:
    total   = await users.collection.count_documents({})
    banned  = await users.collection.count_documents({"banned": True})
    warned  = await users.collection.count_documents({"warn_count": {"$gt": 0}})
    active  = total - banned
    new_24h = await users.collection.count_documents({
        "joined_at": {"$gte": datetime.now(tz=timezone.utc).timestamp() - 86_400}
    })
    pct_banned = f"{banned / total * 100:.1f}%" if total else "0.0%"
    pct_active = f"{active / total * 100:.1f}%" if total else "0.0%"

    return (
        f"**STATISTICS**\n"
        f"`{HDR}`\n"
        f"`  Total       {total:>8,}`\n"
        f"`  Active      {active:>8,}   ({pct_active})`\n"
        f"`  Banned      {banned:>8,}   ({pct_banned})`\n"
        f"`  Warned      {warned:>8,}`\n"
        f"`  New (24 h)  {new_24h:>8,}`\n"
        f"`{HDR}`"
    )


# ════════════════════════════════════════════════════════════
#  ACTION HANDLER
# ════════════════════════════════════════════════════════════

async def handle_action(client, action: str, uid: int) -> Tuple[str, bool]:
    """
    Execute a moderation action on a user.
    Returns (toast_text, show_alert).
    """
    user = await users.read_document(uid)
    if not user:
        return "User not found.", True

    update: dict = {}
    toast        = ""
    alert        = False

    if action == "warn":
        warns = user.get("warn_count", 0) + 1
        update["warn_count"] = warns
        await safe_send(client, uid,
            f"You have received a warning ({warns}/{AUTO_BAN_WARN}).")

        if warns >= AUTO_BAN_WARN:
            update["banned"]    = True
            update["banned_at"] = datetime.now(tz=timezone.utc).timestamp()
            await safe_send(client, uid,
                "You have been banned after reaching the warning limit.")
            toast = f"Auto-banned — {warns} warnings reached."
            alert = True
        else:
            toast = f"Warning issued.  {warns} / {AUTO_BAN_WARN}"

    elif action == "unwarn":
        prev = user.get("warn_count", 0)
        update["warn_count"] = 0
        toast = f"Warnings cleared.  Was: {prev}"

    elif action == "ban":
        if user.get("banned"):
            return "User is already banned.", False
        update["banned"]    = True
        update["banned_at"] = datetime.now(tz=timezone.utc).timestamp()
        await safe_send(client, uid, "You have been banned from this service.")
        toast = "User banned."

    elif action == "unban":
        if not user.get("banned"):
            return "User is not banned.", False
        update["banned"] = False
        update.pop("banned_at", None)
        await safe_send(client, uid, "Your ban has been lifted.")
        toast = "User unbanned."

    elif action == "spamup":
        spam = user.get("rate_limit", 0) + 1
        update["rate_limit"] = spam
        if spam >= AUTO_BAN_SPAM:
            update["banned"]    = True
            update["banned_at"] = datetime.now(tz=timezone.utc).timestamp()
            await safe_send(client, uid,
                "You have been banned for excessive spam.")
            toast = f"Spam auto-ban triggered at {spam} hits."
            alert = True
        else:
            toast = f"Spam count increased.  {spam} / {AUTO_BAN_SPAM}"

    elif action == "spamdown":
        prev = user.get("rate_limit", 0)
        update["rate_limit"] = max(0, prev - 1)
        toast = f"Spam count decreased.  {update['rate_limit']} / {AUTO_BAN_SPAM}"

    elif action == "spamreset":
        update["rate_limit"] = 0
        toast = "Spam count reset to 0."

    else:
        return f"Unknown action: {action}", True

    if update:
        await users.update_document(uid, update)
        log.info("admin action='%s' uid=%s delta=%s", action, uid, update)

    return toast, alert


# ════════════════════════════════════════════════════════════
#  CALLBACK ROUTER
# ════════════════════════════════════════════════════════════

@bot.on_callback_query(filters.regex(r"^adm_"))
async def callbacks(client, q: CallbackQuery) -> None:
    data = q.data

    # ── HOME ────────────────────────────────────────────────
    if data == "adm_home":
        text, kb = await _panel_text_and_kb()
        await edit_or_reply(q, text, kb)

    # ── CLOSE ───────────────────────────────────────────────
    elif data == "adm_close":
        try:
            await q.message.delete()
        except Exception:
            pass

    # ── LIST  adm_list_{page}_{filter} ──────────────────────
    elif data.startswith("adm_list_"):
        parts      = data.split("_")
        page       = int(parts[2]) if len(parts) > 2 else 1
        filter_key = parts[3]      if len(parts) > 3 else "all"
        text, kb   = await build_list(page, filter_key)
        await edit_or_reply(q, text, kb)

    # ── PROFILE  adm_view_{uid}_{page}_{filter} ─────────────
    elif data.startswith("adm_view_"):
        parts      = data.split("_")
        uid        = int(parts[2])
        page       = int(parts[3]) if len(parts) > 3 else 1
        filter_key = parts[4]      if len(parts) > 4 else "all"

        text, kb, photo = await build_profile(client, uid, page, filter_key)
        if kb is None:
            await cb_answer(q, text, alert=True)
            return

        if photo:
            try:
                await q.message.reply_photo(
                    photo, caption=text, reply_markup=kb,
                    parse_mode=ParseMode.MARKDOWN,
                )
                await q.message.delete()
                return
            except Exception:
                pass  # fall through to plain-text edit

        await edit_or_reply(q, text, kb)

    # ── MODERATION ACTIONS ──────────────────────────────────
    #   Pattern: adm_{action}_{uid}_{page}_{filter}
    elif re.match(r"^adm_(warn|unwarn|ban|unban|spamup|spamdown|spamreset)_", data):
        parts      = data.split("_")
        action     = parts[1]
        uid        = int(parts[2])
        page       = int(parts[3]) if len(parts) > 3 else 1
        filter_key = parts[4]      if len(parts) > 4 else "all"

        toast, alert_flag = await handle_action(client, action, uid)
        await cb_answer(q, toast, alert=alert_flag)

        text, kb, _ = await build_profile(client, uid, page, filter_key)
        if kb:
            await edit_or_reply(q, text, kb)

    # ── SEARCH PROMPT ───────────────────────────────────────
    elif data == "adm_search":
        await edit_or_reply(
            q,
            f"**SEARCH USER**\n"
            f"`{DIV}`\n"
            "_Reply with a name, username, or numeric user ID._",
            back_home_kb(),
        )

    # ── BROADCAST PROMPT ────────────────────────────────────
    elif data == "adm_bc":
        await edit_or_reply(
            q,
            f"**BROADCAST**\n"
            f"`{DIV}`\n"
            "_Reply with the message to send to all active users._\n\n"
            "_Note: Banned users are excluded automatically._",
            back_home_kb(),
        )

    # ── MESSAGE USER PROMPT  adm_msg_{uid} ──────────────────
    elif data.startswith("adm_msg_"):
        uid = int(data.split("_")[2])
        await edit_or_reply(
            q,
            f"**SEND MESSAGE**\n"
            f"`{DIV}`\n"
            f"_Reply with the message to deliver to user_ `{uid}`.",
            back_home_kb(),
        )

    # ── STATISTICS ──────────────────────────────────────────
    elif data == "adm_stats":
        text = await build_stats()
        kb   = InlineKeyboardMarkup([[
            InlineKeyboardButton("Refresh", "adm_stats"),
            InlineKeyboardButton("« Back",  "adm_home"),
        ]])
        await edit_or_reply(q, text, kb)

    else:
        await cb_answer(q, "Unknown action.", alert=True)


# ════════════════════════════════════════════════════════════
#  REPLY HANDLER  (search / broadcast / message-user)
# ════════════════════════════════════════════════════════════

@bot.on_message(filters.reply & sudo_cmd)
async def reply_handler(client, msg: Message) -> None:
    if not msg.reply_to_message:
        return

    base = msg.reply_to_message.text or msg.reply_to_message.caption or ""

    # ── SEARCH ──────────────────────────────────────────────
    if "SEARCH USER" in base:
        raw = (msg.text or "").strip().lstrip("@")
        if not raw:
            return await msg.reply("No query provided.")

        if raw.isdigit():
            user    = await users.read_document(int(raw))
            results = [user] if user else []
        else:
            results = await users.collection.find({
                "$or": [
                    {"name":     {"$regex": re.escape(raw), "$options": "i"}},
                    {"username": {"$regex": re.escape(raw), "$options": "i"}},
                ]
            }).to_list(length=MAX_SEARCH_HITS)

        if not results:
            return await msg.reply(
                f"**SEARCH USER**\n`{DIV}`\n_No records found for_ `{raw}`.",
                parse_mode=ParseMode.MARKDOWN,
            )

        if len(results) == 1:
            text, kb, photo = await build_profile(client, results[0]["_id"], 1)
            if photo:
                await msg.reply_photo(photo, caption=text, reply_markup=kb,
                                      parse_mode=ParseMode.MARKDOWN)
            else:
                await msg.reply(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        else:
            lines = [
                f"**SEARCH RESULTS**\n`{DIV}`\n"
                f"_{len(results)} records matched_ `{raw}`\n"
            ]
            for u in results:
                lines.append(f"{BULL} `{u['_id']}`  —  {u.get('name','Unknown')}")

            buttons = [[InlineKeyboardButton(
                f"{u.get('name','Unknown')[:24]}  ({u['_id']})",
                f"adm_view_{u['_id']}_1_all",
            )] for u in results]

            await msg.reply(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN,
            )

    # ── BROADCAST ───────────────────────────────────────────
    elif "BROADCAST" in base:
        all_users = await users.collection.find(
            {"banned": {"$ne": True}}
        ).to_list(length=None)

        total   = len(all_users)
        sent    = 0
        fail    = 0
        blocked = 0

        status_msg = await msg.reply(
            f"**BROADCAST**\n`{DIV}`\n_Sending to {total:,} users … 0% complete_",
            parse_mode=ParseMode.MARKDOWN,
        )

        for i, u in enumerate(all_users, 1):
            try:
                await msg.copy(u["_id"])
                sent += 1
            except (UserIsBlocked, InputUserDeactivated):
                blocked += 1
                fail    += 1
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await msg.copy(u["_id"])
                    sent += 1
                except Exception:
                    fail += 1
            except Exception:
                fail += 1

            if i % 20 == 0 or i == total:
                pct = int(i / total * 100)
                try:
                    await status_msg.edit_text(
                        f"**BROADCAST**\n`{DIV}`\n"
                        f"_Progress: {pct}%  {BULL}  Sent: {sent:,}  {BULL}  Failed: {fail:,}_",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass

            await asyncio.sleep(BROADCAST_DELAY)

        await status_msg.edit_text(
            f"**BROADCAST COMPLETE**\n"
            f"`{HDR}`\n"
            f"`  Total      {total:>8,}`\n"
            f"`  Sent       {sent:>8,}`\n"
            f"`  Failed     {fail:>8,}`\n"
            f"`  Blocked    {blocked:>8,}`\n"
            f"`{HDR}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── MESSAGE USER ────────────────────────────────────────
    elif "SEND MESSAGE" in base:
        match = re.search(r"\b(\d{5,})\b", base)
        if not match:
            return await msg.reply("Could not parse a user ID from the prompt.")

        uid = int(match.group(1))
        try:
            await msg.copy(uid)
            await msg.reply(
                f"**SEND MESSAGE**\n`{DIV}`\n_Message delivered to_ `{uid}`.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except (UserIsBlocked, InputUserDeactivated):
            await msg.reply(
                f"_User_ `{uid}` _has blocked the bot or is deactivated._",
                parse_mode=ParseMode.MARKDOWN,
            )
        except PeerIdInvalid:
            await msg.reply(
                f"_Invalid user ID:_ `{uid}`.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:
            log.error("reply_handler message-user error: %s", exc)
            await msg.reply(
                f"_Delivery failed:_ `{exc}`",
                parse_mode=ParseMode.MARKDOWN,
            )
