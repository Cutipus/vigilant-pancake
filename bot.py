import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import yaml


QUITE_A_WHILE = 20
YTDL_FORMAT_OPTIONS = {
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
FFMPEG_OPTIONS = {
        'options': '-vn',
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
}


class Player:
    """A music player instance. One should exist for every guild.

    Attributes
    ----------
    client : commands.Bot
        The bot running the player.
    guild : discord.Guild
        The guild associated with the player. Each player is responsible for only one guild.

    FINISHED_EVENT : int
        An event signaling the run task to be stopped.
    SKIPPED_EVENT : int
        An event signaling the run task should skip the current song.
    _queue : asyncio.Queue
        The queue of the songs to play. Each song is a string url.
    _run_task : asyncio.Task
        The run loop of a single voice channel session. Joins voice channel, plays songs from queue and disconnects afterwrards.
    _is_playing : bool
        Whether or not the player is currently connected to a voice channel.
    _ytdl : YoutubeDL
        The YoutubeDL downloader.
    """
    def __init__(self, client: commands.Bot, guild: discord.Guild):
        self.FINISHED_EVENT = 0
        self.SKIPPED_EVENT = 1

        self.client = client
        self.guild = guild

        self._ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
        self._queue = asyncio.Queue()
        self._run_events = asyncio.Queue()
        self._is_playing = False
        self._run_task = None

    async def queue_song(self, song: str) -> bool:
        """Queues a song for the run loop to play. Returns True if first song and started playing.
        
        Parameters
        ----------
        song : str
            The url of the song to play. Needs to be playable by youtube-dl.
        """
        print("queueing song: ", song)
        await self._queue.put(song)
        if not self._is_playing:
            asyncio.create_task(self._start_playing())
            return True
        return False

    async def stop_playing(self):
        """Stops the run loop."""
        self._run_task.cancel()

    async def skip_song(self):
        """Sends skip song event to the run loop."""
        await self._run_events.put(self.SKIPPED_EVENT)

    async def _run(self):
        """The player's run loop, responsible for a single session in a voice channel."""
        try:
            voice_channel = self.guild.voice_client
            print("Joining voice channel: ", voice_channel.channel)

            value = dict()
            while True:
                try:
                    url = await asyncio.wait_for(self.queue.get(), QUITE_A_WHILE)
                except TimeoutError:
                    await self._leave_voice()
                    return

                filename = await self._download_url(url)
                voice_channel.play(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), after=self._callback)

                # handles external events 
                event = await self._run_events.get()
                if event == self.SKIPPED_EVENT:
                    voice_channel.stop()
                elif event == self.FINISHED_EVENT:
                    pass # finished song, skipping to next one

        except asyncio.CancelledError:
            print("resetting player")
            self._is_playing = False
            await self._leave_voice()
            self._queue = asyncio.Queue()
            raise asyncio.CancelledError

    async def _join_voice(self, user: discord.Member):
        """Joins a user's voice channel. Returns False if user not in any voice channel.
        
        Parameters
        ----------
        user : discord.Member
            The user who's connected voice channel to join to.
        """
        if not self._is_playing:
            if not user.voice:
                return False
            await user.voice.channel.connect()
            print("Joined voice channel")
            return True

    async def _leave_voice(self) -> bool:
        """Disconnects from voice channel and sets is_playing flag.
        Returns True if not connected to any channel.
        """
        self._is_playing = False
        if not self.guild.voice_client:
            return False
        await self.guild.voice_client.disconnect()
        return True

    async def _start_playing(self):
        """Creates the run loop task and manages and sets is_playing flag."""
        print("Starting run loop")
        self._is_playing = True
        self._run_task = asyncio.create_task(self._run())
        try:
            await self._run_task
        except asyncio.CancelledError:
            print("Run loop stopped")

    def _callback(self, err):
        """Called at the end of a song and sends event to run loop."""
        if err:
            print(err)

        asyncio.run(self._run_events.put(self.FINISHED_EVENT))

    async def _download_url(self, url: str) -> str:
        """Processes the URL of a song and returns the URL of the audio to be used in FFMPEG.

        Parameters
        ----------
        url : str
            The URL of the song to
        """
        data = await self.client.loop.run_in_executor(None, lambda: self._ytdl.extract_info(url, download=False))

        if 'entries' in data:
            # first item from playlist
            data = data['entries'][0]

        return data['url']


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = None

    @commands.Cog.listener()
    async def on_ready(self):
        self.players = {guild: Player(self, guild) for guild in self.guilds}
        print("---Music cog ready, connected to servers--")
        for guild in self.players.keys():
            print(f"\t{guild.name}")
        print("---")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        print("Guild joined:", guild)
        self.players[guild] = Player(self, guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        print("Guild exited:", guild)
        del self.players[guild]

    @commands.command()
    async def sync(self, ctx):
        print("---Synching slash commands---")
        synced = await self.bot.tree.sync()
        for command in synced:
            print(f"\t{command}")
        print("---")

    @commands.command()
    async def set_bot_channel(self, ctx, *, channel: discord.TextChannel):
        pass

    @app_commands.command()
    async def stop(self, interaction: discord.Interaction):
        print("Stopping player")
        player = bot.players[interaction.guild]
        await player.stop_playing()
        await interaction.response.send_message(f"Stopped playing")

    @app_commands.command()
    async def skip(self, interaction: discord.Interaction):
        print("Skipping song")
        player = bot.players[interaction.guild]
        await player.skip_song()
        await interaction.response.send_message(f"Skipped song")

    @app_commands.command()
    async def play(self, interaction: discord.Interaction, url: str):
        player = bot.players[interaction.guild]
        err = await player._join_voice(interaction.user)
        if err:
            print(err)
            return
        first_in_queue = await player.queue_song(url)
        if first_in_queue:
            print("Playing url: ", url)
            await interaction.response.send_message(f"Now playing {url}")
        else:
            print("Queuing url: ", url)
            await interaction.response.send_message(f"Queued song {url}")

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)


async def main():
    bot = Bot()
    with open("config.yaml") as config_file:
        config = yaml.safe_load(config_file)

    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(config["secret_token"])

asyncio.run(main())
