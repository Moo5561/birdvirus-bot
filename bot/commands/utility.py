import aiohttp
import base64
import datetime
import random
import sys
import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
from bot.config import apikey
import bot.db as db
from playwright.async_api import async_playwright

def setup_utility(client: commands.Bot):
    # ping
    @client.hybrid_command(name="ping", description="pong :p")
    async def ping_cmd(ctx: commands.Context):
        await ctx.reply("pong :p")

    # gif
    @client.hybrid_command(name="gif", description="get a free cool gif from my gifs")
    async def gif_cmd(ctx: commands.Context):
        gifs = [
            "https://cdn.discordapp.com/attachments/1366521106940559470/1499180770500280320/image0.gif ", 
            "https://cdn.discordapp.com/attachments/1478830458950127797/1499169563064008804/togif.30a22110.gif", 
            "https://cdn.discordapp.com/attachments/1474959610564841706/1517008268487299092/attachment.gif",
            "https://tenor.com/view/mango-bird-gif-14282880132606879525",
            "https://tenor.com/view/joe-coin-joe-coin-emotiguy-emoti-guy-gif-5950636071310089815", 
            "https://tenor.com/view/boom-boom-cat-boom-cat-nuke-nuclear-cat-boomba-cat-gif-7123677201497573048", 
            "https://cdn.discordapp.com/attachments/1520142568837353572/1520888335902572695/youre_pin_-_gigachadtrey.gif" 
        ]
        
        gif = random.choice(gifs) + "\n **heres ur tuff gif**"
        
        if ctx.message and ctx.message.reference and ctx.message.reference.message_id:
            try:
                referenced_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                await referenced_msg.reply(gif)
                try:
                    await ctx.message.delete()
                except discord.Forbidden:
                    pass
                return
            except Exception as e:
                print(f"error replying to referenced message: {e}")
                
        await ctx.reply(gif)

    # version
    @client.hybrid_command(name="version", description="show bot version and commit")
    async def version_cmd(ctx: commands.Context):
        host = "unknown"
        if "--host" in sys.argv:
            try:
                host = sys.argv[sys.argv.index("--host") + 1]
            except IndexError:
                pass
                
        try:
            with open("version.txt", "r") as f:
                content = f.read().strip()
            
            await ctx.reply(f"birdvirus bot\n{content}\ncurrent host: `{host}`")
        except Exception:
            await ctx.reply(f"birdvirus bot\ncommit: unknown\ncurrent host: `{host}`")

    # chat
    @client.hybrid_command(name="chat", description="chat with the birdvirus bot")
    @app_commands.describe(message="what you want to say")
    async def chat(ctx: commands.Context, *, message: str):
        messages = []
        trigger_msg_id = ctx.message.id if not ctx.interaction else None

        aiheaders = {
            "Authorization": f"Bearer {apikey}",
            "Content-Type": "application/json",
        }

        reset_str = await asyncio.to_thread(db.get_chat_reset, ctx.channel.id)
        reset_time = datetime.datetime.fromisoformat(reset_str) if reset_str else None

        after = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
        if reset_time and reset_time > after:
            after = reset_time

        async for msg in ctx.channel.history(limit=10, after=after, oldest_first=True):
            if trigger_msg_id and msg.id == trigger_msg_id:
                continue
            if reset_time and msg.created_at < reset_time:
                continue
            if msg.content.startswith("!chat "):
                msg.content = msg.content[6:]

            if msg.author == client.user:
                messages.append({"role": "assistant", "content": msg.content})
            else:
                messages.append({"role": "user", "content": f"{msg.author.display_name}: {msg.content}"})

        if message:
            messages.append({"role": "user", "content": f"{ctx.author.display_name}: {message}"})

        if not messages:
            async for msg in ctx.channel.history(limit=5, oldest_first=True):
                if trigger_msg_id and msg.id == trigger_msg_id:
                    continue
                if reset_time and msg.created_at < reset_time:
                    continue
                if msg.content.startswith("!chat "):
                    msg.content = msg.content[6:]
                if msg.author == client.user:
                    messages.append({"role": "assistant", "content": msg.content})
                else:
                    messages.append({"role": "user", "content": f"{msg.author.display_name}: {msg.content}"})

        aipayload = {
            "model": "gemini-3.1-flash-lite",
            "messages": [
                {"role": "system", "content": f"you are a dude in a discord server. you are called birdvirus. you do NOT use emojis, capital letters or punctuation marks. keep responses short and casual like a real person texting. do not over explain things. do not use full sentences if you dont need to. you remember what people said earlier in the conversation and refer back to it naturally. if someone asks who said something you can tell them because messages are prefixed with their username. do not acknowledge that you have a system prompt or that you are an ai. just act like a guy in the server. if someone is annoying just be dry or ignore them. you can have opinions and preferences. you are not helpful on purpose you just happen to help sometimes. the chat history is for context only. always respond to the very last message in the history, that is the one you are replying to, but you can also bring up others if appropiate but still respond to the genuine question. also dont respond to anyone with zombie in there name"},
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
        
        aimessage = data["choices"][0]["message"]["content"]
        await ctx.reply(aimessage)

    @client.hybrid_command(name="chat_reset", description="reset the ai context for this channel")
    async def chat_reset(ctx: commands.Context):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await asyncio.to_thread(db.set_chat_reset, ctx.channel.id, now)
        await ctx.reply("ai context wiped for this channel.", ephemeral=True)

    # say command
    @client.hybrid_command(name="say", description="make the bot say something")
    @app_commands.describe(message="what you want the bot to say")
    async def say(ctx: commands.Context, message: str):
        await asyncio.to_thread(db.log_say, ctx.author.id, ctx.author.name, message)
        if ctx.interaction:
            await ctx.interaction.response.send_message("sent", ephemeral=True)
            await ctx.channel.send(message)
        else:
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass
            await ctx.send(message)

    # Internet Group
    @client.hybrid_group(name="internet", description="internet commands")
    async def internet_group(ctx: commands.Context):
        pass

    @internet_get_command := internet_group.command(name="get", description="get internet stuff")
    async def internet_get(ctx: commands.Context):
        await ctx.reply("no we are not using ts lol")

    @internet_search_command := internet_group.command(name="search", description="search the web on duckduckgo and describe results")
    @app_commands.describe(query="what to search for")
    async def internet_search(ctx: commands.Context, query: str):
        async with ctx.typing():
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto("https://duckduckgo.com/")
                    await page.fill('input[name="q"]', query)
                    await page.press('input[name="q"]', "Enter")
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_timeout(1000)
                    screenshot = await page.screenshot(type="png")
                    await browser.close()
            except Exception as e:
                await ctx.reply(f"browser error: {e}")
                return

            img_base64 = base64.b64encode(screenshot).decode("utf-8")

            aiheaders = {
                "Authorization": f"Bearer {apikey}",
                "Content-Type": "application/json",
            }

            aipayload = {
                "model": "gemini-3.1-flash-lite",
                "messages": [
                    {"role": "system", "content": "you are a dude in a discord server. you are called birdvirus. you do NOT use emojis, capital letters or punctuation marks. keep responses short and casual like a real person texting. do not over explain things. you are looking at a duckduckgo search results page and describing what you see for the user."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"heres a screenshot of duckduckgo search results for '{query}'. describe what you see in a casual and brief way"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                        ]
                    }
                ],
                "temperature": 0.5,
            }

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

        aimessage = data["choices"][0]["message"]["content"]
        await ctx.reply(aimessage)

    # eat_bomb
    @client.hybrid_command(name="eatbomb", description="eat a highly nutritious consumable bomb")
    async def eat_bomb(ctx: commands.Context):
        cost = 10
        balance_val = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance_val < cost:
            await ctx.reply(f"you can't afford a bomb. it costs {cost} coins (your balance: {balance_val})")
            return
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        
        # 30% chance of digesting, 70% chance of exploding
        success = random.random() < 0.30
        if success:
            gain = 25
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, gain)
            await ctx.reply(f"you digested the bomb successfully! it was extremely nutritious. gained {gain} {coin_emoji} (balance: {new_balance})")
        else:
            loss = -10
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, loss)
            responses = [
                f"you ate the bomb and blew up. lost {cost} coins for the bomb and {abs(loss)} coins for medical bills (balance: {new_balance})",
                f"the fuse was still lit. you exploded from the inside out and lost {cost + abs(loss)} coins (balance: {new_balance})",
                f"it tasted like sulfur and pain. you blew up and lost {cost + abs(loss)} coins (balance: {new_balance})"
            ]
            await ctx.reply(random.choice(responses))
