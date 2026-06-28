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
    print(f'the bird has awoken as {client.user}')

client.run(token)

# add more soon idk
