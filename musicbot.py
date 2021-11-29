"""
MusicBot

Searches and plays music from youtube.
"""

import time
import asyncio
import yt_dlp.YoutubeDL
import discord
from discord.ext import commands


intents = discord.Intents.default()
intents.members = True


bot = commands.Bot(command_prefix="!", case_insensitive=True)
bot.remove_command('help')


@bot.event
async def on_ready():
    print(f"Bot is ready.\n")
    await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.listening, name='commands'))


class Player(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.song_queue = []
        self.is_playing = False
        self.end_time = None
        self.timer_on = False
        self.bot_vc = None

        self.FFMPEG_OPTIONS = {
            'before_options': '-referer "https://www.youtube.com/" '
                              '-user_agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36" '
                              '-reconnect 1 '
                              '-reconnect_streamed 1 '
                              '-reconnect_on_network_error 1 '
                              '-reconnect_delay_max 5',
            'options': '-vn'
        }

        self.YTDL_OPTIONS = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
            "referer": "https://www.youtube.com/",
            'noplaylist': 'True'
        }

    async def leave_timer(self, ctx):
        self.timer_on = True
        while True:
            await asyncio.sleep(1)
            if self.end_time is not None:
                if time.perf_counter() - self.end_time > 600:
                    if ctx.voice_client is not None:
                        break

        print(f"Leaving {self.bot_vc} due to inactivity\n")
        await ctx.voice_client.disconnect()
        self.timer_on = False
        self.bot_vc = None
        self.end_time = None

    async def check_queue(self, ctx):
        if len(self.song_queue) > 0:
            self.end_time = None
            await self.play_song(ctx, self.song_queue[0][0], self.song_queue[0][1])

            if len(self.song_queue) > 0:
                self.song_queue.pop(0)
            self.is_playing = True

        else:
            self.is_playing = False
            await bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.listening,
                                          name='commands'))
            self.end_time = time.perf_counter()

    async def search_song(self, ctx, song):
        print(f"Extracting info: {song}")
        # when song isn't URL
        if not ("youtube.com/watch?" in song or "https://youtu.be/" in song):
            message = await ctx.send("Searching...")

            info = await self.bot.loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(self.YTDL_OPTIONS).extract_info(f"ytsearch:{song}", download=False, ie_key="YoutubeSearch"))
            await message.delete()

            if info['entries'] is None or info['entries'] == []:
                await ctx.send("Couldn't find song.")
                return
            else:
                info = info['entries'][0]

        # when song is URL
        else:
            try:
                info = await self.bot.loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(self.YTDL_OPTIONS).extract_info(song, download=False))
            except Exception:
                await ctx.send("Couldn't find song.")
                return

        url = None
        try:
            for video_format in info["formats"]:
                if video_format["format_id"] == "251":
                    url = video_format["url"]
                    break
        except KeyError:
            await ctx.send("Couldn't find song.")
            return

        title = info['title']

        queue_len = len(self.song_queue)
        self.song_queue.append([url, title])

        if not self.is_playing:
            await self.check_queue(ctx)

        else:
            print(f"Queued - Position {queue_len + 1}\n{title}\n")
            embed = discord.Embed(
                title=f"Queued - Position {queue_len + 1}",
                description=title,
                colour=discord.Colour.green()
            )
            await ctx.send(embed=embed)

    async def play_song(self, ctx, url, title):

        print(f"Playing: {title}\n")
        embed = discord.Embed(
                    title="Now Playing",
                    description=title,
                    colour=discord.Colour.blue()
        )
        await ctx.send(embed=embed)

        await bot.change_presence(activity=discord.Game(title))

        try:
            source = discord.FFmpegOpusAudio(url, **self.FFMPEG_OPTIONS, codec="copy")

            ctx.voice_client.play(source, after=lambda error: self.bot.loop.create_task(self.check_queue(ctx)))

        except Exception:
            await ctx.send("Could not play song, skipping")
            ctx.voice_client.stop()
            await bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.listening,
                                          name='commands'))
            self.bot.loop.create_task(self.check_queue(ctx))

    @commands.command()
    async def leave(self, ctx):
        print(f"Leaving {ctx.author.voice.channel}\n")
        if ctx.voice_client is not None:
            self.end_time = None
            await ctx.voice_client.disconnect()
            self.bot_vc = None
        else:
            await ctx.send("I am not connected to a voice channel.")

    @commands.command()
    async def play(self, ctx, *, song=None):
        if song is None:
            await ctx.send("You must include a song to play.")
            return

        if ctx.voice_client is None:
            if ctx.author.voice is None:
                await ctx.send(
                    "Please connect to the channel you want the bot to join.")
                return
            else:
                await ctx.author.voice.channel.connect()
                self.bot_vc = ctx.author.voice.channel
                print(f"Joining: {self.bot_vc}\n")

        if self.bot_vc != ctx.author.voice.channel:
            await ctx.send("Changing voice channel...")
            await ctx.voice_client.move_to(ctx.author.voice.channel)
            print(f"Changing channel:{self.bot_vc} to {ctx.author.voice.channel}")
            self.bot_vc = ctx.author.voice.channel

        if not self.timer_on:
            bot.loop.create_task(self.leave_timer(ctx))

        await self.search_song(ctx, song)

    @commands.command()
    async def remove(self, ctx, *, song=None):
        if len(self.song_queue) == 0:
            await ctx.send(f"Song queue is empty.")
            return

        if song is None:
            await ctx.send("You must include a song number to remove!")
        elif song == "last":
            try:
                title = self.song_queue.pop(-1)[1]
                await ctx.send(f"Removed {title}")
            except IndexError:
                await ctx.send(f"Song queue is empty.")
        else:
            try:
                song_index = int(song) - 1
                if song_index == -1:
                    await ctx.send("Invalid song number!")
                    return

            except ValueError:
                await ctx.send(f"You must include the song number!")
                return

            try:
                title = self.song_queue[song_index][1]
                self.song_queue.pop(song_index)
                print(
                    f"Removed {song_index+1}. {title}"
                )
                await ctx.send(f"Removed **{song_index+1}.** {title}")
            except IndexError:
                await ctx.send("Invalid song number!")

    @commands.command()
    async def queue(self, ctx):  # display the current guilds queue
        if len(self.song_queue) == 0:
            return await ctx.send("There are currently no songs in the queue.")

        embed = discord.Embed(title="Song Queue", description="",
                              colour=discord.Colour.blue())
        i = 1
        for url in self.song_queue:
            embed.description += f"{i}. {url[1]}\n"
            i += 1

        await ctx.send(embed=embed)

    @commands.command()
    async def skip(self, ctx):
        print("Skipping\n")
        if not self.is_playing:
            return await ctx.send("I am not playing any song.")

        if ctx.author.voice is None:
            return await ctx.send(
                "You are not connected to any voice channel.")

        if ctx.author.voice.channel.id != ctx.voice_client.channel.id:
            return await ctx.send(
                "I am not currently playing any songs for you.")
        ctx.voice_client.stop()

    @commands.command()
    async def move(self, ctx):
        if self.bot_vc != ctx.author.voice.channel:
            await ctx.send("Changing voice channel")
            await ctx.voice_client.move_to(ctx.author.voice.channel)
            print(f"Changing channel:{self.bot_vc} to {ctx.author.voice.channel}")
            self.bot_vc = ctx.author.voice.channel

    @commands.command()
    async def clear(self, ctx):
        queue_len = len(self.song_queue)
        print(f"Cleared {queue_len} songs from queue\n")
        self.song_queue.clear()
        await ctx.send(f":white_check_mark: Song queue cleared")

    @commands.command()
    async def pause(self, ctx):
        if ctx.voice_client.is_paused():
            return await ctx.send("I am already paused.")
        else:
            ctx.voice_client.pause()
            await ctx.send("The current song has been paused.")

    @commands.command()
    async def resume(self, ctx):
        if ctx.voice_client is None:
            return await ctx.send("I am not connected to a voice channel.")

        elif not ctx.voice_client.is_paused():
            return await ctx.send("I am already playing a song.")

        else:
            ctx.voice_client.resume()
            await ctx.send("The current song has been resumed.")

    @commands.command()
    async def help(self, ctx):
        embed = discord.Embed(
            title="Commands",
            description="**!play** 'name or link': Plays song from youtube\n"
                        "**!skip**: Skips current song\n"
                        "**!remove** 'song number': Removes song from queue\n"
                        "**!move**: Moves bot to user's voice channel\n"
                        "**!queue**: Shows current song queue\n"
                        "**!clear**: Clears song queue, doesn't skip\n"
                        "**!pause**: Pauses current song\n"
                        "**!resume**: Resumes current song\n"
                        "**!leave**: Disconnects the bot from voice",
            colour=discord.Colour.blue()
        )
        await ctx.send(embed=embed)


async def setup():
    await bot.wait_until_ready()
    bot.add_cog(Player(bot))


bot.loop.create_task(setup())

bot.run("TOKEN")  # Replace TOKEN with your discord bot token
