#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

import os
import shutil
import time
from datetime import datetime

import psutil
from PIL import Image, ImageDraw, ImageFont
from pyrogram import filters
from pyrogram.types import InputMediaPhoto, Message

from src import BotStartTime, bot
from src.helpers.functions import get_readable_bytes, get_readable_time


@bot.on_message(filters.command(["stats", "serverstats"]))
async def stats(_, message: Message):

    image = Image.open("src/helpers/assets/statsbg.png").convert("RGB")
    IronFont = ImageFont.truetype("src/helpers/assets/IronFont.otf", 42)
    draw = ImageDraw.Draw(image)

    # 120, coordinate, progress, coordinate - 25
    def draw_progressbar(coordinate, progress):
        progress = 110 + (progress * 10.8)
        draw.ellipse((105, coordinate - 25, 127, coordinate), fill="#DDFD35")
        progress = 121 if progress < 121 else progress
        draw.rectangle([(120, coordinate - 25), (progress, coordinate)], fill="#DDFD35")
        draw.ellipse(
            (progress - 7, coordinate - 25, progress + 15, coordinate), fill="#DDFD35"
        )

    total, used, free = shutil.disk_usage(".")
    process = psutil.Process(os.getpid())

    botuptime = get_readable_time(time.time() - BotStartTime)
    osuptime = get_readable_time(time.time() - psutil.boot_time())
    botusage = f"{round(process.memory_info()[0]/1024 ** 2)} MiB"

    upload = get_readable_bytes(psutil.net_io_counters().bytes_sent)
    download = get_readable_bytes(psutil.net_io_counters().bytes_recv)

    cpu_percentage = psutil.cpu_percent()
    cpu_count = psutil.cpu_count()

    ram_percentage = psutil.virtual_memory().percent
    ram_total = get_readable_bytes(psutil.virtual_memory().total)
    ram_used = get_readable_bytes(psutil.virtual_memory().used)

    disk_percenatge = psutil.disk_usage("/").percent
    disk_total = get_readable_bytes(total)
    disk_used = get_readable_bytes(used)
    disk_free = get_readable_bytes(free)

    caption = f"♚ **OS Uptime:** __{osuptime}__\n♔ **Bot Usage:** __{botusage}__\n\n♕ **Total Space:** __{disk_total}__\n♛ **Free Space:** __{disk_free}__\n\n♛ **Download:** __{download}__\n♛ **Upload:** __{upload}__"

    start = datetime.now()
    msg = await message.reply_photo(
        photo="https://te.legra.ph/file/30a82c22854971d0232c7.jpg",
        caption=caption,
        quote=True,
    )
    end = datetime.now()

    draw_progressbar(243, int(cpu_percentage))
    draw.text(
        (225, 153),
        f"( {cpu_count} core, {cpu_percentage}% )",
        (255, 255, 255),
        font=IronFont,
    )

    draw_progressbar(395, int(disk_percenatge))
    draw.text(
        (335, 302),
        f"( {disk_used} / {disk_total}, {disk_percenatge}% )",
        (255, 255, 255),
        font=IronFont,
    )

    draw_progressbar(533, int(ram_percentage))
    draw.text(
        (225, 445),
        f"( {ram_used} / {ram_total} , {ram_percentage}% )",
        (255, 255, 255),
        font=IronFont,
    )

    draw.text((290, 590), botuptime, (255, 255, 255), font=IronFont)
    draw.text(
        (910, 590),
        f"{(end-start).microseconds/1000} ms",
        (255, 255, 255),
        font=IronFont,
    )

    image.save("stats.png")
    await msg.edit_media(media=InputMediaPhoto("stats.png", caption=caption))
    os.remove("stats.png")
