# File: src/plugins/sudo/render_admin.py

import aiohttp
from pyrogram import filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup,
    InlineKeyboardButton, CallbackQuery
)
from pyrogram.enums import ParseMode

from src.config import RENDER_API_KEY, SERVICE_ID
from src import bot
from src.helpers.filters import sudo_cmd

BASE_URL = "https://api.render.com/v1/services"
HEADERS = {"Authorization": f"Bearer {RENDER_API_KEY}"}


# ───────────────────────────────────────────── #
#               API LAYER                      #
# ───────────────────────────────────────────── #

async def api_get(endpoint):
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, headers=HEADERS) as r:
            return await r.json()

async def api_post(endpoint):
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint, headers=HEADERS) as r:
            return r.status


async def get_service():
    return await api_get(f"{BASE_URL}/{SERVICE_ID}")


async def get_deploys():
    return await api_get(f"{BASE_URL}/{SERVICE_ID}/deploys")


async def restart_service():
    return await api_post(f"{BASE_URL}/{SERVICE_ID}/restart")


async def deploy_latest():
    return await api_post(f"{BASE_URL}/{SERVICE_ID}/deploys")


# ───────────────────────────────────────────── #
#               UI BUILDERS                    #
# ───────────────────────────────────────────── #

def format_status(data):
    details = data.get("serviceDetails", {})
    return (
        f"Service      : {data.get('name')}\n"
        f"Status       : {details.get('status','unknown')}\n"
        f"Environment  : {data.get('env')}\n"
        f"Region       : {data.get('region')}\n"
        f"Auto Deploy  : {data.get('autoDeploy')}\n"
    )


def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Refresh", "rnd_refresh"),
            InlineKeyboardButton("Details", "rnd_details")
        ],
        [
            InlineKeyboardButton("Restart", "rnd_restart"),
            InlineKeyboardButton("Deploy", "rnd_deploy")
        ],
        [
            InlineKeyboardButton("Deploy History", "rnd_deploys")
        ],
        [
            InlineKeyboardButton("Close", "rnd_close")
        ]
    ])


# ───────────────────────────────────────────── #
#               MAIN PANEL                     #
# ───────────────────────────────────────────── #

@bot.on_message(filters.command("render") & sudo_cmd)
async def render_panel(_, message: Message):

    data = await get_service()

    text = (
        "**Render Service Panel**\n\n"
        "Current Status\n"
        "────────────────────────\n"
        f"{format_status(data)}"
    )

    await message.reply_text(
        text,
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )


# ───────────────────────────────────────────── #
#               CALLBACKS                      #
# ───────────────────────────────────────────── #

@bot.on_callback_query(filters.regex("^rnd_"))
async def render_callbacks(_, q: CallbackQuery):

    action = q.data

    # REFRESH
    if action == "rnd_refresh":
        data = await get_service()

        text = (
            "**Render Service Panel**\n\n"
            "Current Status\n"
            "────────────────────────\n"
            f"{format_status(data)}"
        )

        await q.message.edit_text(
            text,
            reply_markup=main_keyboard()
        )

    # DETAILS VIEW
    elif action == "rnd_details":
        data = await get_service()
        details = data.get("serviceDetails", {})

        text = (
            "**Service Details**\n\n"
            "────────────────────────\n"
            f"ID           : {data.get('id')}\n"
            f"Type         : {data.get('type')}\n"
            f"Plan         : {data.get('plan')}\n"
            f"Repo         : {data.get('repo')}\n"
            f"Branch       : {data.get('branch')}\n"
            f"Build Cmd    : {data.get('buildCommand')}\n"
            f"Start Cmd    : {data.get('startCommand')}\n"
            "────────────────────────\n"
        )

        await q.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back", "rnd_refresh")]
            ])
        )

    # RESTART
    elif action == "rnd_restart":
        await q.answer("Processing request...", True)

        status = await restart_service()

        if status == 202:
            await q.answer("Restart initiated", True)
        else:
            await q.answer("Restart failed", True)

    # DEPLOY
    elif action == "rnd_deploy":
        await q.answer("Processing request...", True)

        status = await deploy_latest()

        if status == 201:
            await q.answer("Deployment started", True)
        else:
            await q.answer("Deployment failed", True)

    # DEPLOY HISTORY
    elif action == "rnd_deploys":
        data = await get_deploys()

        deploys = data[:5] if isinstance(data, list) else []

        text = "**Recent Deploys**\n\n────────────────────────\n"

        for d in deploys:
            text += (
                f"ID      : {d.get('id')}\n"
                f"Status  : {d.get('status')}\n"
                f"Commit  : {d.get('commit',{}).get('id','N/A')}\n"
                "────────────────────────\n"
            )

        await q.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back", "rnd_refresh")]
            ])
        )

    # CLOSE
    elif action == "rnd_close":
        await q.message.delete()