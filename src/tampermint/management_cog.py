import logging
import sys

from discord.ext import commands

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))


class BasicCog(commands.Cog):
    """Simple commands like uwu and sync."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="uwu")
    async def uwu(self, ctx: commands.Context):
        """Replies with OwO."""
        logger.info("OwO")
        await ctx.send("OwO")

    @commands.command(name="sync")
    async def sync(self, ctx: commands.Context):
        """Sync new slash commands to Discord."""
        logmsg = "---Synching slash commands---\n"
        synced = await self.bot.tree.sync()
        for command in synced:
            logmsg += f"\t{command}\n"
        logger.info(logmsg)
        await ctx.send(f"Synced {len(synced)} slash commands!")


async def setup(bot: commands.Bot):
    await bot.add_cog(BasicCog(bot))
    logger.info("management cog loaded!")
