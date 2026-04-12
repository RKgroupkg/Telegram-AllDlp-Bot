from src.version import (__license__, __pyro_version__, __python_version__,
                         __version__)

# Load images into memory once at startup
QUICKDL_BANNER = "https://raw.githubusercontent.com/RKgroupkg/Telegram-AllDlp-Bot/refs/heads/main/src/helpers/assets/QuickDlBanner.jpg"

QUICKDL_LOGO = "https://raw.githubusercontent.com/RKgroupkg/Telegram-AllDlp-Bot/refs/heads/main/src/helpers/assets/QuickDlLogo.jpg"

RKGROUP_LOGO = "https://raw.githubusercontent.com/RKgroupkg/Telegram-AllDlp-Bot/refs/heads/main/src/helpers/assets/RKgroupLogo.jpg"

BOT_NAME = "@Quick_dlbot"
DLP_TEXT = """

<b>━━━〔 Dlp Cmd Doc 〕━━━</b>

<b>/yt</b>  <i>
To download video, shots, or music from YouTube.  
◇  You can also directly send the link using @vid or directly from YouTube.  
◇  Select your format and quality for the video, music, or song and have it downloaded.
</i>
<b>/spotify</b><i>  
To download Spotify tracks or songs.  
◇  You can directly provide the Spotify link, and I’ll find a YouTube alternative with the same audio and download it for you.
</i>
<b>/insta</b>  
<i>To download Instagram reels, videos, public stories, images, or posters.  
◇  You can directly provide the link.  
◇  You can also use the inline feature for this.
</i>
<b>/dl</b>  
<i>To download any link (except yt.).  
◇  You can directly provide the link.  
◇  supports 2k+ sites.
 

"""
DEV_TEXT = """
━━━〔 Developer Commands 〕━━━

- /update
  ↳ Update the bot to the latest commit from the repository.

- /shell | /sh
  ↳ Execute terminal commands directly via the bot.

- /exec | /py
  ↳ Execute Python code via the bot with a built-in refresh button.

- /broadcast
  ↳ Broadcast a message to all bot users and groups.
"""

SUDO_TEXT = """
━━━〔 Sudo Commands 〕━━━

- /stats | /serverstats
  ↳ Get server resource stats (CPU, RAM, disk, etc).

- /dbstats
  ↳ Get MongoDB database statistics including collections and usage.

- /log | /logs
  ↳ Open the log management control panel.

- /inspect
  ↳ Inspect a message and return full details in JSON format.

- /catch
  ↳ Open the catch file manager to browse and manage temporary files.

- /cookie | /cookies <pastebinUrl>
  ↳ Import new cookies via a Base64-encoded Pastebin URL.

- /speedtest | /speed
  ↳ Run a speedtest on the server where the bot is hosted.
"""

USER_TEXT = """
━━━〔 User Commands 〕━━━

- /start | /help
  ↳ Start the bot or get the help menu.

- /ping | /alive
  ↳ Check Telegram API ping speed and bot uptime.

- /dl <url>
  ↳ Download media from a supported URL (auto-detects platform).

- /youtube | /yt | /ytdl <url>
  ↳ Download a YouTube video or audio by URL.

- /music | /search | /play <query>
  ↳ Search YouTube for music tracks and pick one to download.

- /ytstats
  ↳ Show YouTube downloader usage statistics.

- /clean_ytcache
  ↳ Clear the YouTube downloader cache manually.

- /spotify | /spt | /sptdlp | /dlmusic <url>
  ↳ Download a Spotify track by intercepting the Spotify link.

- /instagram | /insta | /igdl <url>
  ↳ Download Instagram reels, posts, or stories by URL.

- /ighelp
  ↳ Get detailed help about the Instagram downloader feature.

- /paste
  ↳ Paste text or images with interactive formatting options.

- /id
  ↳ Get detailed info about a user, message, chat, or forwarded content.
"""

ABOUT_CAPTION = f"""• Python version : {__python_version__}
• 𝙱𝚘𝚝 𝚟𝚎𝚛𝚜𝚒𝚘𝚗: {__version__}
• 𝚙𝚢𝚛𝚘𝚐𝚛𝚊𝚖  𝚟𝚎𝚛𝚜𝚒𝚘𝚗 : {__pyro_version__}
• 𝙻𝚒𝚌𝚎𝚗𝚜𝚎 : {__license__}
"""

START_ANIMATION = "https://images.app.goo.gl/hjN3cqtM43Bs95fJ6"

START_CAPTION = """
♔ **Step into a world of swift downloads**.\nfrom __Instagram__ to __Spotify__ to __Youtube__, I deliver with professional precision.
"""


COMMAND_CAPTION = """**𝙷𝚎𝚛𝚎 𝚊𝚛𝚎 𝚝𝚑𝚎 𝚕𝚒𝚜𝚝 𝚘𝚏 𝚌𝚘𝚖𝚖𝚊𝚗𝚍𝚜 𝚠𝚑𝚒𝚌𝚑 𝚢𝚘𝚞 𝚌𝚊𝚗 𝚞𝚜𝚎 𝚒𝚗 𝚋𝚘𝚝.\n**"""
