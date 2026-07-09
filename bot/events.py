import discord
import random
import asyncio
import discord.ext.commands as commands
import bot.db as db

BANNED_USERS = set()

class UserBanned(commands.CheckFailure):
    pass

def setup(client: commands.Bot):
    @client.event
    async def on_ready():
        global BANNED_USERS
        BANNED_USERS = await asyncio.to_thread(db.get_banned_users)
        # Add the initial hardbanned users to db if not there
        for uid in [924850244435460136, 1205487376105734184, 1494758877898477690, 1316825719820779576, 1318032136976072744, 1208819266338553957]:
            if uid not in BANNED_USERS:
                await asyncio.to_thread(db.ban_user, uid)
                BANNED_USERS.add(uid)
        
        print(f'the bird has awoken as {client.user}')
        try:
            synced = await client.tree.sync()
            print(f"synced {len(synced)} command(s) with discord")
        except Exception as e:
            print(f"error syncing command tree: {e}")

    @client.check
    async def globally_block_banned(ctx):
        if ctx.author.id in BANNED_USERS:
            raise UserBanned()
        return True

    @client.tree.interaction_check
    async def globally_block_banned_interactions(interaction: discord.Interaction):
        if interaction.user.id in BANNED_USERS:
            return False
        return True

    @client.listen('on_message')
    async def on_message(message: discord.Message):
        if message.author == client.user:
            return
        if message.author.id in BANNED_USERS:
            return
            
        if "67" in message.content:
            if message.guild and message.guild.voice_client:
                vc = message.guild.voice_client
                if vc.is_connected():
                    try:
                        from bot.commands import audio_queues
                        guild_id = vc.guild.id
                        source = "mp3/birdvirus.mp3" if random.random() < 0.50 else "mp3/bird.mp3"
                        
                        if not vc.is_playing():
                            def play_next(error, vc_ref, g_id):
                                if error: print(f"player error: {error}")
                                if g_id in audio_queues and len(audio_queues[g_id]) > 0:
                                    src = audio_queues[g_id].pop(0)
                                    vc_ref.play(discord.FFmpegPCMAudio(src), after=lambda e: play_next(e, vc_ref, g_id))
                                    
                            vc.play(discord.FFmpegPCMAudio(source), after=lambda e: play_next(e, vc, guild_id))
                        else:
                            if guild_id not in audio_queues:
                                audio_queues[guild_id] = []
                            audio_queues[guild_id].append(source)
                    except Exception as e:
                        print(f"error queueing bird on 67: {e}")

    @client.event
    async def on_command_error(ctx: commands.Context, error):
        if isinstance(error, UserBanned):
            return
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            await ctx.reply("you don't have permission to do that", ephemeral=True)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"slow down dude wait {error.retry_after:.1f} seconds", ephemeral=True)
        else:
            print(f"command error: {error}")
