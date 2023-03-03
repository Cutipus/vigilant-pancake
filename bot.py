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
    is_playing : bool
        Whether or not the player is currently connected to a voice channel.

    FINISHED_EVENT : int
        An event signaling the run task to be stopped.
    SKIPPED_EVENT : int
        An event signaling the run task should skip the current song.
    _queue : asyncio.Queue
        The queue of the songs to play. Each song is a string url.
    _run_task : asyncio.Task
        The run loop of a single voice channel session. Joins voice channel, plays songs from queue and disconnects afterwrards.
    _ytdl : YoutubeDL
        The YoutubeDL downloader.
    """
    def __init__(self, client: commands.Bot, guild: discord.Guild):
        self.FINISHED_EVENT = 0
        self.SKIPPED_EVENT = 1

        self.client = client
        self.guild = guild
        self.is_playing = False

        self._ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
        self._queue = asyncio.Queue()
        self._run_events = asyncio.Queue()
        self._run_task = None

    async def queue_song(self, song: str) -> bool:
        """Queues a song for the run loop to play. Returns True if first song and started playing.
        
        Parameters
        ----------
        song : str
            The url of the song to play. Needs to be playable by youtube-dl.
        """
        await self._queue.put(song)

    async def stop_playing(self):
        """Stops the run loop."""
        self._run_task.cancel()

    async def skip_song(self):
        """Sends skip song event to the run loop."""
        await self._run_events.put(self.SKIPPED_EVENT)

    async def start_playing(self, channel: discord.VoiceChannel):
        """Creates the run loop task and manages and sets is_playing flag.

        Paramters
        ---------
        channel: discord.VoiceChannel
            The voice channel to connect to.
        """
        self.is_playing = True
        self._run_task = asyncio.create_task(self._run(channel))
        self._run_task.add_done_callback(self._cleanup_run_task)

    def _cleanup_run_task(self, _):
        asyncio.create_task(self.guild.voice_client.disconnect())
        self.is_playing = False
        self._run_task = None
        self._queue = asyncio.Queue()

    async def _run(self, voice_channel: discord.VoiceChannel):
        """The player's run loop, responsible for a single session in a voice channel.

        Parameters
        ----------
        voice_channel : discord.VoiceChannel
            The voice channel to join.
        """
        await voice_channel.connect()
        voice_client = self.guild.voice_client

        while True:
            try:
                url = await asyncio.wait_for(self._queue.get(), QUITE_A_WHILE)
            except TimeoutError:
                raise asyncio.CancelledError

            filename = await self._download_url(url)
            voice_client.play(
                    discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS),
                    after=lambda _: asyncio.create_task(self._run_events.put(self.FINISHED_EVENT)))

            event = await self._run_events.get()
            if event == self.SKIPPED_EVENT:
                voice_client.stop()
                await self._run_events.get() # skip finished signal for skipped song
            elif event == self.FINISHED_EVENT:
                pass


    async def _download_url(self, url: str) -> str:
        """Processes the URL of a song and returns the URL of the audio to be used in FFMPEG.

        Parameters
        ----------
        url : str
            The URL of the song to
        """
        data = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._ytdl.extract_info(url, download=False))

        if 'entries' in data:
            # first item from playlist
            data = data['entries'][0]

        return data['url']


class Music(commands.Cog):
    """This is the practical implementation of the music bot.
    It is responsible for managing the music players for the various guilds, and manage commands.

    Attributes
    ----------
    bot : commands.Bot
        A reference to the bot.
    players : Dict[discord.Guild, Player]
        A dictionary of all servers connected and their respective music players.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players = dict()

    @commands.Cog.listener()
    async def on_ready(self):
        """Creates players for all servers the bot is in."""
        print("Initializing music cog...")
        for guild in self.bot.guilds:
            print(f"Creating player for {guild.name}...", end="")
            self.players[guild] = Player(self, guild)
            print("Done")
        print("Music cog ready")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Automatically creates new players for new guilds during runtime."""
        print("Guild joined:", guild)
        self.players[guild] = Player(self, guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Automatically delete players when removed from guilds."""
        print("Guild exited:", guild)
        del self.players[guild]

    @commands.command()
    async def sync(self, ctx):
        """Syncs new slash commands to discord. This should be run when adding, removing or changing slash commands."""
        print("---Synching slash commands---")
        synced = await self.bot.tree.sync()
        for command in synced:
            print(f"\t{command}")
        print("---")

    @commands.command()
    async def set_bot_channel(self, ctx, *, channel: discord.TextChannel):
        """Sets the main text channel for the bot. All messages should be set to this designated channel."""
        pass

    @app_commands.command()
    async def play(self, interaction: discord.Interaction, url: str):
        """Plays a song by URL. If a song is already playing it will be queued."""
        print("Play command started...")
        player = self.players[interaction.guild]

        if not interaction.user.voice and not player.is_playing:
            await interaction.response.send_message("You need to be in a voice channel to start a play session.")
            print("User not connected to any voice channel.")
            return

        await player.queue_song(url)
        if not player.is_playing:
            await player.start_playing(interaction.user.voice.channel)
            await interaction.response.send_message(f"Now playing {url}")
            print("Playing url: ", url)
        else:
            await interaction.response.send_message(f"Queued song {url}")
            print("Queuing url: ", url)

    @app_commands.command()
    async def stop(self, interaction: discord.Interaction):
        """Stops the music player."""
        print("Stopping player")
        player = self.players[interaction.guild]
        await player.stop_playing()
        await interaction.response.send_message(f"Stopped playing")

    @app_commands.command()
    async def skip(self, interaction: discord.Interaction):
        """Skips the current playing song."""
        print("Skipping song...")
        player = self.players[interaction.guild]
        await player.skip_song()
        print("Skip message sent")
        await interaction.response.send_message(f"Skipped song")

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    def on_ready(self):
        print("Bot ready!")


async def main():
    print("Creating bot...")
    bot = Bot()
    print("Loading configuration file...")
    with open("config.yaml") as config_file:
        config = yaml.safe_load(config_file)

    async with bot:
        print("Adding music cog...")
        await bot.add_cog(Music(bot))
        print("Starting bot...")
        await bot.start(config["secret_token"])

asyncio.run(main())
