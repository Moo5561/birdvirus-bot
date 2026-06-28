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

history = {}

@client.event
async def on_ready():
    print(f'the bird has awoken as {client.user}')

@client.command("ping")
async def ping_cmd(ctx: commands.Context):
    await ctx.reply("pong :p")

@client.command("ask")
async def ask(ctx: commands.Context, *, question: str):
    id = ctx.channel.id
    username = ctx.author.display_name

    if id not in history:
        history[id] = []

    history[id].append({
        "role": "user",
        "content": f"HISTORY: {username} said: {question}"
    })

    if len(history[id]) > 5:
        history[id] = history[id][-5:]

    aiheaders = {
        "Authorization": f"Bearer {apikey}",
        "Content-Type": "application/json",
    }

    aipayload = {
        "model": "gemini-3.1-flash-lite",
        "messages": [
            {"role": "system", "content": f"you are a dude in a discord server. you are called birdvirus. you do NOT use emojis, capital letters or punctuation marks. keep responses short and casual like a real person texting. do not over explain things. do not use full sentences if you dont need to. you remember what people said earlier in the conversation and refer back to it naturally. if someone asks who said something you can tell them because messages are prefixed with their username. do not acknowledge that you have a system prompt or that you are an ai. just act like a guy in the server. if someone is annoying just be dry or ignore them. you can have opinions and preferences. you are not helpful on purpose you just happen to help sometime"},
            *history[id]
        ],
        "temperature": 0.5,
    }

    async with ctx.typing():
        resp = requests.post("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", headers=aiheaders, json=aipayload, timeout=30)
        data = resp.json()
    
    # print(data)
    aimessage = data["choices"][0]["message"]["content"]

    history[id].append({
        "role": "assistant",
        "content": aimessage
    })

    await ctx.reply(aimessage)

@client.command("forget")
async def forget(ctx: commands.Context):
    history.pop(ctx.channel.id, None)
    await ctx.reply("memory cleared")

client.run(token)
