import json
import os
from os import getenv
from pathlib import Path
from dotenv import load_dotenv
from TelegramBot.logging import LOGGER

logger = LOGGER(__name__)

# Check for .env or config.env files
env_files = ["config.env", ".env"]
env_loaded = False

for env_file in env_files:
    if Path(env_file).exists():
        logger.info(f"Loading environment from {env_file}")
        load_dotenv(env_file)
        env_loaded = True
        break

if not env_loaded:
    logger.info("No .env file found, using system environment variables")

# Helper function to handle both direct env vars and .env format
def parse_json_env(key, default=None):
    value = getenv(key, "")
    logger.debug(f"Raw value for {key}: {repr(value)}")  # Show exact string with quotes
    
    if not value:
        logger.debug(f"No value found for {key}, using default")
        return default if default is not None else []
    
    # Clean up the value
    value = value.strip()
    
    # Check if it looks like JSON
    if (value.startswith('[') and value.endswith(']')) or \
       (value.startswith('{') and value.endswith('}')):
        try:
            parsed = json.loads(value)
            logger.debug(f"Successfully parsed {key}: {parsed}")
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {key}: {e}")
            logger.error(f"Problematic value: {repr(value)}")
            return default if default is not None else []
    
    # Fallback for non-JSON values
    try:
        return [int(value)]  # For single integer values
    except ValueError:
        return [value]  # Return as single string item
    
    
# Load configuration
RAPID_API_KEYS = parse_json_env("RAPID_API_KEYS")

API_ID = int(getenv("API_ID", 0))
API_HASH = getenv("API_HASH", "")
BOT_TOKEN = getenv("BOT_TOKEN", "")

# YT config
COOKIE_ROTATION_COOLDOWN :int = int(getenv("COOKIE_ROTATION_COOLDOWN", "600"))
DEFAULT_COOKIES_DIR : str = getenv("DEFAULT_COOKIES_DIR", "./cookies")
YT_PROGRESS_UPDATE_INTERVAL : int = int(getenv("YT_PROGRESS_UPDATE_INTERVAL", "5"))
YT_DOWNLOAD_PATH : str= getenv("YT_DOWNLOAD_PATH", "./tmp")
MAX_VIDEO_LENGTH_MINUTES : int = int(getenv("MAX_VIDEO_LENGTH_MINUTES","15"))

SPOTIFY_CLIENT_ID : str = getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET : str = getenv("SPOTIFY_CLIENT_SECRET", "")




# Helper function to handle both direct env vars and .env format
def parse_json_env(key, default=None):
    value = getenv(key, "")
    if not value:
        return default if default is not None else []
    
    # Clean up the value (remove extra spaces, etc.)
    value = value.strip()
    
    # Check if it's already a valid JSON string
    if (value.startswith('[') and value.endswith(']')) or \
       (value.startswith('{') and value.endswith('}')):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    
    # Try to interpret as a single value
    try:
        # For a single integer
        return [int(value)]
    except ValueError:
        # If not an integer, return as a single string item
        return [value]

# Handle owner and sudo users
try:
    OWNER_USERID = parse_json_env("OWNER_USERID", [])
    SUDO_USERID = OWNER_USERID.copy()
except Exception as error:
    logger.error(f"Failed to parse OWNER_USERID: {error}")
    OWNER_USERID = []
    SUDO_USERID = []

try:
    sudo_users = parse_json_env("SUDO_USERID", [])
    if sudo_users:
        SUDO_USERID += sudo_users
        logger.info("Added sudo user(s)")
except Exception as error:
    logger.info("No sudo user(s) mentioned in config.")

# Ensure unique user IDs
SUDO_USERID = list(set(SUDO_USERID))
MONGO_URI = getenv("MONGO_URI", "")

# Validate essential configuration
if not API_ID or not API_HASH or not BOT_TOKEN:
    logger.critical("Missing essential configuration (API_ID, API_HASH, or BOT_TOKEN)")

if not OWNER_USERID:
    logger.warning("No owner user IDs specified")

if not MONGO_URI:
    logger.warning("MONGO_URI not specified, some features may be unavailable")