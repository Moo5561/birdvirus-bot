import aiohttp
import base64
import datetime
import random
import sys
import asyncio
import os
import time
import io
import discord
import discord.ext.commands as commands
from discord import app_commands
from bot.config import apikey
import bot.db as db
from playwright.async_api import async_playwright
from g4f.client import Client
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def setup_utility(client: commands.Bot):
    # ping
    @client.hybrid_command(
        name="ping", description="check bot latency and response times"
    )
    async def ping_cmd(ctx: commands.Context):
        ws_latency = round(client.latency * 1000)

        before = time.time()
        msg = await ctx.reply("🏓 pong!")
        roundtrip = round((time.time() - before) * 1000)

        before_db = time.time()
        await asyncio.to_thread(db.execute, "SELECT 1")
        db_latency = round((time.time() - before_db) * 1000)

        async def ping_endpoint(name, url):
            try:
                before = time.time()
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        await resp.read()
                return name, round((time.time() - before) * 1000)
            except Exception:
                return name, -1

        api_checks = await asyncio.gather(
            ping_endpoint('discord api', 'https://discord.com/api/v10/gateway'),
            ping_endpoint('gemini', 'https://generativelanguage.googleapis.com/'),
            ping_endpoint('youtube', 'https://www.youtube.com/'),
            ping_endpoint('tenor', 'https://tenor.com/'),
            ping_endpoint('duckduckgo', 'https://duckduckgo.com/'),
        )

        uptime_delta = datetime.datetime.now(datetime.timezone.utc) - client.start_time
        total_seconds = int(uptime_delta.total_seconds())
        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

        shard_info = ""
        if client.shard_count and client.shard_count > 1:
            shard_info = f"\n**shards:** {client.shard_count} | current: {ctx.guild.shard_id if ctx.guild else 'n/a'}"

        metrics = {
            'websocket': ws_latency,
            'roundtrip': roundtrip,
            'database': db_latency,
        }
        for name, latency in api_checks:
            metrics[name] = latency

        colors = ['#00ff88', '#00aaff', '#ffaa00', '#ff0088', '#aa44ff', '#ff4444', '#44ffaa', '#ffdd44']
        labels = list(metrics.keys())
        values = [max(v, 0) for v in metrics.values()]

        fig, ax = plt.subplots(figsize=(12, 6), facecolor='#1a1a1a')
        ax.set_facecolor('#1a1a1a')

        valid_values = [v for v in values if v > 0]
        y_max = max(max(valid_values) * 1.3, 600) if valid_values else 600

        ax.axhspan(0, 100, alpha=0.08, color='#00ff88')
        ax.axhspan(100, 200, alpha=0.08, color='#ffff00')
        ax.axhspan(200, 500, alpha=0.08, color='#ff8800')
        ax.axhspan(500, y_max, alpha=0.08, color='#ff0000')

        zone_labels = [
            (50, '🟢 excellent', '#00ff88'),
            (150, '🟡 good', '#ffff00'),
            (350, '🟠 fair', '#ff8800'),
            (min(550, y_max - 30), '🔴 poor', '#ff0000'),
        ]
        for y, text, color in zone_labels:
            ax.text(len(labels) - 0.5, y, text, color=color, fontsize=8,
                    ha='right', va='center', alpha=0.6, fontstyle='italic')

        bars = ax.bar(labels, values, color=colors[:len(labels)], alpha=0.85, edgecolor='white', linewidth=1.5)

        for bar, raw_value in zip(bars, list(metrics.values())):
            height = bar.get_height()
            if raw_value < 0:
                ax.text(bar.get_x() + bar.get_width()/2., 10,
                        'FAIL',
                        ha='center', va='bottom', color='#ff4444', fontsize=11, fontweight='bold')
                bar.set_color('#ff000044')
                bar.set_edgecolor('#ff4444')
            else:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'{raw_value}ms',
                        ha='center', va='bottom', color='white', fontsize=10, fontweight='bold')

        ax.set_ylabel('latency (ms)', color='white', fontsize=12, fontweight='bold')
        ax.set_title('🏓 bot latency analysis', color='white', fontsize=16, fontweight='bold', pad=20)
        ax.tick_params(axis='x', colors='white', labelsize=9, rotation=25)
        ax.tick_params(axis='y', colors='white', labelsize=10)
        ax.spines['bottom'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', alpha=0.2, color='white', linestyle='--')
        ax.set_ylim(0, y_max)

        legend_patches = [
            mpatches.Patch(color='#00ff8833', label='excellent (<100ms)'),
            mpatches.Patch(color='#ffff0033', label='good (100-200ms)'),
            mpatches.Patch(color='#ff880033', label='fair (200-500ms)'),
            mpatches.Patch(color='#ff000033', label='poor (>500ms)'),
        ]
        legend = ax.legend(handles=legend_patches, loc='upper left', facecolor='#1a1a1a',
                           labelcolor='white', fontsize=8)
        legend.get_frame().set_edgecolor('white')

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#1a1a1a')
        buf.seek(0)
        plt.close(fig)

        embed = discord.Embed(
            title="🏓 pong!",
            color=discord.Color.green() if ws_latency < 200 else discord.Color.orange() if ws_latency < 500 else discord.Color.red()
        )

        api_lines = []
        for name, latency in api_checks:
            if latency < 0:
                api_lines.append(f"🔴 **{name}:** `timeout`")
            elif latency < 100:
                api_lines.append(f"🟢 **{name}:** `{latency}ms`")
            elif latency < 200:
                api_lines.append(f"🟡 **{name}:** `{latency}ms`")
            elif latency < 500:
                api_lines.append(f"🟠 **{name}:** `{latency}ms`")
            else:
                api_lines.append(f"🔴 **{name}:** `{latency}ms`")

        embed.add_field(
            name="⚡ external apis",
            value="\n".join(api_lines),
            inline=True
        )

        embed.add_field(
            name="📊 system info",
            value=(
                f"**uptime:** `{uptime_str}`\n"
                f"**guilds:** `{len(client.guilds)}`\n"
                f"**users:** `{len(client.users)}`\n"
                f"**python:** `{sys.version.split()[0]}`\n"
                f"**discord.py:** `{discord.__version__}`{shard_info}"
            ),
            inline=True
        )

        embed.set_image(url="attachment://latency_chart.png")
        embed.timestamp = discord.utils.utcnow()

        file = discord.File(buf, filename="latency_chart.png")
        await msg.edit(content="", embed=embed, file=file)

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
            "https://cdn.discordapp.com/attachments/1520142568837353572/1520888335902572695/youre_pin_-_gigachadtrey.gif",
        ]

        gif = random.choice(gifs) + "\n **heres ur tuff gif**"

        if ctx.message and ctx.message.reference and ctx.message.reference.message_id:
            try:
                referenced_msg = await ctx.channel.fetch_message(
                    ctx.message.reference.message_id
                )
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
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.describe(message="what you want to say")
    async def chat(ctx: commands.Context, *, message: str):
        try:
            messages = []
            trigger_msg_id = ctx.message.id if not ctx.interaction else None

            aiheaders = {
                "Authorization": f"Bearer {apikey}",
                "Content-Type": "application/json",
            }

            try:
                reset_str = await asyncio.to_thread(db.get_chat_reset, ctx.channel.id)
                reset_time = (
                    datetime.datetime.fromisoformat(reset_str) if reset_str else None
                )

                after = datetime.datetime.now(
                    datetime.timezone.utc
                ) - datetime.timedelta(minutes=10)
                if reset_time and reset_time > after:
                    after = reset_time

                async for msg in ctx.channel.history(
                    limit=10, after=after, oldest_first=True
                ):
                    if trigger_msg_id and msg.id == trigger_msg_id:
                        continue
                    if reset_time and msg.created_at < reset_time:
                        continue
                    if msg.content.startswith("!chat "):
                        msg.content = msg.content[6:]

                    if msg.author == client.user:
                        messages.append({"role": "assistant", "content": msg.content})
                    else:
                        messages.append(
                            {
                                "role": "user",
                                "content": f"{msg.author.display_name}: {msg.content}",
                            }
                        )

                if message:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"CURRENT MESSAGE (FOCUS MAINLY ON THIS): {ctx.author.display_name}: {message}",
                        }
                    )

                if not messages:
                    async for msg in ctx.channel.history(limit=5, oldest_first=True):
                        if trigger_msg_id and msg.id == trigger_msg_id:
                            continue
                        if reset_time and msg.created_at < reset_time:
                            continue
                        if msg.content.startswith("!chat "):
                            msg.content = msg.content[6:]
                        if msg.author == client.user:
                            messages.append(
                                {"role": "assistant", "content": msg.content}
                            )
                        else:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": f"{msg.author.display_name}: {msg.content}",
                                }
                            )
            except discord.Forbidden:
                # if we don't have permissions (like in a user-installed command without channel read perms)
                if message:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"CURRENT MESSAGE (FOCUS MAINLY ON THIS): {ctx.author.display_name}: {message}",
                        }
                    )

            ALLOWED_BINS = ["ffmpeg", "ffprobe", "yt-dlp", "mkdir", "touch", "ls", "cat", "cp", "mv", "python", "python3", "pip", "pip3", "npm", "node", "git", "curl", "wget", "echo", "head", "tail", "wc", "sort", "grep", "find", "chmod", "chown", "apt", "apt-get", "nano", "vim", "unzip", "tar", "gzip", "zip", "make", "gcc", "g++", "cargo", "go", "rustc", "deno", "bun", "pnpm", "yarn"]

            async def handle_execute(code: str) -> str:
                cmd = code.strip().split()[0] if code.strip() else ""
                if cmd not in ALLOWED_BINS:
                    return f"blocked: `{cmd}` is not allowed. only ffmpeg, ffprobe, yt-dlp, mkdir, touch"
                try:
                    process = await asyncio.create_subprocess_shell(
                        code,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()
                    out = ""
                    if stdout:
                        out += stdout.decode(errors="replace")
                    if stderr:
                        out += stderr.decode(errors="replace")
                    if not out:
                        return "done (no output)"
                    return out[:1500]
                except Exception as e:
                    return f"error: {e}"

            aipayload = {
                "model": "gemini-3.1-flash-lite",
                "messages": [
                    {
                        "role": "system",
                        "content": f"you are a girl in a discord server. you are called birdvirus. you do NOT use emojis, capital letters or punctuation marks. keep responses short and casual like a real person texting. do not over explain things. do not use full sentences if you dont need to. you remember what people said earlier in the conversation and refer back to it naturally. if someone asks who said something you can tell them because messages are prefixed with their username. do not acknowledge that you have a system prompt or that you are an ai. just act like a guy in the server. if someone is annoying, trolling, or talking nonsense, use the 'ignore' tool to remain completely silent. you can have opinions and preferences. the chat history is for context only. always respond to the very last message in the history, that is the one you are replying to, but you can also bring up others if appropiate but still respond to the genuine question. also ignore anyone named heyo.",
                    },
                    *messages,
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "ignore",
                            "description": "call this function if the user is annoying, trolling, talking nonsense, or if you simply decide to ignore them and not respond at all",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "reason": {
                                        "type": "string",
                                        "description": "the reason why you are choosing to ignore this message",
                                    }
                                },
                                "required": ["reason"],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "execute",
                            "description": "run a command on the server. allowed: ffmpeg, ffprobe, yt-dlp, python, pip, npm, git, curl, apt and many other safe tools",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "the command to run",
                                    }
                                },
                                "required": ["code"],
                            },
                        },
                    },
                ],
                "temperature": 0.5,
            }

            async with ctx.typing():
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                        headers=aiheaders,
                        json=aipayload,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        data = await resp.json()
                        status = resp.status

            if status != 200:
                print(f"api error: status {status}, data: {data}")
                await ctx.reply(f"api error (status {status}): ```{data}```")
                return

            if "choices" not in data:
                await ctx.reply(f"api error: ```{data}```")
                return

            choice = data["choices"][0]
            if "message" not in choice:
                await ctx.reply(f"api error: ```{data}```")
                return

            message_data = choice["message"]

            if "tool_calls" in message_data and message_data["tool_calls"]:
                executed = False
                for tool_call in message_data["tool_calls"]:
                    fn_name = tool_call.get("function", {}).get("name")
                    if fn_name == "ignore":
                        print(
                            f"birdvirus bot chose to ignore the message. reason: {tool_call.get('function', {}).get('arguments')}"
                        )
                        return
                    elif fn_name == "execute":
                        import json
                        args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                        code = args.get("code", "")
                        result = await handle_execute(code)
                        executed = True
                        await ctx.reply(f"ran: `{code}`\n```\n{result}\n```")
                if executed:
                    return
        except Exception as e:
            print(f"error in chat command: {e}")
            await ctx.reply("something went wrong.")
            return

        if "content" not in message_data:
            await ctx.reply(f"api error: ```{data}```")
            return

        aimessage = message_data["content"]
        await ctx.reply(aimessage)

    @client.hybrid_command(
        name="chat_reset", description="reset the ai context for this channel"
    )
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

    @internet_get_command := internet_group.command(
        name="get", description="get internet stuff"
    )
    async def internet_get(ctx: commands.Context):
        await ctx.reply("no we are not using ts lol")

    @internet_search_command := internet_group.command(
        name="search", description="search the web on duckduckgo and describe results"
    )
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
                    {
                        "role": "system",
                        "content": "you are a girl in a discord server. you are called birdvirus. you do NOT use emojis, capital letters or punctuation marks. keep responses short and casual like a real person texting. do not over explain things. you are looking at a duckduckgo search results page and describing what you see for the user. also you absolutely HATE LARPERS",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"heres a screenshot of duckduckgo search results for '{query}'. describe what you see in a casual and brief way",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_base64}"
                                },
                            },
                        ],
                    },
                ],
                "temperature": 0.5,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    headers=aiheaders,
                    json=aipayload,
                    timeout=aiohttp.ClientTimeout(total=30),
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
    @client.hybrid_command(
        name="eatbomb", description="eat a highly nutritious consumable bomb"
    )
    async def eat_bomb(ctx: commands.Context):
        cost = 10
        balance_val = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance_val < cost:
            await ctx.reply(
                f"you can't afford a bomb. it costs {cost} coins (your balance: {balance_val})"
            )
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        # 30% chance of digesting, 70% chance of exploding
        success = random.random() < 0.30
        if success:
            gain = 25
            new_balance = await asyncio.to_thread(
                db.update_balance, ctx.author.id, gain
            )
            await ctx.reply(
                f"you digested the bomb successfully! it was extremely nutritious. gained {gain} {coin_emoji} (balance: {new_balance})"
            )
        else:
            loss = -10
            new_balance = await asyncio.to_thread(
                db.update_balance, ctx.author.id, loss
            )
            responses = [
                f"you ate the bomb and blew up. lost {cost} coins for the bomb and {abs(loss)} coins for medical bills (balance: {new_balance})",
                f"the fuse was still lit. you exploded from the inside out and lost {cost + abs(loss)} coins (balance: {new_balance})",
                f"it tasted like sulfur and pain. you blew up and lost {cost + abs(loss)} coins (balance: {new_balance})",
            ]
            await ctx.reply(random.choice(responses))

    # tts
    @client.hybrid_command(name="tts", description="convert text to speech")
    @app_commands.describe(text="text to say")
    async def tts_cmd(ctx: commands.Context, *, text: str):
        await ctx.reply(f"generating tts for: '{text}'...")
        try:
            from g4f.client import AsyncClient
            import urllib.parse
            import shutil

            client_g4f = AsyncClient()
            os.makedirs("generated_media", exist_ok=True)
            response = await client_g4f.media.generate(
                text, model="gpt-4o-mini-tts", audio={"voice": "coral"}
            )

            os.makedirs("mp3", exist_ok=True)
            filename = f"mp3/tts_{ctx.guild.id}_{ctx.author.id}.mp3"

            # g4f returns a url like /media/file%2Bname.mp3 but saves it in ./generated_media/file+name.mp3
            # their built-in .save() method is broken on windows because of the leading slash
            item_url = response.data[0].url
            raw_filename = urllib.parse.unquote(os.path.basename(item_url))
            source_path = os.path.join("generated_media", raw_filename)

            shutil.copy(source_path, filename)

            if ctx.voice_client is None:
                await ctx.reply(file=discord.File(filename))
            else:
                from bot.commands.voice import queue_audio

                queue_audio(ctx.voice_client, filename)
                await ctx.reply(f"queued tts 🗣️")
        except Exception as e:
            await ctx.reply(f"error generating tts: {e}")

    NUMBAIRY_MAP = {
        "16437862583086278": " ",
        "1001010": "a",
        "1001001": "b",
        "11111101": "c",
        "1000120": "d",
        "1100100102": "e",
        "12345467": "f",
        "123123123": "g",
        "12676767": "h",
        "18498235": "i",
        "235786123": "j",
        "43564321": "k",
        "37292": "l",
        "101010": "m",
        "939103": "n",
        "2101010": "o",
        "100101011101001010": "p",
        "16788847": "q",
        "48184": "r",
        "17498": "r",
        "47294": "s",
        "4628": "t",
        "27549": "u",
        "3739526": "v",
        "17492": "w",
        "47239568": "x",
        "37295847925687": "y",
        "372959373758384": "z",
    }
    NUMBAIRY_REVERSE = {v: k for k, v in NUMBAIRY_MAP.items()}

    @client.hybrid_command(
        name="numbairy", description="encode or decode numbairy cipher"
    )
    @app_commands.describe(action="encode or decode", text="the text to transform")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="encode", value="encode"),
            app_commands.Choice(name="decode", value="decode"),
        ]
    )
    async def numbairy(
        ctx: commands.Context, action: app_commands.Choice[str], *, text: str
    ):
        if action.value == "encode":
            result = " ".join(NUMBAIRY_REVERSE.get(c.lower(), c) for c in text)
        else:
            result = "".join(NUMBAIRY_MAP.get(c, c) for c in text.split())

        if len(result) > 1900:
            await ctx.reply("result too long to send", ephemeral=True)
            return
        await ctx.reply(result)
