#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

import sys
import logging as log
import time
import uvloop
from pyrogram import Client
from telegraph.aio import Telegraph
from asyncio import get_event_loop, new_event_loop, set_event_loop

from src import config
from src.logging import LOGGER
from src.database.MongoDb import check_mongo_uri

from keep_alive_ping import KeepAliveService

# for render and koyeb comment it ou uf you dont need it 

service = KeepAliveService(
    log_level = log.ERROR, # no need for info 
    ping_interval=60  # Ping every 1 minutes
)


uvloop.install()
LOGGER(__name__).info("Starting Quick DL....")
BotStartTime = time.time()


if sys.version_info[0] < 3 or sys.version_info[1] < 7:
    LOGGER(__name__).critical(
        """
=============================================================
You MUST need to be on python 3.7 or above, shutting down the bot...
=============================================================
"""
    )
    sys.exit(1)


LOGGER(__name__).info("setting up event loop....")
try:
    loop = get_event_loop()
except RuntimeError:
    set_event_loop(new_event_loop())
    loop = get_event_loop()

LOGGER(__name__).info("setting up pinger for keep alive ....")

try:
  # service.start()
  pass
except Exception as e:
  raise e
# https://patorjk.com/software/taag/#p=display&f=Graffiti&t=Type%20Something%20


LOGGER(__name__).info("checking MongoDb URI....")
loop.run_until_complete(check_mongo_uri(config.MONGO_URI))

LOGGER(__name__).info("creating telegraph session....")
telegraph = Telegraph(domain="graph.org")

LOGGER(__name__).info("initiating the client....")
plugins = dict(root="src/plugins")  # https://docs.pyrogram.org/topics/smart-plugins
bot = Client(
    "Quick Dl",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    plugins=plugins,
)
