"""Constants for YouTube Watching integration."""

DOMAIN = "youtube_current_watching"

# Configuration
CONF_APPLE_TV = "apple_tv_entity_id"
CONF_COOKIES_PATH = "cookies_path"
CONF_TRACK_ALL = "track_all"  # 항상 추적 모드

# Default cookies path
DEFAULT_COOKIES_PATH = "/config/youtube_cookies.txt"

# Update interval
SCAN_INTERVAL_SECONDS = 30

# Sensor attributes
ATTR_CHANNEL = "channel"
ATTR_TITLE = "title"
ATTR_VIDEO_ID = "video_id"
ATTR_THUMBNAIL = "thumbnail"
ATTR_DURATION = "duration"
ATTR_URL = "url"

# Binary sensor
ATTR_COOKIES_VALID = "cookies_valid"

# YouTube app IDs for different platforms
YOUTUBE_APP_IDS = [
    "com.google.ios.youtube",           # Apple TV
    "com.google.android.youtube.tv",    # Android TV
    "com.google.android.youtube.tvunplugged",  # YouTube TV on Android
    "com.google.android.youtube",       # Android (generic)
    "com.google.android.apps.youtube.music",  # YouTube Music
    "com.google.android.youtube.googletv",  # Google TV
    "YouTube",                          # Some devices use simple names
    "youtube",                          # Lowercase variant
    "com.google.android.youtube.tvkids",  # YouTube Kids
]