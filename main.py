import discord
import requests
from dotenv import load_dotenv
import discord.ext.commands as commands
import os

# do the env variables
load_dotenv()
token = os.getenv('KEY')
apikey = os.getenv('API_KEY')

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="#", intents=intents)

@client.event
async def on_ready():
    print(f'the bird has awoken as {client.user}')

@commands.command("ping")
async def ping_cmd(ctx: commands.Context):
    await ctx.reply("pong :p")

@commands.command("ask")
async def ask(ctx: commands.Context):
    aiheaders = {
        "Authorization": f"{apikey}",
        "Content-Type": "application/json",
    }

    aipayload = {
        "model": "gemini-3.5-flash",
        "messages": [
            {"role": "system", "content": f"You are a dude in a discord server. you are called birdvirus. you do NOT use emojis, capital letters or punctiation marks. only respond like this 'hi', 'hello', 'no' these are examples you shouldnt output them if the context doesnt match it."},
            {"role": "user", "content": ctx.message.content},
        ],
        "temperature": 0.5,
    }

    resp = await requests.post("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", headers=aiheaders, json=aipayload, timeout=30)
    data = resp.json()
    aimessage = data["choices"][0]["message"]["content"]

    await ctx.reply(aimessage)

client.run(token)
