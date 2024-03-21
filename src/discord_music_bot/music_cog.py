import asyncio
import logging

from discord import app_commands
from discord.ext import commands
import discord
import yt_dlp

logger = logging.getLogger(__name__)
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
    'source_address': '0.0.0.0',  # bind to ipv4 since ipv6 addresses cause issues sometimes
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
    song_queue : asyncio.Queue[str]
        The list of songs to play
    is_connected : bool
        Whether or not the player is currently connected to a voice channel.
    is_playing : bool
        Whether or not the player is currently playing a song.
    _run_task : asyncio.Task
        The run loop of a single voice channel session. Joins voice channel, plays songs from queue and disconnects afterwrards.
    _ytdl : YoutubeDL
        The YoutubeDL downloader.

    Methods
    -------
    start_playing
        Join the voice channel and begin playing.
    queue_song(str)
        Queue a song.
    skip_song
        Skip the current playing song.
    stop_playing
        Stop the player.
    """

    def __init__(self, client: commands.Bot, guild: discord.Guild):
        self.client = client
        self.guild = guild
        self.song_queue: asyncio.Queue[str] = asyncio.Queue()
        self.is_playing = False
        self.is_connected = False
        self.logger = logging.getLogger(f'{__name__}:Player:{guild.id}')

        self._ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)
        self._run_task = None

    async def queue_song(self, song: str) -> bool:
        """Queues a song for the run loop to play. Returns True if first song and started playing.

        Parameters
        ----------
        song : str
            The url of the song to play. Needs to be playable by youtube-dl.
        """
        await self.song_queue.put(song)
        self.logger.info(f"Queed {song}")

    async def stop_playing(self):
        """Stop the run loop."""
        self._run_task.cancel()
        self.logger.info("Stopped.")

    async def skip_song(self):
        """Send skip song event to the run loop."""
        self.guild.voice_client.stop()
        self.logger.info("Skipped.")

    async def start_playing(self, channel: discord.VoiceChannel):
        """Create the run loop task and manages and sets is_connected flag.

        Paramters
        ---------
        channel: discord.VoiceChannel
            The voice channel to connect to.
        """
        self._run_task = asyncio.create_task(self._run(channel))
        self.logger.info("Started playing.")

    async def _play_file(self, filename: str):
        """Play a file.
        
        Parameters
        ----------
        filename : str
            The file to play.
        """
        # BUG: when exiting it tries to play despite voice_client being None at that point
        self.logger.debug(f"Playing file: {filename}")
        self.is_playing = True
        finished_playing = asyncio.Event()
        self.guild.voice_client.play(
                source=discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS),
                after=lambda _: finished_playing.set())
        await finished_playing.wait()
        self.logger.debug(f"Finished playing file: {filename}")

    async def _run(self, voice_channel: discord.VoiceChannel):
        """Execute the loop responsible for a single session in a voice channel.

        Parameters
        ----------
        voice_channel : discord.VoiceChannel
            The voice channel to join.
        """
        try:
            self.logger.debug("Connecting to voice channel.")
            await voice_channel.connect()
            self.is_connected = True

            while True:
                logger.debug("Fetching next song.")
                url = await self.song_queue.get()  # TODO: Add timeout
                await self._play_file(url)
        finally:
            self.logger.info("Disconnecting from voice channel.")
            await self.guild.voice_client.disconnect()
            self.is_connected = False
            self._run_task = None


class Music(commands.Cog):
    """This is the practical implementation of the music bot.

    It is responsible for managing the music players for the various guilds, and manage commands.

    Attributes
    ----------
    bot : commands.Bot
        A reference to the bot.
    players : Dict[discord.Guild, Player]
        A dictionary of all servers connected and their respective music players.

    Commands
    --------
    sync
        Sync slash commands to discord.

    Slash Commands
    --------------
    play(str)
        Queue a song. If not in voice channel, join and start playing.
    stop
        Stop playing.
    skip
        Skip current song to next one in queue.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players = dict()
        self._ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

    @commands.Cog.listener()
    async def on_ready(self):
        """Create players for all servers the bot is in."""
        logger.debug("Initializing music cog...")
        for guild in self.bot.guilds:
            logger.debug(f"Creating player for {guild.name}...")
            self.players[guild] = Player(self, guild)
        logger.info("Music cog ready")

    @app_commands.command()
    async def play(self, interaction: discord.Interaction, url: str):
        """Play a song by URL. If a song is already playing it will be queued."""
        logger.debug(f"Playing: {url}")
        await interaction.response.defer(thinking=True)
        player = self.players[interaction.guild]
        if not interaction.user.voice and not player.is_connected:
            await interaction.followup.send("You need to be in a voice channel to start a play session.")
            logger.info("User not connected to any voice channel.")
            return
        playlist = await self._parse_url(url)  # consider reworking _get_audio_urls
        output = 'Queued song(s)\n'
        for title, url in playlist.items():
            output += f"{title}\n"
            await player.queue_song(url)
        logger.info(output)
        await interaction.followup.send(output)
        if not player.is_connected:
            await player.start_playing(interaction.user.voice.channel)

    @app_commands.command()
    async def stop(self, interaction: discord.Interaction):
        """Stop the music player."""
        logger.info("Stopping player")
        player = self.players[interaction.guild]
        await player.stop_playing()
        await interaction.response.send_message("Stopped playing")

    @app_commands.command()
    async def skip(self, interaction: discord.Interaction):
        """Skips the current playing song."""
        logger.info("Skipping song...")
        player = self.players[interaction.guild]
        await player.skip_song()
        logger.info("Skip message sent")
        await interaction.response.send_message("Skipped song")

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Automatically creates new players for new guilds during runtime."""
        self.players[guild] = Player(self, guild)
        logger.info(f"Guild joined: {guild}")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Automatically delete players when removed from guilds."""
        del self.players[guild]
        logger.info(f"Guild exited: {guild}")

    # TODO: move to a different data type
    async def _parse_url(self, request: str) -> dict[str, str]:
        """Parse the URL of a song and returns a song_name->audio_url dict.

        Parameters
        ----------
        url : str
            The URL of the song to parse.
        """
        logger.debug("")
        data = await asyncio.get_running_loop().run_in_executor(
                None,
                self._ytdl.extract_info,
                request,
                download=False,)

        if 'entries' in data:
            return {entry['title']: entry['url'] for entry in data['entries']}
        else:
            return dict(((data['title'], data['url']),))


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
    logger.info('loaded Music cog')
