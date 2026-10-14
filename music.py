import asyncio
import shutil
from collections import defaultdict, deque
import discord

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch1",
    "extract_flat": False,
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class MusicManager:
    def __init__(self, bot):
        self.bot = bot
        self.queues = defaultdict(deque)
        self.now_playing = {}
        self.lock = asyncio.Lock()

    async def extract(self, query):
        if yt_dlp is None:
            raise RuntimeError("Music search needs yt-dlp installed.")
        loop = asyncio.get_running_loop()
        def run():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                return ydl.extract_info(query, download=False)
        info = await loop.run_in_executor(None, run)
        if "entries" in info:
            info = next((entry for entry in info["entries"] if entry), None)
        if not info:
            raise RuntimeError("No matching track found.")
        return {"title": info.get("title", "Unknown title"), "url": info.get("url"), "webpage_url": info.get("webpage_url", query)}

    async def play(self, interaction, query):
        if not interaction.guild:
            raise RuntimeError("Use music commands in a server.")
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg is not installed on the hosting machine.")
        if not interaction.user.voice or not interaction.user.voice.channel:
            raise RuntimeError("Join a voice channel first.")
        voice_channel = interaction.user.voice.channel
        voice = interaction.guild.voice_client
        if voice is None:
            voice = await voice_channel.connect()
        elif voice.channel != voice_channel:
            await voice.move_to(voice_channel)
        track = await self.extract(query)
        guild_id = interaction.guild.id
        async with self.lock:
            if voice.is_playing() or voice.is_paused() or guild_id in self.now_playing:
                self.queues[guild_id].append(track)
                return f"➕ Added **{track['title']}** to the queue."
            return await self._start_track(interaction.guild, voice, track)

    async def _start_track(self, guild, voice, track):
        source = discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source, volume=0.5)
        self.now_playing[guild.id] = track
        def after(error):
            if error:
                print(f"Music playback error: {error}")
            asyncio.run_coroutine_threadsafe(self._next(guild, voice), self.bot.loop)
        voice.play(source, after=after)
        return f"▶️ Now playing **{track['title']}**"

    async def _next(self, guild, voice):
        async with self.lock:
            if self.queues[guild.id]:
                track = self.queues[guild.id].popleft()
                await self._start_track(guild, voice, track)
            else:
                self.now_playing.pop(guild.id, None)

    def _voice(self, interaction):
        return interaction.guild.voice_client if interaction.guild else None

    async def skip(self, interaction):
        voice = self._voice(interaction)
        if not voice or not (voice.is_playing() or voice.is_paused()):
            return "Nothing is playing."
        voice.stop()
        return "⏭️ Skipped the current track."

    async def stop(self, interaction):
        voice = self._voice(interaction)
        if not voice:
            return "The bot is not in a voice channel."
        self.queues[interaction.guild.id].clear()
        self.now_playing.pop(interaction.guild.id, None)
        voice.stop()
        await voice.disconnect()
        return "⏹️ Stopped music and cleared the queue."

    async def pause(self, interaction):
        voice = self._voice(interaction)
        if not voice or not voice.is_playing():
            return "Nothing is playing."
        voice.pause()
        return "⏸️ Paused."

    async def resume(self, interaction):
        voice = self._voice(interaction)
        if not voice or not voice.is_paused():
            return "Nothing is paused."
        voice.resume()
        return "▶️ Resumed."

    async def show_queue(self, interaction):
        guild_id = interaction.guild.id
        lines = []
        current = self.now_playing.get(guild_id)
        if current:
            lines.append(f"**Now playing:** {current['title']}")
        for i, track in enumerate(list(self.queues[guild_id])[:10], start=1):
            lines.append(f"{i}. {track['title']}")
        return "\n".join(lines) if lines else "The music queue is empty."
