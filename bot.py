import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import yaml


QUITE_A_WHILE = 20
ytdl_format_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0', # bind to ipv4 since ipv6 addresses cause issues sometimes
}
ffmpeg_options = {
        'options': '-vn',
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
}


class Player:
    def __init__(self, client, guild):
        self.ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
        self.client = client
        self.guild = guild
        self.queue = asyncio.Queue()
        self.FINISHED_EVENT = 0
        self.SKIPPED_EVENT = 1
        self._run_events = asyncio.Queue()
        self.is_playing = False
        self._run_task = None

    async def join_voice(self, user):
        if not self.is_playing:
            if not user.voice:
                return "You're not connected to voice!"
            await user.voice.channel.connect()
            print("Joined voice channel")

    async def leave_voice(self):
        self.is_playing = False
        if not self.guild.voice_client:
            return "Bot is not connected to a voice channel."
        await self.guild.voice_client.disconnect()

    async def queue_song(self, song):
        print("queueing song: ", song)
        await self.queue.put(song)
        if not self.is_playing:
            asyncio.create_task(self.start_playing())
            return True
        return False

    async def start_playing(self):
        print("Starting run loop")
        self.is_playing = True
        self._run_task = asyncio.create_task(self._run())
        try:
            await self._run_task
        except asyncio.CancelledError:
            print("Run loop stopped")


    async def stop_playing(self):
        self._run_task.cancel()

    async def skip_song(self):
        await self._run_events.put(self.SKIPPED_EVENT)
        

    def _callback(self, err):
        if err:
            print(err)

        asyncio.run(self._run_events.put(self.FINISHED_EVENT))
        # self.client.loop.call_soon_threadsafe(self._run_events.put, self.FINISHED_EVENT)

    async def _responder(self, queue, value):
        value["value"] = await queue.get()

    async def _run(self):
        try:
            voice_channel = self.guild.voice_client
            print("joining voice channel: ", voice_channel.channel)

            value = dict()
            while True:
                # receives the next song from the queue into value
                try:
                    await asyncio.wait_for(self._responder(self.queue, value), QUITE_A_WHILE)
                except TimeoutError:
                    await self.leave_voice()
                    return
                #self.event.clear()
                url = value["value"]

                filename = await self.download_url(url)
                voice_channel.play(discord.FFmpegPCMAudio(filename, **ffmpeg_options), after=self._callback)
                #await self.event.wait()
                event = await self._run_events.get()
                if event == self.SKIPPED_EVENT:
                    voice_channel.stop()
                elif event == self.FINISHED_EVENT:
                    pass # finished song, skipping to next one

        except asyncio.CancelledError:
            print("resetting player")
            self.is_playing = False
            await self.leave_voice()
            self.queue = asyncio.Queue()
            raise asyncio.CancelledError

    async def download_url(self, url):
        data = await self.client.loop.run_in_executor(None, lambda: self.ytdl.extract_info(url, download=False))

        if 'entries' in data:
            # first item from playlist
            data = data['entries'][0]

        return data['url']


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        self.players = {guild: Player(self, guild) for guild in self.guilds}

    async def on_guild_join(self, guild):
        print("Guild joined:", guild)
        self.players[guild] = Player(self, guild)

    async def on_guild_remove(self, guild):
        print("Guild exited:", guild)
        del self.players[guild]

    async def on_message(self, message):
        # TODO:add permisions
        if message.content.startswith('$sync'):
            print("synching")
            synced = await self.tree.sync()
            print("synced: ", synced)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def sync(self, ctx):
        pass

    @commands.command()
    async def set_bot_channel(self, ctx, *, channel: discord.TextChannel):
        pass

    @app_commands.command()
    async def stop(self, interaction: discord.Interaction):
        player = bot.players[interaction.guild]
        await player.stop_playing()
        await interaction.response.send_message(f"Stopped playing")

    @app_commands.command()
    async def skip(self, interaction: discord.Interaction):
        player = bot.players[interaction.guild]
        await player.skip_song()
        await interaction.response.send_message(f"Skipped song")

    @app_commands.command()
    async def play(self, interaction: discord.Interaction, url: str):
        player = bot.players[interaction.guild]
        err = await player.join_voice(interaction.user)
        if err:
            print(err)
            return
        first_in_queue = await player.queue_song(url)
        if first_in_queue:
            await interaction.response.send_message(f"Now playing {url}")
        else:
            await interaction.response.send_message(f"Queued song {url}")

async def main():
    bot = Bot()
    with open("config.yaml") as config_file:
        config = yaml.safe_load(config_file)

    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(config["secret_token"])

asyncio.run(main())
