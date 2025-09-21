"""The best music bot that does YouTube for Discord."""

import logging
import sys

import discord
from discord.ext import commands
from discord.ext.commands import Context

from tampermint import music_cog
from tampermint import management_cog


logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        logger.info("Bot ready!")


async def start_bot(secret):
    bot = Bot()
    await music_cog.setup(bot)
    await management_cog.setup(bot)
    await bot.start(secret)
