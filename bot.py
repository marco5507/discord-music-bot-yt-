"""
Discord music bot
==================

This script defines a simple Discord bot that can play music from YouTube.
Users can issue commands prefixed with ``!`` to have the bot join a voice
channel, play songs by URL or search query, control playback (pause,
resume, skip, previous), and display the queue of upcoming songs.  The
implementation uses the ``discord.py`` library together with the
``yt‑dlp`` extractor to stream audio directly from YouTube.  FFmpeg is
required for audio transcoding.

The design is intentionally lightweight: a per‑guild ``MusicPlayer``
instance maintains a list of queued tracks and manages playback.  When
the current track finishes, the bot automatically advances to the next
one.  The bot token is loaded from the environment variable
``DISCORD_TOKEN`` or a ``.env`` file when available.

This code is for educational purposes.  Downloading YouTube content may
violate YouTube’s Terms of Service【562454067469386†L183-L190】—use it
responsibly and at your own risk.
"""

import asyncio
import os
import re
from typing import Dict, List, Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

import yt_dlp

###############################################################################
# Configuration
#
# The YT‑DLP and FFmpeg settings below were inspired by the Python Land
# tutorial’s configuration for ``youtube_dl``【562454067469386†L183-L224】.  They
# select the best available audio track, restrict playlists, and prevent
# unnecessary logging.  FFmpeg is configured to exclude the video stream.
###############################################################################

load_dotenv()  # load .env file if present

# Discord bot token must be provided via environment variable or .env file
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN not set. Please create a .env file or set the environment variable."
    )

# YT‑DLP options: select audio only, quiet mode, safe defaults
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "auto",  # allows searching with plain text
    "source_address": "0.0.0.0",  # bind to ipv4
}
FFMPEG_OPTIONS = {
    "options": "-vn",  # drop the video stream
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


async def extract_info(search: str) -> Dict:
    """Use yt‑dlp to extract video information.

    If ``search`` is a valid URL, the metadata for that URL is returned.  If
    ``search`` does not look like a URL, yt‑dlp performs a YouTube search and
    returns the first result.  Because ``ytdl.extract_info`` is blocking,
    extraction is run in an executor.

    :param search: A YouTube URL or a search query.
    :returns: Metadata dictionary including ``title``, ``url`` and
              ``webpage_url``.
    """
    loop = asyncio.get_event_loop()
    # Determine whether the query is a URL; simple heuristic using regex
    url_regex = re.compile(r"^https?://")
    query = search if url_regex.match(search) else f"ytsearch:{search}"
    info = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    # If a search returns a playlist of entries, use the first entry
    if "entries" in info:
        info = info["entries"][0]
    return info


def create_audio_source(info: Dict) -> discord.AudioSource:
    """Create a FFmpeg audio source from yt‑dlp metadata.

    The function builds a ``discord.FFmpegPCMAudio`` object using the
    extracted audio URL.  Additional reconnection options could be added
    here if desired.

    :param info: Metadata dict returned by ``extract_info``.
    :returns: Audio source ready for playback in Discord.
    """
    # ``url`` contains a direct link to the media stream
    url = info.get("url")
    # Use FFmpeg to transcode the stream; drop video with -vn
    return discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)


class MusicPlayer:
    """Maintain a queue of tracks and manage playback for a guild.

    Each guild using the music bot gets its own instance of ``MusicPlayer``.
    The player stores the queue, keeps track of the current index and
    orchestrates starting the next track when the current one finishes.
    """

    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.queue: List[Dict] = []  # each item: {info, source}
        self.current_index: int = -1
        self.voice_client: Optional[discord.VoiceClient] = None
        self.lock = asyncio.Lock()  # ensure single access to queue

    async def connect(self, channel: discord.VoiceChannel):
        """Connect to a voice channel or move if already connected."""
        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.channel != channel:
                await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()

    async def add_track(self, info: Dict):
        """Add a track to the queue and start playing if idle."""
        async with self.lock:
            source = create_audio_source(info)
            self.queue.append({"info": info, "source": source})
            # If nothing is currently playing, start playback immediately
            if not self.voice_client.is_playing() and not self.voice_client.is_paused():
                await self._play_next()

    async def _play_next(self):
        """Play the next track in the queue, if any."""
        async with self.lock:
            self.current_index += 1
            if 0 <= self.current_index < len(self.queue):
                entry = self.queue[self.current_index]
                source = entry["source"]
                info = entry["info"]

                def after_playback(error: Optional[Exception]):
                    # Schedule the next track in the event loop
                    fut = asyncio.run_coroutine_threadsafe(self._play_next(), self.bot.loop)
                    try:
                        fut.result()
                    except Exception:
                        pass

                self.voice_client.play(source, after=after_playback)
            else:
                # queue exhausted, disconnect and reset index
                await self.stop()

    async def stop(self):
        """Stop playback and reset state."""
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.disconnect()
        self.queue.clear()
        self.current_index = -1
        self.voice_client = None

    async def pause(self):
        if self.voice_client and self.voice_client.is_playing():
            await self.voice_client.pause()

    async def resume(self):
        if self.voice_client and self.voice_client.is_paused():
            await self.voice_client.resume()

    async def skip(self):
        """Skip the current track by stopping it.  The after callback will
        automatically trigger playback of the next track."""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    async def previous(self):
        """Replay the previous track, if available."""
        async with self.lock:
            # There must be a previous track (index >= 1)
            if self.current_index > 0:
                # Move back two positions because the after callback will increment by one
                self.current_index -= 2
                self.voice_client.stop()
                return True
            return False

    def format_queue(self) -> str:
        """Return a human‑readable representation of the queue."""
        if not self.queue:
            return "Queue is empty."
        lines = []
        for i, entry in enumerate(self.queue):
            marker = "-> " if i == self.current_index else "   "
            title = entry["info"].get("title", "Unknown title")
            lines.append(f"{marker}{i + 1}. {title}")
        return "\n".join(lines)


###############################################################################
# Bot setup and command definitions
###############################################################################

intents = discord.Intents.default()
intents.message_content = True  # required to read message content
bot = commands.Bot(command_prefix="!", intents=intents, description="Music bot")

players: Dict[int, MusicPlayer] = {}


def get_player(ctx: commands.Context) -> MusicPlayer:
    """Get or create a MusicPlayer for the guild associated with the context."""
    guild_id = ctx.guild.id
    if guild_id not in players:
        players[guild_id] = MusicPlayer(bot, guild_id)
    return players[guild_id]


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")


@bot.command(name="join", help="Make the bot join your voice channel")
async def join(ctx: commands.Context):
    if not ctx.author.voice:
        await ctx.send(f"{ctx.author.name}, you are not connected to a voice channel.")
        return
    player = get_player(ctx)
    await player.connect(ctx.author.voice.channel)
    await ctx.send(f"Joined {ctx.author.voice.channel.name}.")


@bot.command(name="leave", help="Disconnect from the voice channel and clear the queue")
async def leave(ctx: commands.Context):
    player = players.get(ctx.guild.id)
    if not player or not player.voice_client or not player.voice_client.is_connected():
        await ctx.send("I am not connected to any voice channel.")
        return
    await player.stop()
    players.pop(ctx.guild.id, None)
    await ctx.send("Disconnected and cleared the queue.")


@bot.command(name="play", help="Play a song by URL or search term")
async def play(ctx: commands.Context, *, query: str):
    # Ensure the user is connected to a voice channel
    if not ctx.author.voice:
        await ctx.send("You need to be connected to a voice channel to play music.")
        return
    # Connect if not already connected
    player = get_player(ctx)
    await player.connect(ctx.author.voice.channel)
    # Extract info using yt‑dlp
    try:
        info = await extract_info(query)
    except Exception as e:
        await ctx.send(f"Error extracting information: {e}")
        return
    await player.add_track(info)
    title = info.get("title", "Unknown title")
    await ctx.send(f"Added to queue: {title}")


@bot.command(name="pause", help="Pause the current song")
async def pause(ctx: commands.Context):
    player = players.get(ctx.guild.id)
    if not player or not player.voice_client:
        await ctx.send("Not connected to any voice channel.")
        return
    if player.voice_client.is_playing():
        await player.pause()
        await ctx.send("Paused.")
    else:
        await ctx.send("Nothing is playing.")


@bot.command(name="resume", help="Resume a paused song")
async def resume(ctx: commands.Context):
    player = players.get(ctx.guild.id)
    if not player or not player.voice_client:
        await ctx.send("Not connected to any voice channel.")
        return
    if player.voice_client.is_paused():
        await player.resume()
        await ctx.send("Resumed.")
    else:
        await ctx.send("Nothing is paused.")


@bot.command(name="skip", help="Skip to the next song in the queue")
async def skip(ctx: commands.Context):
    player = players.get(ctx.guild.id)
    if not player or not player.voice_client:
        await ctx.send("Not connected to any voice channel.")
        return
    if player.current_index + 1 >= len(player.queue):
        await ctx.send("No more songs in the queue.")
        return
    await player.skip()
    await ctx.send("Skipped.")


@bot.command(name="prev", help="Play the previous song")
async def prev(ctx: commands.Context):
    player = players.get(ctx.guild.id)
    if not player or not player.voice_client:
        await ctx.send("Not connected to any voice channel.")
        return
    if await player.previous():
        await ctx.send("Playing previous song...")
    else:
        await ctx.send("There is no previous song to play.")


@bot.command(name="queue", help="Show the current song queue")
async def queue(ctx: commands.Context):
    player = players.get(ctx.guild.id)
    if not player:
        await ctx.send("The queue is empty.")
    else:
        await ctx.send(player.format_queue())


if __name__ == "__main__":
    bot.run(TOKEN)