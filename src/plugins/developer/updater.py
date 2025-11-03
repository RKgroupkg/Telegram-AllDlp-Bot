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

@bot.on_message(filters.command("update") & dev_cmd)
async def update(_, message: Message):
    """Pull latest commits from GitHub and redeploy."""
    msg = await message.reply_text("🔄 Pulling latest commits from GitHub...", quote=True)
    out, err, code = await run_cmd(["git", "pull"])

    if code != 0:
        await msg.edit(f"❌ Git update failed:\n`{err or out}`")
        log.error(f"Git pull failed: {err or out}")
        return

    updated_lines = "\n".join(line for line in out.splitlines()[:6])
    await msg.edit(f"✅ Bot updated successfully:\n```\n{updated_lines}\n```\nRestarting now...")
    log.info(f"Bot updated successfully at {datetime.now().isoformat()}")
    restart_bot()


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
