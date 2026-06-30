import discord
import discord.ext.commands as commands

def setup(client: commands.Bot):
    @client.event
    async def on_ready():
        print(f'the bird has awoken as {client.user}')
        try:
            synced = await client.tree.sync()
            print(f"synced {len(synced)} command(s) with discord")
        except Exception as e:
            print(f"error syncing command tree: {e}")

    @client.listen('on_message')
    async def on_message(message: discord.Message):
        if message.author == client.user:
            return
            
        if "67" in message.content:
            if message.guild and message.guild.voice_client:
                vc = message.guild.voice_client
                if vc.is_connected() and not vc.is_playing():
                    try:
                        vc.play(discord.FFmpegPCMAudio("bird.mp3"))
                    except Exception as e:
                        print(f"error playing bird on 67: {e}")

    @client.event
    async def on_command_error(ctx: commands.Context, error):
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            await ctx.reply("you don't have permission to do that", ephemeral=True)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"slow down dude wait {error.retry_after:.1f} seconds", ephemeral=True)
        else:
            print(f"command error: {error}")
