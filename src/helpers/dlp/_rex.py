YT_LINK_REGEX = r"(?:https?:\/\/)?(?:www\.|m\.|music\.)?" + \
                r"(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|playlist\?(?:.*&)?list=|" + \
                r"embed\/|v\/|channel\/|user\/|" + \
                r"attribution_link\?(?:.*&)?u=\/watch\?(?:.*&)?v=)|" + \
                r"youtu\.be\/|youtube\.com\/clip\/|youtube\.com\/live\/)([a-zA-Z0-9_-]{11}|" + \
                r"[a-zA-Z0-9_-]{12,}(?=&|\?|$))"
# Regex patterns for Spotify links
SPOTIFY_TRACK_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/track/([a-zA-Z0-9]+)"
SPOTIFY_ALBUM_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/album/([a-zA-Z0-9]+)"
SPOTIFY_PLAYLIST_REGEX = r"(?:https?://)?(?:www\.)?open\.spotify\.com/playlist/([a-zA-Z0-9]+)"
INSTAGRAM_URL_PATTERN = r"https?://(?:www\.)?instagram\.com/(?:share/)?(?:p|reel|tv)/([a-zA-Z0-9_-]+)(?:/[a-zA-Z0-9_-]+)?"
# Simple regex pattern to find URLs starting with https://
URL_REGEX = r"https://\S+"  

# List all regex patterns you want to check
LINK_REGEX_PATTERNS = [
    YT_LINK_REGEX,
    SPOTIFY_TRACK_REGEX,
    SPOTIFY_ALBUM_REGEX,
    SPOTIFY_PLAYLIST_REGEX,
    INSTAGRAM_URL_PATTERN,
]
