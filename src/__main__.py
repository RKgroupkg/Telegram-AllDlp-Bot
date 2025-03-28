#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from src import bot
from src.logging import LOGGER

LOGGER(__name__).info("client successfully initiated....")
if __name__ == "__main__":
    bot.run()
