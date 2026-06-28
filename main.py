import discord
from dotenv import load_dotenv
import discord.ext.commands as commands
import os

# do the env variables
load_dotenv()
token = os.getenv('KEY')

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="#", intents=intents)

@client.event
async def on_ready():
    print(f'the bird has awoken as {client.user}')

@commands.command("ping")
async def ping_cmd(ctx: commands.Context):
    await ctx.reply("pong :p")


client.run(token)
