"""
MusicBot

Searches and plays music from youtube.
"""


import yt_dlp.YoutubeDL
import discord
from discord.ext import commands


intents = discord.Intents.default()
intents.members = True


bot = commands.Bot(command_prefix="!", case_insensitive=True)
bot.remove_command('help')


@bot.event
async def on_ready():
    print(f"{bot.user.name} is ready.\n")
    await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.listening, name='commands'))


class Player(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.song_queue = {}
        self.is_playing = False

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

        self.setup()

    def setup(self):
        for guild in self.bot.guilds:
            self.song_queue[guild.id] = []

    async def check_queue(self, ctx):
        if len(self.song_queue[ctx.guild.id]) > 0:
            await self.play_song(ctx, self.song_queue[ctx.guild.id][0][0], self.song_queue[ctx.guild.id][0][1])

            if len(self.song_queue[ctx.guild.id]) > 0:
                self.song_queue[ctx.guild.id].pop(0)
            self.is_playing = True

        else:
            self.is_playing = False
            await bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.listening,
                                          name='commands'))

    async def search_song(self, ctx, song):
        # when song isn't URL
        if not ("youtube.com/watch?" in song or "https://youtu.be/" in song):
            await ctx.send("Searching...")

            info = await self.bot.loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(self.YTDL_OPTIONS).extract_info(f"ytsearch:{song}", download=False, ie_key="YoutubeSearch"))

            if info['entries'] is None or info['entries'] == []:
                return await ctx.send("Couldn't find song.")
            else:
                info = info['entries'][0]

        # when song is URL
        else:
            try:
                info = await self.bot.loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(self.YTDL_OPTIONS).extract_info(song, download=False))
            except Exception:
                return await ctx.send("Couldn't find song.")

        url = info['formats'][4]['url']
        title = info['title']

        queue_len = len(self.song_queue[ctx.guild.id])
        self.song_queue[ctx.guild.id].append([url, title])

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

        print(f"Playing: {title}\n{url}\n")
        embed = discord.Embed(
                    title=":arrow_forward: Now playing :arrow_forward:",
                    description=title,
                    colour=discord.Colour.blue()
        )
        await ctx.send(embed=embed)

        await bot.change_presence(activity=discord.Game(title))

        try:
            ctx.voice_client.play((discord.FFmpegOpusAudio(
                    url, **self.FFMPEG_OPTIONS, codec="copy")),
                              after=lambda error:
                              self.bot.loop.create_task(self.check_queue(ctx)))

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
            return await ctx.voice_client.disconnect()

        await ctx.send("I am not connected to a voice channel.")

    @commands.command()
    async def play(self, ctx, *, song=None):
        if ctx.voice_client is None:
            if ctx.author.voice is None:
                return await ctx.send(
                    "Please connect to the channel you want the bot to join.")
            else:
                await ctx.author.voice.channel.connect()
                print(f"Joining: {ctx.author.voice.channel}\n")

        if song is None:
            return await ctx.send("You must include a song to play.")

        elif ctx.voice_client is None:
            return await ctx.send(
                "I must be in a voice channel to play a song.")
        else:
            await self.search_song(ctx, song)

    @commands.command()
    async def queue(self, ctx):  # display the current guilds queue
        if len(self.song_queue[ctx.guild.id]) == 0:
            return await ctx.send("There are currently no songs in the queue.")

        embed = discord.Embed(title="Song Queue", description="",
                              colour=discord.Colour.blue())
        i = 1
        for url in self.song_queue[ctx.guild.id]:
            embed.description += f"{i}. {url[1]}\n"
            i += 1

        await ctx.send(embed=embed)

    @commands.command()
    async def skip(self, ctx):
        print("Skipping\n")
        if ctx.voice_client is None:
            return await ctx.send("I am not playing any song.")

        if ctx.author.voice is None:
            return await ctx.send(
                "You are not connected to any voice channel.")

        if ctx.author.voice.channel.id != ctx.voice_client.channel.id:
            return await ctx.send(
                "I am not currently playing any songs for you.")
        ctx.voice_client.stop()

    @commands.command()
    async def clear(self, ctx):
        queue_len = len(self.song_queue[ctx.guild.id])
        print(f"Cleared {queue_len} songs from queue\n")
        self.song_queue[ctx.guild.id].clear()
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
            description="play\nskip\nqueue\nclear\npause\nresume ",
            colour=discord.Colour.blue()
        )
        await ctx.send(embed=embed)


async def setup():
    await bot.wait_until_ready()
    bot.add_cog(Player(bot))


bot.loop.create_task(setup())

bot.run("TOKEN")  # Replace TOKEN with your discord bot token
