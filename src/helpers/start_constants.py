# src/helpers/start_constants.py
from src.version import (__license__, __pyro_version__, __python_version__,
                         __version__)

QUICKDL_BANNER = "https://raw.githubusercontent.com/RKgroupkg/Telegram-AllDlp-Bot/refs/heads/main/src/helpers/assets/QuickDlBanner.jpg"
QUICKDL_LOGO   = "https://raw.githubusercontent.com/RKgroupkg/Telegram-AllDlp-Bot/refs/heads/main/src/helpers/assets/QuickDlLogo.jpg"
RKGROUP_LOGO   = "https://raw.githubusercontent.com/RKgroupkg/Telegram-AllDlp-Bot/refs/heads/main/src/helpers/assets/RKgroupLogo.jpg"

BOT_NAME = "@Quick_dlbot"

# ──────────────────────────────────────────────
#  START / WELCOME
# ──────────────────────────────────────────────
START_CAPTION = """
♔ **Welcome to Quick DL**

Swift, silent, precise — your all-in-one media downloader.

**∷ Supported Platforms**
┣ ◈ __YouTube__  — videos, shorts & audio
┣ ◈ __Spotify__  — tracks via YouTube mirror
┣ ◈ __Instagram__ — reels, posts & stories
┗ ◈ __Universal__ — 2000+ sites via `/dl`

✦ Just send a link — or tap **⌤ Commands** to explore.
"""

# ──────────────────────────────────────────────
#  COMMANDS MENU
# ──────────────────────────────────────────────
COMMAND_CAPTION = """
**━━━〔 Command Categories 〕━━━**

Select a category below to view its commands.

┣ ⚜ **DLP**  — Downloader commands
┣ ⚜ **Users**  — General commands
┣ ⚜ **Sudo**  — Admin tools _(restricted)_
┗ ⚜ **Developer**  — Dev tools _(restricted)_

✦ _Tip: You can send any supported URL directly — no command needed._
"""

# ──────────────────────────────────────────────
#  DLP COMMANDS
# ──────────────────────────────────────────────
DLP_TEXT = """
<b>━━━〔 Dlp Commands 〕━━━</b>

<b>/yt</b> <code>&lt;url / query&gt;</code>
<i>◇ Download YouTube videos, Shorts, or audio.
◇ Choose format and quality interactively.
◇ Also works inline via @Quick_dlbot.</i>

<b>/spotify</b> <code>&lt;url&gt;</code>
<i>◇ Download Spotify tracks.
◇ Automatically mirrors the best YouTube audio.</i>

<b>/insta</b> <code>&lt;url&gt;</code>
<i>◇ Download Instagram reels, posts, stories, or images.
◇ Inline support available.</i>

<b>/dl</b> <code>&lt;url&gt;</code>
<i>◇ Universal downloader — supports 2000+ websites.
◇ Use this for any platform not listed above.</i>

━━━━━━━━━━━━━━━━
✦ <i>For YouTube, select video quality and format before downloading.</i>
"""

# ──────────────────────────────────────────────
#  USER COMMANDS
# ──────────────────────────────────────────────
USER_TEXT = """
━━━〔 User Commands 〕━━━

✦ General
┣ /start · /help
  ↳ Show the welcome menu.
┗ /ping · /alive
  ↳ Check bot latency and uptime.

✦ Downloaders
┣ /dl <url>
  ↳ Universal link downloader (2000+ sites).
┣ /yt <url>
  ↳ YouTube video or audio download.
┣ /spotify <url>
  ↳ Spotify track download.
┗ /insta <url>
  ↳ Instagram reels, posts and stories.

✦ YouTube Extras
┣ /music · /search · /play <query>
  ↳ Search YouTube and pick a track to download.
┣ /ytstats
  ↳ Show YouTube downloader usage statistics.
┗ /clean_ytcache
  ↳ Clear the YouTube downloader cache manually.

✦ Utilities
┣ /paste
  ↳ Paste text or images with formatting options.
┣ /id
  ↳ Get info about a user, chat, or forwarded message.
┗ /ighelp
  ↳ Detailed Instagram downloader guide.
"""

# ──────────────────────────────────────────────
#  SUDO COMMANDS
# ──────────────────────────────────────────────
SUDO_TEXT = """
━━━〔 Sudo Commands 〕━━━

✦ Management
┣ /users · /serverstats
  ↳ Control panel — view users, stats and admin actions.
┗ /stats
  ↳ Live server resource stats (CPU, RAM, disk).

✦ Database
┗ /dbstats
  ↳ MongoDB statistics — collections and usage.

✦ Logs & Files
┣ /log · /logs
  ↳ Open the log management panel.
┣ /catch
  ↳ Browse and manage temporary cached files.
┗ /inspect
  ↳ Dump full message details as JSON.

✦ Network & Tools
┣ /speedtest · /speed
  ↳ Run a speedtest on the host server.
┗ /cookie <pastebinUrl>
  ↳ Import cookies via a Base64-encoded Pastebin URL.
"""

# ──────────────────────────────────────────────
#  DEVELOPER COMMANDS
# ──────────────────────────────────────────────
DEV_TEXT = """
━━━〔 Developer Commands 〕━━━

- /update
  ↳ Pull the latest commit and restart the bot.

- /shell · /sh <cmd>
  ↳ Execute a terminal command directly via the bot.

- /exec · /py <code>
  ↳ Run Python code with a built-in refresh button.

- /broadcast
  ↳ Send a message to all users and groups.

- /render
  ↳ Toggle or control the render feature.
"""

# ──────────────────────────────────────────────
#  ABOUT
# ──────────────────────────────────────────────
ABOUT_CAPTION = f"""
━━━〔 About Quick DL 〕━━━

◈ Swift, open-source media downloader for Telegram.
◈ Built for reliability, speed and ease of use.

✦ Runtime
┣ Python      {__python_version__}
┣ Pyrogram    {__pyro_version__}
┗ Bot version {__version__}

✦ Legal
┣ License : {__license__}
┣ Privacy Policy  — see below
┗ Code of Conduct — see below

∴ Crafted with precision by RKgroup
"""

# ──────────────────────────────────────────────
#  MISC
# ──────────────────────────────────────────────
START_ANIMATION = "https://images.app.goo.gl/hjN3cqtM43Bs95fJ6"
