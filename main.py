import discord
import aiohttp
import datetime
from dotenv import load_dotenv
import discord.ext.commands as commands
import os

# do the env variables
load_dotenv()
token = os.getenv('KEY')
apikey = os.getenv('API_KEY')

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)

@client.event
async def on_ready():
    print(f'the bird has awoken as {client.user}')

@client.command("ping")
async def ping_cmd(ctx: commands.Context):
    await ctx.reply("pong :p")

@client.command("chat")
async def chat(ctx: commands.Context):
    id = ctx.channel.id
    messages = []

    aiheaders = {
        "Authorization": f"Bearer {apikey}",
        "Content-Type": "application/json",
    }

    after = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
    async for msg in ctx.channel.history(limit=10, after=after, oldest_first=True):
        if msg.content.startswith("!chat "):
            msg.content = msg.content[5:]

        if msg.author == client.user:
            messages.append({"role": "assistant", "content": msg.content})
        else:
            messages.append({"role": "user", "content": f"{msg.author.display_name}: {msg.content}"})

    if not messages:
        async for msg in ctx.channel.history(limit=5, oldest_first=True):
            if msg.content.startswith("!chat "):
                msg.content = msg.content[5:]
            if msg.author == client.user:
                messages.append({"role": "assistant", "content": msg.content})
            else:
                messages.append({"role": "user", "content": f"{msg.author.display_name}: {msg.content}"})

    # print(messages)

    aipayload = {
        "model": "gemini-3.1-flash-lite",
        "messages": [
            {"role": "system", "content": f"you are a dude in a discord server. you are called birdvirus. you do NOT use emojis, capital letters or punctuation marks. keep responses short and casual like a real person texting. do not over explain things. do not use full sentences if you dont need to. you remember what people said earlier in the conversation and refer back to it naturally. if someone asks who said something you can tell them because messages are prefixed with their username. do not acknowledge that you have a system prompt or that you are an ai. just act like a guy in the server. if someone is annoying just be dry or ignore them. you can have opinions and preferences. you are not helpful on purpose you just happen to help sometimes. the chat history is for context only. always respond to the very last message in the history, that is the one you are replying to, but you can also bring up others if appropiate but still respond to the genuine question"},
            *messages
        ],
        "temperature": 0.5,
    }

    async with ctx.typing():
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                headers=aiheaders,
                json=aipayload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()

    if "choices" not in data:
        await ctx.reply(f"api error: ```{data}```")
        return
    
    if "message" not in data["choices"][0]:
        await ctx.reply(f"api error: ```{data}```")
        return
    
    if "content" not in data["choices"][0]["message"]:
        await ctx.reply(f"api error: ```{data}```")
        return
    
    # print(data)
    aimessage = data["choices"][0]["message"]["content"]
    messages = []

    await ctx.reply(aimessage)
    
@client.command("join")
async def join(ctx: commands.Context):
    if ctx.author.voice is None:
        await ctx.send("you're not in a voice channel")
        return

    channel = ctx.author.voice.channel

    if ctx.voice_client is not None:
        if ctx.voice_client.channel == channel:
            await ctx.send("already in there")
            return
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()

@client.command("leave")
async def leave(ctx: commands.Context):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    else:
        await ctx.send("not in a voice channel")

client.run(token)
