"""The best music bot that does YouTube for Discord."""
import logging
import sys

import discord
from discord.ext import commands

from tampermint import music_cog


logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        logger.info("Bot ready!")
        await music_cog.setup(self)  # extensions don't work with packages??

    @commands.command()
    async def sync(self, ctx):
        """Sync new slash commands to discord.

        This should be run when adding, removing or changing slash commands.
        """
        logmsg = "---Synching slash commands---\n"
        synced = await self.bot.tree.sync()
        for command in synced:
            logmsg += f"\t{command}\n"
        logger.info(logmsg)
