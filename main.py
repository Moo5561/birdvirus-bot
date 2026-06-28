import discord
import aiohttp
import datetime
import discord.ext.commands as commands
import bot.events
import bot.commands
from bot.config import token

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="#", intents=intents)

bot.events.setup(client)
bot.commands.setup(client)

client.run(token)
