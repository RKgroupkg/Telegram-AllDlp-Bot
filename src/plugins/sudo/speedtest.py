from speedtest import Speedtest

from pyrogram import filters
from pyrogram.types import Message

from src import bot
from src.logging import LOGGER
from src.helpers.filters import sudo_cmd
from src.helpers.functions import get_readable_bytes
from src.helpers.decorators import run_sync_in_thread


@run_sync_in_thread
def speedtestcli():
    test = Speedtest()
    test.get_best_server()
    test.download()
    test.upload()
    test.results.share()
    return test.results.dict()


@bot.on_message(filters.command(["speedtest", "speed"]) & sudo_cmd)
async def speedtest(_, message: Message):
    """Give speedtest of the server where bot is running."""

    speed = await message.reply("♢ Running speedtest....", quote=True)
    LOGGER(__name__).info("Running speedtest....")
    result = await speedtestcli()

    speed_string = f"""
♚ **Upload:** __{get_readable_bytes(result["upload"] / 8)}/s__
♜ **Download**: __{get_readable_bytes(result["download"] / 8)}/s__
○ **Ping:** __{result["ping"]} ms__
♝ **ISP:** __{result["client"]["isp"]}__
"""
    await speed.delete()
    return await message.reply_photo(
        photo=result["share"], caption=speed_string, quote=True
    )
