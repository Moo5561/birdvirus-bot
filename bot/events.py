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

    @client.event
    async def on_command_error(ctx: commands.Context, error):
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            await ctx.reply("you don't have permission to do that", ephemeral=True)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"slow down dude wait {error.retry_after:.1f} seconds", ephemeral=True)
        else:
            print(f"command error: {error}")
