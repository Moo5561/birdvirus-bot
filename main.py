import discord
from dotenv import load_dotenv
import discord.ext.commands
import os

# do the env variables
load_dotenv()
token = os.getenv('KEY')

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print('the bird has awoken.')

# add more soon idk
