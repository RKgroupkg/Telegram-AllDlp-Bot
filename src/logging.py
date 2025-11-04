#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Log file path
LOG_FILE = Path("logs.txt")

# Configure logging
def setup_logging() -> None:
    """
    Configure global logging with console + rotating file handlers.
    """
    log_format = "[%(asctime)s - %(levelname)s] - %(name)s - %(message)s"
    date_format = "%d-%b-%y %H:%M:%S"

    handlers = [
        RotatingFileHandler(
            LOG_FILE,
            mode="a",                # Append instead of overwriting
            maxBytes=5_000_000,      # Rotate after ~5MB
            backupCount=3,           # Keep 3 backups
            encoding="utf-8"         # Avoid encoding issues
        ),
        logging.StreamHandler()
    ]

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True                 # Ensures reconfiguration if called twice
    )

    # Suppress noisy third-party loggers
    logging.getLogger("pyrogram").setLevel(logging.ERROR)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("keep-alive-ping").setLevel(logging.WARNING)
    logging.getLogger("werkzeug'").setLevel(logging.WARNING)

def LOGGER(name: str) -> logging.Logger:
    """
    Get a logger for a given module.
    Example:
        logger = LOGGER(__name__)
        logger.info("Message")
    """
    return logging.getLogger(name)


# Automatically configure logging when imported
setup_logging()
