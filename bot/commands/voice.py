import random
import asyncio
import discord
import discord.ext.commands as commands
from discord.ext import tasks
from bot.commands import audio_queues, voice_joiners

def play_next(error, vc, guild_id):
    if error:
        print(f"player error: {error}")
        
    if guild_id in audio_queues and len(audio_queues[guild_id]) > 0:
        source = audio_queues[guild_id].pop(0)
        vol = 0.25 if "badapple" in source else 0.6
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source), volume=vol)
        vc.play(audio_source, after=lambda e: play_next(e, vc, guild_id))

def queue_audio(vc, source):
    guild_id = vc.guild.id
    if not vc.is_playing():
        vol = 0.25 if "badapple" in source else 0.6
        audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(source), volume=vol)
        vc.play(audio_source, after=lambda e: play_next(e, vc, guild_id))
    else:
        if guild_id not in audio_queues:
            audio_queues[guild_id] = []
        audio_queues[guild_id].append(source)

def setup_voice(client: commands.Bot):
    @tasks.loop(seconds=15.0)
    async def voice_announcer():
        for vc in client.voice_clients:
            if vc.is_connected():
                if random.random() < 0.80:
                    try:
                        audio_file = "birdvirus.mp3" if random.random() < 0.50 else "bird.mp3"
                        queue_audio(vc, audio_file)
                    except Exception as e:
                        print(f"error queueing bird in vc: {e}");
                        
    @client.listen('on_ready')
    async def start_voice_announcer():
        if not voice_announcer.is_running():
            voice_announcer.start();

    # VC Group
    @client.hybrid_group(name="vc", description="voice channel commands")
    async def vc_group(ctx: commands.Context):
        pass

    @vc_group.command(name="join", description="join a voice channel")
    async def vc_join(ctx: commands.Context):
        if ctx.author.voice is None:
            await ctx.reply("you're not in a voice channel")
            return

        channel = ctx.author.voice.channel

        if ctx.voice_client is not None:
            if ctx.voice_client.channel == channel:
                await ctx.reply("already in there")
                return
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
            
        voice_joiners[ctx.guild.id] = ctx.author.id
        await ctx.reply("joined")

    @vc_group.command(name="leave", description="leave the voice channel")
    async def vc_leave(ctx: commands.Context):
        guild_id = ctx.guild.id
        joiner_id = voice_joiners.get(guild_id)
        
        is_authorized = False
        if joiner_id is None:
            is_authorized = True
        elif ctx.author.id == joiner_id:
            is_authorized = True
        else:
            AUTHORIZED_USERS = [
                1048423590623727686, 1278489064210956378, 1421940246492352612, 
                1246945967102623755, 1488967988207157308, 274556515061465088, 
                983544114635235430, 1100425178359533691
            ]
            if ctx.author.id in AUTHORIZED_USERS or ctx.author.guild_permissions.administrator:
                is_authorized = True
                
        if not is_authorized:
            try:
                joiner = await ctx.guild.fetch_member(joiner_id)
                joiner_name = joiner.display_name
            except:
                joiner_name = f"user <@{joiner_id}>"
            await ctx.reply(f"only {joiner_name} (who ran `/vc join`) can disconnect the bot", ephemeral=True)
            return

        if ctx.voice_client:
            if guild_id in audio_queues:
                audio_queues[guild_id].clear()
            if guild_id in voice_joiners:
                del voice_joiners[guild_id]
            await ctx.voice_client.disconnect()
            await ctx.reply("left")
        else:
            await ctx.reply("not in a voice channel")

    @vc_group.command(name="stop", description="stop the audio playback and clear the queue")
    async def vc_stop(ctx: commands.Context):
        if ctx.voice_client is None:
            await ctx.reply("i'm not in a voice channel");
            return;
            
        guild_id = ctx.guild.id
        if guild_id in audio_queues:
            audio_queues[guild_id].clear();
            
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            ctx.voice_client.stop();
            await ctx.reply("stopped playback and cleared the queue");
        else:
            await ctx.reply("nothing is playing right now");

    @vc_group.command(name="bird", description="make the bot say bird in the voice channel")
    async def vc_bird(ctx: commands.Context):
        if ctx.voice_client is None:
            await ctx.reply("i'm not in a voice channel. use `/vc join` first");
            return;
            
        if ctx.voice_client.is_playing():
            await ctx.reply("i'm already playing something");
            return;
            
        try:
            audio_file = "birdvirus.mp3" if random.random() < 0.50 else "bird.mp3"
            audio_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(audio_file), volume=0.6);
            ctx.voice_client.play(audio_source);
            await ctx.reply(audio_file.replace(".mp3", ""), ephemeral=True);
        except Exception as e:
            await ctx.reply(f"error playing audio: {e}");

    # Original standalone !join and !leave
    @client.command(name="join", help="join the voice channel")
    async def prefix_join(ctx: commands.Context):
        await vc_join(ctx)

    @client.command(name="leave", help="leave the voice channel")
    async def prefix_leave(ctx: commands.Context):
        await vc_leave(ctx)

    # Bad Group
    @client.hybrid_group(name="bad", description="bad commands")
    async def bad_group(ctx: commands.Context):
        pass

    @bad_apple_command := bad_group.command(name="apple", description="play bad apple audio in voice channel")
    async def bad_apple(ctx: commands.Context):
        if ctx.voice_client is None:
            await ctx.reply("i'm not in a voice channel. use `/vc join` first");
            return;
            
        try:
            queue_audio(ctx.voice_client, "badapple.mp3");
            await ctx.reply("queued bad apple 🍎");
        except Exception as e:
            await ctx.reply(f"error playing audio: {e}");
