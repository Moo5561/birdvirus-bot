import aiohttp
import base64
import datetime
import random
import asyncio
import discord
import discord.ext.commands as commands
from discord.ext import tasks
from discord import app_commands
from bot.config import apikey
import bot.db as db
from playwright.async_api import async_playwright

def draw_card():
    suits = ['♠', '♥', '♦', '♣']
    values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    return (random.choice(values), random.choice(suits))

def calculate_hand(hand):
    value = 0
    aces = 0
    for card, suit in hand:
        if card in ['J', 'Q', 'K']:
            value += 10
        elif card == 'A':
            value += 11
            aces += 1
        else:
            value += int(card)
            
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value

def is_admin():
    async def predicate(ctx: commands.Context):
        AUTHORIZED_USERS = [
            1048423590623727686, 1278489064210956378, 1421940246492352612, 
            1246945967102623755, 1488967988207157308, 274556515061465088, 
            983544114635235430, 1100425178359533691
        ]
        if ctx.author.id in AUTHORIZED_USERS:
            return True;

        admin_ids_str = await asyncio.to_thread(db.get_config, "admin_ids");
        if admin_ids_str:
            try:
                admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()];
                if ctx.author.id in admin_ids:
                    return True;
            except Exception as e:
                print(f"error parsing admin_ids config: {e}");
                
        if ctx.author.guild_permissions.administrator:
            return True;
            
        return False;
    return commands.check(predicate);

class BlackjackView(discord.ui.View):
    def __init__(self, ctx, bet, player_hand, dealer_hand, coin_emoji):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.bet = bet
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.coin_emoji = coin_emoji
        self.message = None

    def get_embed(self, hide_dealer=True, status="game in progress"):
        embed = discord.Embed(
            title="blackjack",
            color=0x2f3136 if status == "game in progress" else (0x2ecc71 if "won" in status or "blackjack" in status else 0xe74c3c if "lost" in status or "bust" in status else 0x95a5a6)
        )
        
        player_cards = " ".join([f"`{val}{suit}`" for val, suit in self.player_hand])
        player_score = calculate_hand(self.player_hand)
        embed.add_field(name=f"your hand (score: {player_score})", value=player_cards, inline=False)
        
        if hide_dealer:
            dealer_cards = f"`{self.dealer_hand[0][0]}{self.dealer_hand[0][1]}` `?`"
            embed.add_field(name="dealer hand", value=dealer_cards, inline=False)
        else:
            dealer_cards = " ".join([f"`{val}{suit}`" for val, suit in self.dealer_hand])
            dealer_score = calculate_hand(self.dealer_hand)
            embed.add_field(name=f"dealer hand (score: {dealer_score})", value=dealer_cards, inline=False)
            
        embed.add_field(name="bet", value=f"{self.bet} {self.coin_emoji}", inline=True)
        embed.set_footer(text=status)
        return embed

    async def start(self, ctx):
        self.message = await ctx.reply(embed=self.get_embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("this is not your game dude", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="hit", style=discord.ButtonStyle.blurple)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player_hand.append(draw_card())
        player_score = calculate_hand(self.player_hand)
        
        if player_score > 21:
            self.stop()
            new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, -self.bet)
            
            for item in self.children:
                item.disabled = True
                
            embed = self.get_embed(hide_dealer=False, status=f"you busted and lost {self.bet} {self.coin_emoji} (balance: {new_balance})")
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="stand", style=discord.ButtonStyle.green)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        
        while calculate_hand(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())
            
        player_score = calculate_hand(self.player_hand)
        dealer_score = calculate_hand(self.dealer_hand)
        
        if dealer_score > 21:
            new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, self.bet)
            status_text = f"dealer busted! you won {self.bet} {self.coin_emoji} (balance: {new_balance})"
        elif player_score > dealer_score:
            new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, self.bet)
            status_text = f"you won {self.bet} {self.coin_emoji} (balance: {new_balance})"
        elif player_score < dealer_score:
            new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, -self.bet)
            status_text = f"you lost {self.bet} {self.coin_emoji} (balance: {new_balance})"
        else:
            status_text = "push! it's a tie. bet refunded"
            
        for item in self.children:
            item.disabled = True
            
        embed = self.get_embed(hide_dealer=False, status=status_text)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        
        while calculate_hand(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())
            
        player_score = calculate_hand(self.player_hand)
        dealer_score = calculate_hand(self.dealer_hand)
        
        if dealer_score > 21 or player_score > dealer_score:
            new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, self.bet)
            status_text = f"timed out but you won {self.bet} {self.coin_emoji} (balance: {new_balance})"
        elif player_score < dealer_score:
            new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, -self.bet)
            status_text = f"timed out and lost {self.bet} {self.coin_emoji} (balance: {new_balance})"
        else:
            status_text = "timed out - pushed (bet refunded)"
            
        embed = self.get_embed(hide_dealer=False, status=status_text)
        try:
            await self.message.edit(embed=embed, view=self)
        except:
            pass

audio_queues = {}

def setup(client: commands.Bot):
    def play_next(error, vc, guild_id):
        if error:
            print(f"player error: {error}")
            
        if guild_id in audio_queues and len(audio_queues[guild_id]) > 0:
            source = audio_queues[guild_id].pop(0)
            vc.play(discord.FFmpegPCMAudio(source), after=lambda e: play_next(e, vc, guild_id))

    def queue_audio(vc, source):
        guild_id = vc.guild.id
        if not vc.is_playing():
            vc.play(discord.FFmpegPCMAudio(source), after=lambda e: play_next(e, vc, guild_id))
        else:
            if guild_id not in audio_queues:
                audio_queues[guild_id] = []
            audio_queues[guild_id].append(source)

    @tasks.loop(seconds=15.0)
    async def voice_announcer():
        for vc in client.voice_clients:
            if vc.is_connected():
                if random.random() < 0.80:
                    try:
                        audio_file = "birdvirus.mp3" if random.random() < 0.50 else "bird.mp3"
                        queue_audio(vc, audio_file)
                    except Exception as e:
                        print(f"error queueing bird in vc: {e}");
                        
    @client.listen('on_ready')
    async def start_voice_announcer():
        if not voice_announcer.is_running():
            voice_announcer.start();

    # ping
    @client.hybrid_command(name="ping", description="pong :p")
    async def ping_cmd(ctx: commands.Context):
        await ctx.reply("pong :p")

    # version
    @client.hybrid_command(name="version", description="show bot version and commit")
    async def version_cmd(ctx: commands.Context):
        import sys
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
        now = datetime.datetime.now(datetime.timezone.utc).isoformat();
        await asyncio.to_thread(db.set_chat_reset, ctx.channel.id, now);
        await ctx.reply("ai context wiped for this channel.", ephemeral=True);

    # VC Group
    @client.hybrid_group(name="vc", description="voice channel commands")
    async def vc_group(ctx: commands.Context):
        pass

    @vc_group.command(name="join", description="join a voice channel")
    async def vc_join(ctx: commands.Context):
        if ctx.author.voice is None:
            await ctx.reply("you're not in a voice channel")
            return

        channel = ctx.author.voice.channel

        if ctx.voice_client is not None:
            if ctx.voice_client.channel == channel:
                await ctx.reply("already in there")
                return
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.reply("joined")

    @vc_group.command(name="leave", description="leave the voice channel")
    async def vc_leave(ctx: commands.Context):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.reply("left")
        else:
            await ctx.reply("not in a voice channel")

    @vc_group.command(name="bird", description="make the bot say bird in the voice channel")
    async def vc_bird(ctx: commands.Context):
        if ctx.voice_client is None:
            await ctx.reply("i'm not in a voice channel. use `/vc join` first");
            return;
            
        if ctx.voice_client.is_playing():
            await ctx.reply("i'm already playing something");
            return;
            
        try:
            audio_file = "birdvirus.mp3" if random.random() < 0.50 else "bird.mp3"
            ctx.voice_client.play(discord.FFmpegPCMAudio(audio_file));
            await ctx.reply(audio_file.replace(".mp3", ""), ephemeral=True);
        except Exception as e:
            await ctx.reply(f"error playing audio: {e}");

    # Original standalone !join and !leave
    @client.command(name="join", help="join the voice channel")
    async def prefix_join(ctx: commands.Context):
        await vc_join(ctx)

    @client.command(name="leave", help="leave the voice channel")
    async def prefix_leave(ctx: commands.Context):
        await vc_leave(ctx)

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

    # View Group
    @client.hybrid_group(name="view", description="view logs and other data")
    @is_admin()
    async def view_group(ctx: commands.Context):
        pass

    @view_say_command := view_group.command(name="say", description="see who said what with say")
    @is_admin()
    async def view_say(ctx: commands.Context):
        logs = await asyncio.to_thread(db.get_say_logs, 20)
        if not logs:
            await ctx.reply("no logs found", ephemeral=True)
            return
        
        lines = []
        for user_name, user_id, content, ts in logs:
            try:
                dt = datetime.datetime.fromisoformat(ts)
                formatted_ts = dt.strftime("%Y-%m-%d %H:%M")
            except:
                formatted_ts = ts
            lines.append(f"{user_name} ({user_id}) at {formatted_ts}: {content}")
        
        response_text = "\n".join(lines)
        if len(response_text) > 1900:
            response_text = response_text[:1900] + "\n..."
        
        await ctx.reply(f"### say logs\n{response_text}", ephemeral=True)

    # Clear Group
    @client.hybrid_group(name="clear", description="clear logs and other data")
    @is_admin()
    async def clear_group(ctx: commands.Context):
        pass

    @clear_saylist_command := clear_group.command(name="saylist", description="clear the say logs")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    async def clear_saylist(ctx: commands.Context):
        await asyncio.to_thread(db.clear_say_logs)
        await ctx.reply("say logs cleared", ephemeral=True)

    # Property Group
    @client.hybrid_group(name="property", description="property commands")
    async def property_group(ctx: commands.Context):
        pass

    @property_register_command := property_group.command(name="register", description="register properties thread channel (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="the channel where private property threads will be created")
    async def property_register(ctx: commands.Context, channel: discord.TextChannel = None):
        target_channel = channel or ctx.channel
        await asyncio.to_thread(db.set_config, "property_channel_id", str(target_channel.id))
        await ctx.reply(f"registered {target_channel.mention} for properties")

    @property_buy_command := property_group.command(name="buy", description="buy a private property thread (costs 50 coins)")
    @app_commands.describe(name="desired name for your private thread")
    async def property_buy(ctx: commands.Context, name: str = None):
        channel_id_str = await asyncio.to_thread(db.get_config, "property_channel_id")
        if not channel_id_str:
            await ctx.reply("properties channel has not been registered yet. an admin needs to run `/property register` first")
            return
            
        channel_id = int(channel_id_str)
        property_channel = ctx.guild.get_channel(channel_id)
        if not property_channel:
            await ctx.reply("registered properties channel not found. please re-register")
            return
            
        cost = 50
        balance = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance < cost:
            await ctx.reply(f"you don't have enough coins. a property costs {cost} coins (your balance: {balance})")
            return
            
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, -cost)
        
        thread_name = name or f"{ctx.author.display_name}s property"
        thread_name = thread_name.lower().replace(" ", "-")
        
        try:
            thread = await property_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread
            )
            
            await thread.add_user(ctx.author)
            await asyncio.to_thread(db.add_property, thread.id, ctx.author.id, thread_name)
            
            coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
            await ctx.reply(f"you bought property {thread.mention}! deducted {cost} {coin_emoji} (remaining: {new_balance} {coin_emoji})")
            await thread.send(f"welcome to your private property {ctx.author.mention}! this thread is yours. enjoy")
            
        except Exception as e:
            await asyncio.to_thread(db.update_balance, ctx.author.id, cost)
            await ctx.reply(f"failed to create thread: {e}")

    # Pure Group
    @client.hybrid_group(name="pure", description="pure economy commands")
    async def pure_group(ctx: commands.Context):
        pass

    @pure_chance_command := pure_group.command(name="chance", description="gamble your coins on pure chance")
    @app_commands.describe(bet="amount of coins to bet")
    async def pure_chance(ctx: commands.Context, bet: int):
        if bet <= 0:
            await ctx.reply("bet must be greater than zero")
            return
            
        balance = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance < bet:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {balance})")
            return
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        win = random.choice([True, False])
        
        if win:
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, bet)
            await ctx.reply(f"you won! doubled your bet of {bet} {coin_emoji} (balance: {new_balance})")
        else:
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, -bet)
            await ctx.reply(f"you lost {bet} {coin_emoji} unlucky dude (balance: {new_balance})")

    @pure_blackjack_command := pure_group.command(name="blackjack", description="play a game of blackjack against the dealer")
    @app_commands.describe(bet="the amount of coins to bet")
    async def pure_blackjack(ctx: commands.Context, bet: int):
        if bet <= 0:
            await ctx.reply("bet must be greater than zero")
            return
            
        balance = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance < bet:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {balance})")
            return
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        
        player_hand = [draw_card(), draw_card()]
        dealer_hand = [draw_card(), draw_card()]
        
        player_total = calculate_hand(player_hand)
        dealer_total = calculate_hand(dealer_hand)
        
        if player_total == 21:
            if dealer_total == 21:
                await ctx.reply(f"both got natural blackjack! it's a tie. bet refunded")
            else:
                payout = int(bet * 1.5)
                new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, payout)
                await ctx.reply(f"natural blackjack! you won {payout} {coin_emoji} (balance: {new_balance})")
            return

        view = BlackjackView(ctx, bet, player_hand, dealer_hand, coin_emoji)
        await view.start(ctx)

    @pure_slots_command := pure_group.command(name="slots", description="play slots and try to win big")
    @app_commands.describe(bet="the amount of coins to bet")
    async def pure_slots(ctx: commands.Context, bet: int):
        if bet <= 0:
            await ctx.reply("bet must be greater than zero");
            return;
            
        balance = await asyncio.to_thread(db.get_balance, ctx.author.id);
        if balance < bet:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {balance})");
            return;
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙");
        emojis = ['🍒', '🍋', '🍇', '🔔', '💎', '7️⃣'];
        
        embed = discord.Embed(title="slots", color=0x2f3136);
        embed.description = "```\n[  🪙  |  🪙  |  🪙  ]\n```\nspinning...";
        message = await ctx.reply(embed=embed);
        
        await asyncio.sleep(0.8);
        spin1 = [random.choice(emojis) for _ in range(3)];
        embed.description = f"```\n[  {spin1[0]}  |  {spin1[1]}  |  {spin1[2]}  ]\n```\nspinning...";
        await message.edit(embed=embed);
        
        await asyncio.sleep(0.8);
        spin2 = [random.choice(emojis) for _ in range(3)];
        embed.description = f"```\n[  {spin2[0]}  |  {spin2[1]}  |  {spin2[2]}  ]\n```\nspinning...";
        await message.edit(embed=embed);
        
        await asyncio.sleep(0.8);
        
        reels = [random.choice(emojis) for _ in range(3)];
        unique_count = len(set(reels));
        
        if unique_count == 1:
            match = reels[0];
            if match == '7️⃣':
                multiplier = 15;
                status = "jackpot! three 7️⃣s!";
            elif match == '💎':
                multiplier = 10;
                status = "mega win! three diamonds!";
            elif match == '🔔':
                multiplier = 7;
                status = "big win! three bells!";
            else:
                multiplier = 5;
                status = f"three of a kind ({match})!";
        elif unique_count == 2:
            if reels[0] == reels[1] or reels[0] == reels[2]:
                pair = reels[0];
            else:
                pair = reels[1];
                
            if pair in ['7️⃣', '💎']:
                multiplier = 2.5;
                status = f"two of a kind ({pair})!";
            else:
                multiplier = 1.5;
                status = f"two of a kind ({pair})!";
        else:
            multiplier = 0;
            status = "no match. unlucky!";
            
        if multiplier > 0:
            net_gain = int(bet * multiplier) - bet;
        else:
            net_gain = -bet;
            
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain);
        
        if net_gain > 0:
            status_text = f"{status}\nyou won {net_gain} {coin_emoji}! (balance: {new_balance})";
            color = 0xf1c40f if multiplier >= 5 else 0x2ecc71;
        else:
            status_text = f"{status}\nyou lost {bet} {coin_emoji}. unlucky (balance: {new_balance})";
            color = 0xe74c3c;
            
        embed.color = color;
        embed.description = f"```\n[  {reels[0]}  |  {reels[1]}  |  {reels[2]}  ]\n```\n{status_text.lower()}";
        await message.edit(embed=embed);

    @pure_roulette_command := pure_group.command(name="roulette", description="gamble your coins on a roulette wheel spin")
    @app_commands.describe(
        bet="the amount of coins to bet",
        guess="where to bet: red, black, even, odd, high (19-36), low (1-18), or a specific number (0-36)"
    )
    async def pure_roulette(ctx: commands.Context, bet: int, guess: str):
        if bet <= 0:
            await ctx.reply("bet must be greater than zero");
            return;
            
        balance = await asyncio.to_thread(db.get_balance, ctx.author.id);
        if balance < bet:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {balance})");
            return;
            
        guess_clean = guess.strip().lower();
        
        is_number = False;
        target_number = -1;
        try:
            target_number = int(guess_clean);
            if 0 <= target_number <= 36:
                is_number = True;
            else:
                await ctx.reply("number must be between 0 and 36");
                return;
        except ValueError:
            pass;
            
        valid_bets = ["red", "black", "even", "odd", "high", "low"];
        if not is_number and guess_clean not in valid_bets:
            await ctx.reply("invalid guess. choose red, black, even, odd, high, low, or a number from 0 to 36");
            return;
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙");
        red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36};
        
        embed = discord.Embed(title="roulette", color=0x2f3136);
        embed.description = "spinning the wheel...";
        message = await ctx.reply(embed=embed);
        
        await asyncio.sleep(0.8);
        dummy_spin1 = random.randint(0, 36);
        dummy_color1 = "🟢" if dummy_spin1 == 0 else "🔴" if dummy_spin1 in red_numbers else "⚫";
        embed.description = f"the ball is rolling...\npassing {dummy_color1} {dummy_spin1}...";
        await message.edit(embed=embed);
        
        await asyncio.sleep(0.8);
        dummy_spin2 = random.randint(0, 36);
        dummy_color2 = "🟢" if dummy_spin2 == 0 else "🔴" if dummy_spin2 in red_numbers else "⚫";
        embed.description = f"the ball is slowing down...\npassing {dummy_color2} {dummy_spin2}...";
        await message.edit(embed=embed);
        
        await asyncio.sleep(0.8);
        
        spin_result = random.randint(0, 36);
        if spin_result == 0:
            result_color = "green";
            result_color_emoji = "🟢";
        elif spin_result in red_numbers:
            result_color = "red";
            result_color_emoji = "🔴";
        else:
            result_color = "black";
            result_color_emoji = "⚫";
            
        win = False;
        multiplier = 0;
        
        if is_number:
            if spin_result == target_number:
                win = True;
                multiplier = 36;
        elif guess_clean == "red":
            if result_color == "red":
                win = True;
                multiplier = 2;
        elif guess_clean == "black":
            if result_color == "black":
                win = True;
                multiplier = 2;
        elif guess_clean == "even":
            if spin_result != 0 and spin_result % 2 == 0:
                win = True;
                multiplier = 2;
        elif guess_clean == "odd":
            if spin_result % 2 != 0:
                win = True;
                multiplier = 2;
        elif guess_clean == "high":
            if 19 <= spin_result <= 36:
                win = True;
                multiplier = 2;
        elif guess_clean == "low":
            if 1 <= spin_result <= 18:
                win = True;
                multiplier = 2;
                
        if win:
            net_gain = int(bet * multiplier) - bet;
        else:
            net_gain = -bet;
            
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain);
        
        if win:
            status_text = f"the ball landed on {result_color_emoji} {spin_result}!\nyou won {net_gain} {coin_emoji}! (balance: {new_balance})";
            color = 0x2ecc71;
        else:
            status_text = f"the ball landed on {result_color_emoji} {spin_result}.\nyou lost {bet} {coin_emoji}. unlucky (balance: {new_balance})";
            color = 0xe74c3c;
            
        embed.color = color;
        embed.description = status_text.lower();
        await message.edit(embed=embed);

    # Plinko command
    @client.hybrid_command(name="plinko", description="horse plinko race — drop the horse and win")
    @app_commands.describe(bet="amount of coins to bet")
    async def plinko(ctx: commands.Context, bet: int):
        if bet <= 0:
            await ctx.reply("bet must be greater than zero")
            return

        balance = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance < bet:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {balance})")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        multipliers = [15, 5, 2, 0.5, 2, 5, 15]
        slot_labels = ['💀', '🔴', '🟠', '🟡', '🟠', '🔴', '💀']
        horse_emojis = ['🐎', '🐴', '🦄', '🐴', '🐎']

        pos = 3
        path = [pos]
        for _ in range(7):
            pos += random.choice([-1, 1])
            pos = max(0, min(6, pos))
            path.append(pos)

        final_slot = path[-1]
        multiplier = multipliers[final_slot]

        embed = discord.Embed(title="horse plinko", color=0x2f3136)
        embed.description = "```\n  ⬇️\n```\nthe horses are off..."
        message = await ctx.reply(embed=embed)

        for frame in range(1, 8):
            await asyncio.sleep(0.4)
            rows = []
            for r in range(frame):
                row_pegs = []
                for c in range(7):
                    if c == path[r]:
                        row_pegs.append('🐎')
                    else:
                        row_pegs.append('⚪')
                rows.append(''.join(row_pegs))
            embed.description = "```\n  ⬇️\n" + "\n".join(rows) + "\n```\nracing..."
            await message.edit(embed=embed)

        await asyncio.sleep(0.5)

        slots_row = ''.join([f'[{s}]' for s in slot_labels])
        mults_row = '  '.join([f'{m}x' for m in multipliers])

        net_gain = int(bet * multiplier) - bet
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)

        if net_gain > 0:
            status = f"your horse finished in {slot_labels[final_slot]} ({multiplier}x)\nyou won {net_gain} {coin_emoji} (balance: {new_balance})"
            color = 0xf1c40f if multiplier >= 5 else 0x2ecc71
        elif net_gain == 0:
            status = f"your horse finished in {slot_labels[final_slot]} ({multiplier}x)\nbroke even (balance: {new_balance})"
            color = 0x95a5a6
        else:
            status = f"your horse finished in {slot_labels[final_slot]} ({multiplier}x)\nyou lost {abs(net_gain)} {coin_emoji} (balance: {new_balance})"
            color = 0xe74c3c

        embed.color = color
        rows = []
        for r in range(8):
            row_pegs = []
            for c in range(7):
                if c == path[r]:
                    row_pegs.append('🐎')
                else:
                    row_pegs.append('⚪')
            rows.append(''.join(row_pegs))
        embed.description = "```\n  ⬇️\n" + "\n".join(rows) + f"\n{slots_row}\n{mults_row}\n```\n{status.lower()}"
        await message.edit(embed=embed)

    # Beg command
    @client.hybrid_command(name="beg", description="beg for some coins with low risk")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def beg(ctx: commands.Context):
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        
        success = random.random() < 0.90
        if success:
            amount = random.randint(1, 15)
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, amount)
            
            responses = [
                f"some guy threw {amount} {coin_emoji} at you (balance: {new_balance})",
                f"you found {amount} {coin_emoji} on the floor (balance: {new_balance})",
                f"a kind stranger gave you {amount} {coin_emoji} (balance: {new_balance})",
                f"you did some chores and got paid {amount} {coin_emoji} (balance: {new_balance})"
            ]
            await ctx.reply(random.choice(responses))
        else:
            responses = [
                "someone told you to get a job lol",
                "you got ignored by everyone",
                "the cop told you to move along",
                "someone threw a wet paper towel at you"
            ]
            await ctx.reply(random.choice(responses))

    @beg.error
    async def beg_error(ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"slow down dude wait {error.retry_after:.1f} seconds", ephemeral=True)
        else:
            await ctx.reply(f"error: {error}")

    # Fish command
    @client.hybrid_command(name="fish", description="go fishing to catch some fish and earn coins")
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def fish(ctx: commands.Context):
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        
        fish_types = [
            {"emoji": "🐟", "name": "common fish", "min": 5, "max": 15, "weight": 60},
            {"emoji": "🐡", "name": "rare blowfish", "min": 20, "max": 40, "weight": 25},
            {"emoji": "🦈", "name": "legendary shark", "min": 100, "max": 200, "weight": 5},
            {"emoji": "👢", "name": "old boot", "min": 0, "max": 0, "weight": 10}
        ]
        
        weights = [f["weight"] for f in fish_types]
        caught = random.choices(fish_types, weights=weights, k=1)[0]
        
        if caught["max"] > 0:
            amount = random.randint(caught["min"], caught["max"])
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, amount)
            await ctx.reply(f"you cast your line and caught a {caught['emoji']} {caught['name']}! you sold it for {amount} {coin_emoji} (balance: {new_balance})")
        else:
            await ctx.reply(f"you cast your line and caught a {caught['emoji']} {caught['name']}. it's worthless. better luck next time.")

    @fish.error
    async def fish_error(ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"the fish are scared away. wait {error.retry_after:.1f} seconds to cast again", ephemeral=True)
        else:
            await ctx.reply(f"error: {error}")

    # Balance command
    @client.hybrid_command(name="balance", description="view coin balance")
    @app_commands.describe(user="the user whose balance you want to check")
    async def balance(ctx: commands.Context, user: discord.Member = None):
        target = user or ctx.author
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        bal, bank = await asyncio.to_thread(db.get_balances, target.id)
        
        embed = discord.Embed(
            title=f"Balance - {target.display_name}",
            color=0x3498db
        )
        
        embed.description = f"**Total Balance: **{coin_emoji} `{bal + bank:,}`\n\n**Holding: **💰`{bal:,}`\n**Bank: **🏦`{bank:,}`\n\n-# birdvirus coin in the bank earn interest!"
        
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)
            
        await ctx.reply(embed=embed)

    # EC Group
    @client.hybrid_group(name="ec", description="economy administration commands")
    @is_admin()
    async def ec_group(ctx: commands.Context):
        pass

    @ec_emoji_command := ec_group.command(name="emoji", description="set the economy coin emoji (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(emoji="the emoji representing birdvirus coin")
    async def ec_emoji(ctx: commands.Context, emoji: str):
        await asyncio.to_thread(db.set_config, "coin_emoji", emoji)
        await ctx.reply(f"set economy emoji to {emoji}")

    @ec_reset_command := ec_group.command(name="reset", description="reset a user's balance to 100 (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="the user whose balance to reset")
    async def ec_reset(ctx: commands.Context, user: discord.Member):
        await asyncio.to_thread(db.set_balance, user.id, 100)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"reset {user.display_name}s balance to 100 {coin_emoji}")

    @ec_set_command := ec_group.command(name="set", description="set a user's balance (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="the user whose balance to set", amount="the new balance amount")
    async def ec_set(ctx: commands.Context, user: discord.Member, amount: int):
        if amount < 0:
            await ctx.reply("amount cannot be negative")
            return
        await asyncio.to_thread(db.set_balance, user.id, amount)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"set {user.display_name}s balance to {amount} {coin_emoji}")

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

    @client.hybrid_command(name="eatbomb", description="eat a highly nutritious consumable bomb")
    async def eat_bomb(ctx: commands.Context):
        cost = 10;
        balance = await asyncio.to_thread(db.get_balance, ctx.author.id);
        if balance < cost:
            await ctx.reply(f"you can't afford a bomb. it costs {cost} coins (your balance: {balance})");
            return;
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙");
        
        # 30% chance of digesting, 70% chance of exploding
        success = random.random() < 0.30;
        if success:
            gain = 25;
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, gain);
            await ctx.reply(f"you digested the bomb successfully! it was extremely nutritious. gained {gain} {coin_emoji} (balance: {new_balance})");
        else:
            loss = -10;
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, loss);
            responses = [
                f"you ate the bomb and blew up. lost {cost} coins for the bomb and {abs(loss)} coins for medical bills (balance: {new_balance})",
                f"the fuse was still lit. you exploded from the inside out and lost {cost + abs(loss)} coins (balance: {new_balance})",
                f"it tasted like sulfur and pain. you blew up and lost {cost + abs(loss)} coins (balance: {new_balance})"
            ];
            await ctx.reply(random.choice(responses));
