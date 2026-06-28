import discord.ext.commands as commands

def setup(client: commands.Bot):
    @client.event
    async def on_ready():
        print(f'the bird has awoken as {client.user}')
