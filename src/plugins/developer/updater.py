# File: src/plugins/developer/updater.py
#  Copyright (c) 2025 Rkgroup.
#  Quick Dl unified updater module

import asyncio
import json
import os
import sys
import urllib.request
import re
from datetime import datetime
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ParseMode

from src import bot
from src.helpers.filters import dev_cmd
from src.logging import LOGGER
from src.config import GITHUB_REPO

log = LOGGER(__name__)

# --------------------------------------------------------------------------- #
#                               Utility Helpers                               #
# --------------------------------------------------------------------------- #

async def run_cmd(cmd: list[str]) -> tuple[str, str, int]:
    """Run a shell command asynchronously and capture output."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode().strip(), stderr.decode().strip(), proc.returncode


def safe_fetch_json(url: str) -> dict | None:
    """Fetch JSON data from a URL with simple error handling."""
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        log.error(f"Failed to fetch JSON from {url}: {e}")
        return None


def restart_bot():
    """Restart the bot cleanly using the same interpreter."""
    log.info("Restarting bot via os.execl()")
    os.execl(sys.executable, sys.executable, "-m", "src")


def escape_markdown(text: str) -> str:
    """Escape text for Telegram MarkdownV2."""
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!\\"  # Telegram MarkdownV2 reserved chars
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", str(text))


# --------------------------------------------------------------------------- #
#                           Developer Control Center                          #
# --------------------------------------------------------------------------- #

@bot.on_message(filters.command("update") & dev_cmd)
async def unified_update(_, message: Message):
    """Main developer update menu."""
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("1. Update Bot (GitHub)", callback_data="upd_git")],
            [InlineKeyboardButton("2. Update yt-dlp", callback_data="upd_dlp")],
            [InlineKeyboardButton("3. Check Dependencies", callback_data="upd_deps")],
            [InlineKeyboardButton("4. Run Diagnostics", callback_data="upd_diag")],
            [InlineKeyboardButton("5. Restart Bot", callback_data="upd_restart")],
            [InlineKeyboardButton("Close", callback_data="upd_close")],
        ]
    )

    await message.reply_text(
        "**[ Developer Control Center ]**\n\n"
        "Select an operation below:\n"
        "──────────────────────────────\n"
        "  [1] Update bot from GitHub\n"
        "  [2] Update yt-dlp module\n"
        "  [3] Check for outdated dependencies\n"
        "  [4] Run system diagnostics\n"
        "  [5] Restart the bot\n"
        "──────────────────────────────",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )


# --------------------------------------------------------------------------- #
#                              GitHub Updater                                 #
# --------------------------------------------------------------------------- #

@bot.on_callback_query(filters.regex("^upd_git$"))
async def cb_update_git(_, query: CallbackQuery):
    msg = await query.message.edit_text("› Checking for new commits on GitHub...")
    out, err, code = await run_cmd(["git", "rev-parse", "HEAD"])
    if code != 0:
        await msg.edit(f"✗ Failed to read local commit:\n`{escape_markdown(err or out)}`",
                       parse_mode=ParseMode.MARKDOWN)
        return

    local_commit = out.strip()
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
    remote_data = safe_fetch_json(api_url)

    if not remote_data:
        return await msg.edit("✗ Could not fetch latest commit info from GitHub.")

    remote_commit = remote_data.get("sha", "")
    commit_msg = remote_data.get("commit", {}).get("message", "")
    commit_url = remote_data.get("html_url", f"https://github.com/{GITHUB_REPO}/commits")

    if local_commit == remote_commit:
        await msg.edit(
            f"✓ Already up-to-date.\n\n"
            f"• Current commit: `{escape_markdown(local_commit[:7])}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await msg.edit(
        f"[ New commit detected ]\n"
        f"──────────────────────────────\n"
        f"Commit: `{escape_markdown(remote_commit[:7])}`\n"
        f"Message: _{escape_markdown(commit_msg)}_\n"
        f"──────────────────────────────\n"
        f"Pulling updates...",
        disable_web_page_preview=True,
        parse_mode=ParseMode.MARKDOWN,
    )

    out, err, code = await run_cmd(["git", "pull"])
    if code != 0:
        await msg.edit(f"✗ Git pull failed:\n`{escape_markdown(err or out)}`", parse_mode=ParseMode.MARKDOWN)
        return

    await msg.edit("✓ Update successful.\nRestarting bot...")
    restart_bot()


# --------------------------------------------------------------------------- #
#                            Dependency Checker                               #
# --------------------------------------------------------------------------- #

@bot.on_callback_query(filters.regex("^upd_deps$"))
async def cb_update_deps(_, query: CallbackQuery):
    msg = await query.message.edit_text("› Checking Python dependencies...")
    out, err, code = await run_cmd([sys.executable, "-m", "pip", "list", "--outdated", "--format", "json"])
    if code != 0:
        return await msg.edit(f"✗ Failed to check packages:\n`{escape_markdown(err or out)}`",
                              parse_mode=ParseMode.MARKDOWN)

    outdated = json.loads(out or "[]")
    if not outdated:
        return await msg.edit("✓ All dependencies are up-to-date.")

    text_lines = ["[ Outdated Dependencies ]", "──────────────────────────────"]
    for i, pkg in enumerate(outdated[:25], 1):
        text_lines.append(
            f"{i:02d}. {escape_markdown(pkg['name'])}: "
            f"{escape_markdown(pkg['version'])} → {escape_markdown(pkg['latest_version'])}"
        )

    await msg.edit("\n".join(text_lines), parse_mode=ParseMode.MARKDOWN)


# --------------------------------------------------------------------------- #
#                              yt-dlp Updater                                 #
# --------------------------------------------------------------------------- #

@bot.on_callback_query(filters.regex("^upd_dlp$"))
async def cb_update_dlp(_, query: CallbackQuery):
    msg = await query.message.edit_text("› Checking yt-dlp version...")
    out, err, code = await run_cmd([sys.executable, "-m", "yt_dlp", "--version"])
    if code != 0:
        return await msg.edit(f"✗ Could not detect yt_dlp version:\n`{escape_markdown(err or out)}`",
                              parse_mode=ParseMode.MARKDOWN)

    current_version = out.strip()
    release = safe_fetch_json("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest")
    if not release:
        return await msg.edit("✗ Could not fetch release info from GitHub.")

    latest_version = release.get("tag_name", "").lstrip("v")
    release_url = release.get("html_url", "https://github.com/yt-dlp/yt-dlp/releases")

    def normalize(v: str):
        return [int(x) if x.isdigit() else x for x in v.replace("-", ".").split(".")]

    if normalize(current_version) >= normalize(latest_version):
        return await msg.edit(
            f"✓ yt-dlp is up-to-date.\nVersion: `{current_version}`\n\n<{release_url}>",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    await msg.edit(f"› Updating yt-dlp {current_version} → {latest_version}...")
    out, err, code = await run_cmd([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])

    if code != 0:
        return await msg.edit(f"✗ Update failed:\n`{escape_markdown(err or out)}`", parse_mode=ParseMode.MARKDOWN)

    await msg.edit(f"✓ yt-dlp updated successfully to {latest_version}.\nRestarting bot...")
    restart_bot()


# --------------------------------------------------------------------------- #
#                              Diagnostics Tool                               #
# --------------------------------------------------------------------------- #

@bot.on_callback_query(filters.regex("^upd_diag$"))
async def cb_diag(_, query: CallbackQuery):
    msg = await query.message.edit_text("› Running diagnostics, please wait...")
    report = ["[ Diagnostics Report ]", "──────────────────────────────"]

    # [1] Internet connectivity
    try:
        with urllib.request.urlopen("https://www.google.com", timeout=5) as r:
            if r.status == 200:
                report.append("[1] Internet connectivity ........ OK")
            else:
                report.append(f"[1] Internet connectivity ........ HTTP {r.status}")
    except Exception as e:
        report.append(f"[1] Internet connectivity ........ FAIL ({escape_markdown(str(e))})")

    # [2] yt_dlp version
    out, err, code = await run_cmd([sys.executable, "-m", "yt_dlp", "--version"])
    if code == 0:
        ytdlp_version = out.strip()
        report.append(f"[2] yt-dlp version ................ {escape_markdown(ytdlp_version)}")
    else:
        report.append(f"[2] yt-dlp version ................ FAIL ({escape_markdown(err or out)})")
        return await msg.edit("\n".join(report), parse_mode=ParseMode.MARKDOWN)

    # [3] yt_dlp YouTube extraction test
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    out, err, code = await run_cmd([sys.executable, "-m", "yt_dlp", "-j", test_url])
    if code == 0:
        try:
            info = json.loads(out)
            title = info.get("title", "Unknown Title")
            uploader = info.get("uploader", "Unknown")
            duration = info.get("duration", "?")
            report.append(f"[3] YouTube extraction ........... OK")
            report.append(f"    Title: {escape_markdown(title)}")
            report.append(f"    Uploader: {escape_markdown(uploader)}")
            report.append(f"    Duration: {duration}s")
        except Exception as e:
            report.append(f"[3] YouTube extraction ........... PARSE ERROR ({escape_markdown(str(e))})")
    else:
        err_msg = err or out
        if "429" in err_msg or "Sign in required" in err_msg:
            report.append("[3] YouTube extraction ........... BLOCKED (Rate limit or sign-in required)")
        elif "blocked" in err_msg.lower():
            report.append("[3] YouTube extraction ........... BLOCKED (Access restricted)")
        else:
            report.append(f"[3] YouTube extraction ........... FAIL ({escape_markdown(err_msg[:100])})")

    # [4] System Info
    out, _, _ = await run_cmd(["python3", "--version"])
    pyver = out or sys.version
    report.append(f"[4] Python version ................ {escape_markdown(pyver.strip())}")
    report.append(f"[5] Platform ...................... {escape_markdown(sys.platform)}")

    await msg.edit("\n".join(report), parse_mode=ParseMode.MARKDOWN)


# --------------------------------------------------------------------------- #
#                            Restart & Close Handlers                         #
# --------------------------------------------------------------------------- #

@bot.on_callback_query(filters.regex("^upd_restart$"))
async def cb_restart(_, query: CallbackQuery):
    await query.message.edit_text("› Restarting bot...")
    restart_bot()


@bot.on_callback_query(filters.regex("^upd_close$"))
async def cb_close(_, query: CallbackQuery):
    await query.message.delete()
