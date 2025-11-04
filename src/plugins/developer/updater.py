#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.

import asyncio
import json
import os
import sys
import urllib.request
from datetime import datetime

from pyrogram import filters
from pyrogram.types import Message
from src import bot
from src.helpers.filters import dev_cmd
from src.logging import LOGGER

from src.config import GITHUB_REPO

log = LOGGER(__name__)
# ----------------------------- Utility helpers ----------------------------- #

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


# ----------------------------- /update command ----------------------------- #

import re
from pyrogram.enums import ParseMode

def escape_markdown(text: str) -> str:
    """
    Escape text for Telegram MarkdownV2.
    Telegram’s MarkdownV2 treats many punctuation marks as control symbols,
    so this replaces them with escaped versions using backslashes.
    """
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!\\"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", str(text))

@bot.on_message(filters.command("update") & dev_cmd)
async def update(_, message: Message):
    """
    Check for new commits in the GitHub repo. 
    If available, pull and restart. 
    If not, check outdated packages and report.
    """

    msg = await message.reply_text("🔍 Checking for new commits on GitHub...", quote=True)
    
    # Step 1: Determine the current local commit hash
    out, err, code = await run_cmd(["git", "rev-parse", "HEAD"])
    if code != 0:
        await msg.edit(
            f"⚠️ Failed to read local commit:\n`{escape_markdown(err or out)}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        log.error(f"Failed to get local commit hash: {err or out}")
        return
    local_commit = out.strip()

    # Step 2: Get latest remote commit from GitHub
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
    remote_data = safe_fetch_json(api_url)
    if not remote_data:
        await msg.edit("⚠️ Could not fetch latest commit info from GitHub.", parse_mode=None)
        return

    remote_commit = remote_data.get("sha", "")
    commit_msg = remote_data.get("commit", {}).get("message", "")
    commit_url = remote_data.get("html_url", f"https://github.com/{GITHUB_REPO}/commits")

    # Step 3: Compare
    if local_commit != remote_commit:
        log.info(f"New commit found: {remote_commit[:7]} — pulling updates.")
        await msg.edit(
            f"🪄 **New commit available!**\n"
            f"• Commit: `{escape_markdown(remote_commit[:7])}`\n"
            f"• Message: _{escape_markdown(commit_msg)}_\n"
            f"• [View on GitHub]({commit_url})\n\n"
            f"⬇️ Pulling changes and restarting...",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        out, err, code = await run_cmd(["git", "pull"])
        if code != 0:
            await msg.edit(
                f"❌ Git pull failed:\n`{escape_markdown(err or out)}`",
                parse_mode=ParseMode.MARKDOWN,
            )
            log.error(f"Git pull failed: {err or out}")
            return

        await msg.edit("✅ Bot updated successfully. Restarting...", parse_mode=None)
        log.info(f"Pulled latest commit {remote_commit[:7]} successfully.")
        restart_bot()
        return

    # Step 4: If no new commits, check outdated packages
    await msg.edit("ℹ️ No new commits. Checking dependencies for updates...", parse_mode=None)
    out, err, code = await run_cmd(
        [sys.executable, "-m", "pip", "list", "--outdated", "--format", "json"]
    )

    if code != 0:
        await msg.edit(
            f"⚠️ Failed to check packages:\n`{escape_markdown(err or out)}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        log.error(f"pip list failed: {err or out}")
        return

    try:
        outdated = json.loads(out)
    except Exception as e:
        await msg.edit(f"⚠️ Could not parse pip output: {escape_markdown(e)}", parse_mode=None)
        return

    if not outdated:
        await msg.edit(
            f"✅ All dependencies are up-to-date!\n"
            f"• No new commits in repo.\n"
            f"• Local commit: `{escape_markdown(local_commit[:7])}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        log.info("All dependencies are up-to-date.")
        return

    # Step 5: Show outdated dependencies in a nice summary
    text_lines = ["📦 **Outdated Packages Detected:**"]
    for pkg in outdated[:30]:  # limit output
        text_lines.append(
            f"• `{escape_markdown(pkg['name'])}`: "
            f"{escape_markdown(pkg['version'])} → {escape_markdown(pkg['latest_version'])}"
        )

    await msg.edit("\n".join(text_lines), parse_mode=ParseMode.MARKDOWN)
    log.info(f"Outdated dependencies found: {[p['name'] for p in outdated]}")
# ----------------------------- /restart command ----------------------------- #

@bot.on_message(filters.command("restart") & dev_cmd)
async def restart(_, message: Message):
    """Manually restart the bot."""
    log.info("Manual restart triggered by developer.")
    await message.reply_text("♻️ Restarting bot...", quote=True)
    restart_bot()


# ----------------------------- /updatedlp command ----------------------------- #

@bot.on_message(filters.command("updatedlp") & dev_cmd)
async def update_dlp(_, message: Message):
    """Smart yt_dlp updater — checks GitHub, compares, updates, logs, and restarts if needed."""
    msg = await message.reply_text("🔍 Checking current yt_dlp version...", quote=True)

    # Step 1: Get current version
    out, err, code = await run_cmd([sys.executable, "-m", "yt_dlp", "--version"])
    if code != 0:
        await msg.edit(f"⚠️ Could not detect yt_dlp version:\n`{err or out}`")
        log.error(f"Failed to detect yt_dlp version: {err or out}")
        return
    current_version = out.strip()

    # Step 2: Get latest release info
    release = safe_fetch_json("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest")
    if not release:
        await msg.edit("⚠️ Could not fetch yt_dlp release info from GitHub.")
        return

    latest_version = release.get("tag_name", "").lstrip("v")
    release_url = release.get("html_url", "https://github.com/yt-dlp/yt-dlp/releases")
    changelog = release.get("body", "No changelog found.")[:700]  # truncate for Telegram

    # Step 3: Compare semantic versions
    def normalize(v: str):
        return [int(x) if x.isdigit() else x for x in v.replace("-", ".").split(".")]
    up_to_date = normalize(current_version) >= normalize(latest_version)

    if up_to_date:
        await msg.edit(
            f"✅ yt_dlp is already up-to-date!\n\n"
            f"• **Current version:** `{current_version}`\n"
            f"• **GitHub Release:** [yt-dlp {latest_version}]({release_url})\n\n"
            f"📝 **Changelog:**\n```\n{changelog}\n```",
            disable_web_page_preview=True,
        )
        log.info(f"yt_dlp already at latest version {current_version}")
        return

    # Step 4: Update yt_dlp via pip
    await msg.edit(
        f"⬆️ Updating yt_dlp from `{current_version}` → `{latest_version}`...\n"
        f"This may take up to a minute."
    )
    out, err, code = await run_cmd([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"])

    if code != 0:
        await msg.edit(f"❌ Update failed:\n`{err or out}`")
        log.error(f"yt_dlp update failed: {err or out}")
        return

    # Step 5: Verify update
    new_out, _, _ = await run_cmd([sys.executable, "-m", "yt_dlp", "--version"])
    new_version = new_out.strip()

    await msg.edit(
        f"✅ **yt_dlp successfully updated!**\n\n"
        f"• **Previous:** `{current_version}`\n"
        f"• **Now:** `{new_version}`\n"
        f"• **Release:** [yt-dlp {latest_version}]({release_url})\n\n"
        f"🧠 **Changelog:**\n```\n{changelog}\n```\n"
        f"🔁 Restarting bot to apply changes...",
        disable_web_page_preview=True,
    )

    log.info(f"yt_dlp updated from {current_version} → {new_version}")
    restart_bot()
