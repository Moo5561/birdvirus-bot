import discord
import aiohttp
import datetime
import argparse
import discord.ext.commands as commands
import bot.events
import bot.commands
from bot.config import token

parser = argparse.ArgumentParser(description="run the birdvirus bot")
parser.add_argument("--host", required=True, help="who is hosting the bot currently")
args = parser.parse_args()

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(
    command_prefix="!", 
    intents=intents,
    activity=discord.CustomActivity(name=f"hosted by {args.host}")
)

bot.events.setup(client)
bot.commands.setup(client)

client.run(token)
