import random
import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from datetime import datetime, timedelta
from typing import Literal

JOBS = {
    "janitor": {
        "description": "clean up messes around the server. easy work, low pay.",
        "base_pay": 25,
        "max_level": 10,
        "emoji": "🧹",
        "cooldown_minutes": 5,
        "req_level": 0,
        "titles": ["Apprentice Sweeper", "Mop Wielder", "Stain Master", "Head Custodian", "Sanitation CEO"]
    },
    "chef": {
        "description": "cook meals for the server. requires good memory.",
        "base_pay": 60,
        "max_level": 15,
        "emoji": "🍳",
        "cooldown_minutes": 10,
        "req_level": 3,
        "titles": ["Dishwasher", "Line Cook", "Sous Chef", "Head Chef", "Culinary Master"]
    },
    "developer": {
        "description": "write code and fix bugs. requires brain power.",
        "base_pay": 120,
        "max_level": 20,
        "emoji": "💻",
        "cooldown_minutes": 15,
        "req_level": 5,
        "titles": ["Intern", "Junior Dev", "Mid-Level Dev", "Senior Dev", "Lead Architect"]
    },
    "hacker": {
        "description": "hack into mainframes. high risk, high reward.",
        "base_pay": 250,
        "max_level": 30,
        "emoji": "🕵️",
        "cooldown_minutes": 30,
        "req_level": 10,
        "titles": ["Script Kiddie", "Netrunner", "White Hat", "Black Hat", "Cyber Overlord"]
    },
    "miner": {
        "description": "delve deep into the mines. dodge lava, find diamonds.",
        "base_pay": 150,
        "max_level": 25,
        "emoji": "⛏️",
        "cooldown_minutes": 20,
        "req_level": 7,
        "titles": ["Pebble Kicker", "Dirt Digger", "Cave Explorer", "Ore Specialist", "Dwarf King"]
    },
    "thief": {
        "description": "steal from houses. push your luck, don't get caught.",
        "base_pay": 0,  # dynamic pay based on what they steal
        "max_level": 20,
        "emoji": "🥷",
        "cooldown_minutes": 20,
        "req_level": 8,
        "titles": ["Pickpocket", "Burglar", "Cat Burglar", "Master Thief", "Phantom"]
    }
}

def get_job_title(job_name, level):
    titles = JOBS[job_name]["titles"]
    idx = min(level // 5, len(titles) - 1)
    return titles[idx]

async def trigger_random_event(ctx, job_name, level):
    if random.random() > 0.15:  # 15% chance of random event
        return 0, ""
        
    events = []
    if job_name == "janitor":
        events = [("a pipe burst while you were sweeping! hospital bill:", -50), ("you found a lost wallet in the trash!", 100)]
    elif job_name == "chef":
        events = [("you burned the soup and got fined by the health inspector.", -100), ("a famous food critic loved your meal and tipped you heavily!", 200)]
    elif job_name == "developer":
        events = [("you dropped the production database. your pay was docked.", -150), ("you fixed a critical day-0 bug and got a fat bonus!", 300)]
    elif job_name == "hacker":
        events = [("the fbi tracked your ip. you had to bribe them.", -500), ("you found a crypto wallet with some leftovers.", 600)]
    elif job_name == "miner":
        events = [("a cave-in crushed your equipment. repair cost:", -200), ("you stumbled upon a hidden gold vein!", 400)]
    elif job_name == "thief":
        events = [("the cops spotted your getaway car. pay the impound fee.", -300), ("you fenced some extra jewelry you forgot you had.", 350)]
        
    if not events:
        return 0, ""
        
    event_desc, coin_change = random.choice(events)
    # scale the event impact by level
    coin_change = int(coin_change * (1 + (level * 0.05)))
    
    return coin_change, event_desc

async def handle_job_reward(ctx, job_name, job_data, success, game_message, custom_payout=None, time_taken=None):
    coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
    level = job_data["job_level"]
    
    if not success:
        embed = game_message.embeds[0]
        embed.color = 0xe74c3c
        embed.description += "\n\n**Result:** you failed the task. boss is mad. no pay for you."
        if custom_payout and custom_payout < 0:
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, custom_payout)
            embed.description += f"\nactually, you got fined {abs(custom_payout)} {coin_emoji}. (balance: {new_balance})"
            
        await game_message.edit(embed=embed, view=None)
        time_str = datetime.utcnow().isoformat()
        await asyncio.to_thread(db.update_job_progress, ctx.author.id, 0, time_str)
        return

    job_info = JOBS[job_name]
    
    if custom_payout is not None:
        payout = custom_payout
    else:
        payout = int(job_info["base_pay"] * (1 + (level * 0.1)))
        
    time_bonus_text = ""
    if time_taken is not None:
        adjusted_time = max(0.1, time_taken - ctx.bot.latency)
        par_times = {
            "janitor": 3.0,
            "chef": 8.0,
            "developer": 15.0,
            "hacker": 12.0,
            "miner": 10.0,
            "thief": 10.0
        }
        par_time = par_times.get(job_name, 10.0)
        
        speed_ratio = par_time / adjusted_time
        multiplier = max(0.1, min(3.0, speed_ratio))
        
        payout = int(payout * multiplier)
        
        if multiplier > 1.2:
            time_bonus_text = f"\n⏱️ **speed bonus!** took {adjusted_time:.1f}s (ping adjusted). {multiplier:.2f}x multiplier applied!"
        elif multiplier < 0.8:
            time_bonus_text = f"\n⏱️ **too slow...** took {adjusted_time:.1f}s (ping adjusted). {multiplier:.2f}x penalty applied."
        else:
            time_bonus_text = f"\n⏱️ **average speed.** took {adjusted_time:.1f}s (ping adjusted)."

    xp_gain = random.randint(15, 30)
    
    # Handle random event
    event_payout, event_desc = await trigger_random_event(ctx, job_name, level)
    total_payout = payout + event_payout
    
    new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, total_payout)
    time_str = datetime.utcnow().isoformat()
    level_up, new_level = await asyncio.to_thread(db.update_job_progress, ctx.author.id, xp_gain, time_str)
    
    embed = game_message.embeds[0]
    embed.color = 0x2ecc71
    
    result_text = f"\n\n**Result:** you completed your shift successfully!"
    if time_bonus_text:
        result_text += time_bonus_text
        
    if event_desc:
        result_text += f"\n⚠️ **Random Event:** {event_desc} ({event_payout} {coin_emoji})\n"
        
    result_text += f"\n+ earned a total of {total_payout} {coin_emoji} (balance: {new_balance})\n+ gained {xp_gain} xp"
    
    if level_up:
        new_title = get_job_title(job_name, new_level)
        result_text += f"\n🎉 **promotion!** you are now level {new_level}! ({new_title})"
        
    embed.description += result_text
    await game_message.edit(embed=embed, view=None)


class JanitorGameView(discord.ui.View):
    def __init__(self, ctx, job_data):
        super().__init__(timeout=20.0)
        self.ctx = ctx
        self.job_data = job_data
        self.message = None
        self.start_time = datetime.utcnow()
        self.dirty_spot = random.randint(0, 8)
        
        for i in range(9):
            is_dirty = (i == self.dirty_spot)
            btn = discord.ui.Button(
                label="💩" if is_dirty else "⬜", 
                style=discord.ButtonStyle.gray, 
                custom_id=f"spot_{i}",
                row=i // 3
            )
            btn.callback = self.make_callback(i)
            self.add_item(btn)

    def make_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("not your job buddy.", ephemeral=True)
                return
                
            self.stop()
            time_taken = (datetime.utcnow() - self.start_time).total_seconds()
            success = (idx == self.dirty_spot)
            await interaction.response.defer()
            await handle_job_reward(self.ctx, "janitor", self.job_data, success, self.message, time_taken=time_taken)
        return callback

    async def on_timeout(self):
        try:
            await handle_job_reward(self.ctx, "janitor", self.job_data, False, self.message)
        except:
            pass


class ChefGameView(discord.ui.View):
    def __init__(self, ctx, job_data):
        super().__init__(timeout=25.0)
        self.ctx = ctx
        self.job_data = job_data
        self.message = None
        self.start_time = datetime.utcnow()
        
        ingredients = ["🥩", "🥬", "🍅", "🧀", "🍞", "🧅", "🥓", "🍳"]
        self.target_recipe = random.sample(ingredients, 3)
        self.available_ingredients = self.target_recipe + random.sample([i for i in ingredients if i not in self.target_recipe], 2)
        random.shuffle(self.available_ingredients)
        
        self.current_step = 0
        
        for i, ing in enumerate(self.available_ingredients):
            btn = discord.ui.Button(label=ing, style=discord.ButtonStyle.blurple, custom_id=f"ing_{i}")
            btn.callback = self.make_callback(ing)
            self.add_item(btn)

    def make_callback(self, ingredient):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("get out of my kitchen.", ephemeral=True)
                return
                
            if ingredient == self.target_recipe[self.current_step]:
                self.current_step += 1
                if self.current_step == len(self.target_recipe):
                    self.stop()
                    time_taken = (datetime.utcnow() - self.start_time).total_seconds()
                    await interaction.response.defer()
                    await handle_job_reward(self.ctx, "chef", self.job_data, True, self.message, time_taken=time_taken)
                else:
                    embed = self.message.embeds[0]
                    embed.description = f"**Recipe:** {' -> '.join(self.target_recipe)}\n\n**Progress:** {' -> '.join(self.target_recipe[:self.current_step])}"
                    await interaction.response.edit_message(embed=embed, view=self)
            else:
                self.stop()
                time_taken = (datetime.utcnow() - self.start_time).total_seconds()
                await interaction.response.defer()
                await handle_job_reward(self.ctx, "chef", self.job_data, False, self.message, time_taken=time_taken)
                
        return callback

    async def on_timeout(self):
        try:
            await handle_job_reward(self.ctx, "chef", self.job_data, False, self.message)
        except:
            pass


class DeveloperGameView(discord.ui.View):
    def __init__(self, ctx, job_data):
        super().__init__(timeout=30.0)
        self.ctx = ctx
        self.job_data = job_data
        self.message = None
        self.start_time = datetime.utcnow()
        
        snippets = [
            ("def add(a, b):\n  return a + b", True),
            ("def add(a, b)\n  return a + b", False),
            ("function add(a, b) {\n  return a + b;\n}", True),
            ("function add(a, b) \n  return a + b;\n}", False),
            ("System.out.println(\"test\");", True),
            ("System.out.println(\"test\")", False)
        ]
        
        good = [s for s in snippets if s[1]]
        bad = [s for s in snippets if not s[1]]
        
        self.correct_snippet = random.choice(good)[0]
        wrong_snippets = [x[0] for x in random.sample(bad, 3)]
        
        all_snippets = wrong_snippets + [self.correct_snippet]
        random.shuffle(all_snippets)
        
        self.select = discord.ui.Select(placeholder="Select the code without syntax errors...", options=[
            discord.SelectOption(label=f"Snippet {i+1}", value=s) for i, s in enumerate(all_snippets)
        ])
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
        self.snippet_display = ""
        for i, s in enumerate(all_snippets):
            self.snippet_display += f"**Snippet {i+1}:**\n```python\n{s}\n```\n"

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("don't touch my keyboard.", ephemeral=True)
            return
            
        self.stop()
        time_taken = (datetime.utcnow() - self.start_time).total_seconds()
        selected = self.select.values[0]
        success = (selected == self.correct_snippet)
        await interaction.response.defer()
        await handle_job_reward(self.ctx, "developer", self.job_data, success, self.message, time_taken=time_taken)

    async def on_timeout(self):
        try:
            await handle_job_reward(self.ctx, "developer", self.job_data, False, self.message)
        except:
            pass


class HackerGameView(discord.ui.View):
    def __init__(self, ctx, job_data):
        super().__init__(timeout=45.0)
        self.ctx = ctx
        self.job_data = job_data
        self.message = None
        self.start_time = datetime.utcnow()
        
        self.target_pin = f"{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}"
        self.attempts = 3
        
        self.input_modal_btn = discord.ui.Button(label="Enter PIN", style=discord.ButtonStyle.danger)
        self.input_modal_btn.callback = self.modal_callback
        self.add_item(self.input_modal_btn)
        
        self.history = []

    async def modal_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("get off my terminal.", ephemeral=True)
            return
            
        modal = HackerModal(self)
        await interaction.response.send_modal(modal)

    async def process_guess(self, guess: str, interaction: discord.Interaction):
        if len(guess) != 3 or not guess.isdigit():
            await interaction.response.send_message("PIN must be exactly 3 digits.", ephemeral=True)
            return
            
        self.attempts -= 1
        
        feedback = ""
        for i in range(3):
            if guess[i] == self.target_pin[i]:
                feedback += "🟩"
            elif guess[i] in self.target_pin:
                feedback += "🟨"
            else:
                feedback += "🟥"
                
        self.history.append(f"`{guess}` - {feedback}")
        
        if guess == self.target_pin:
            self.stop()
            time_taken = (datetime.utcnow() - self.start_time).total_seconds()
            await interaction.response.defer()
            await handle_job_reward(self.ctx, "hacker", self.job_data, True, self.message, time_taken=time_taken)
            return
            
        if self.attempts <= 0:
            self.stop()
            time_taken = (datetime.utcnow() - self.start_time).total_seconds()
            await interaction.response.defer()
            await handle_job_reward(self.ctx, "hacker", self.job_data, False, self.message, time_taken=time_taken)
            return
            
        embed = self.message.embeds[0]
        embed.description = f"**TARGET MAINFRAME ENCRYPTED**\nCrack the 3-digit PIN.\n\n**Attempts left:** {self.attempts}\n\n**History:**\n" + "\n".join(self.history)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        try:
            await handle_job_reward(self.ctx, "hacker", self.job_data, False, self.message)
        except:
            pass


class HackerModal(discord.ui.Modal, title='Hack Mainframe'):
    pin = discord.ui.TextInput(
        label='3-Digit PIN',
        style=discord.TextStyle.short,
        placeholder='e.g. 123',
        required=True,
        max_length=3,
        min_length=3
    )

    def __init__(self, view: HackerGameView):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.view.process_guess(self.pin.value, interaction)


class MinerGameView(discord.ui.View):
    def __init__(self, ctx, job_data):
        super().__init__(timeout=30.0)
        self.ctx = ctx
        self.job_data = job_data
        self.message = None
        self.start_time = datetime.utcnow()
        self.picks_left = 3
        
        # 25 spots: 1 diamond, 4 lava, 20 rock
        self.grid = ["rock"] * 20 + ["lava"] * 4 + ["diamond"] * 1
        random.shuffle(self.grid)
        
        for i in range(25):
            btn = discord.ui.Button(
                label="⬛", 
                style=discord.ButtonStyle.gray, 
                custom_id=f"mine_{i}",
                row=i // 5
            )
            btn.callback = self.make_callback(i, btn)
            self.add_item(btn)

    def make_callback(self, idx, btn):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("get your own pickaxe.", ephemeral=True)
                return
                
            self.picks_left -= 1
            spot_type = self.grid[idx]
            
            btn.disabled = True
            
            if spot_type == "diamond":
                btn.label = "💎"
                btn.style = discord.ButtonStyle.success
                self.stop()
                time_taken = (datetime.utcnow() - self.start_time).total_seconds()
                for item in self.children:
                    item.disabled = True
                
                # Big multiplier for diamond
                payout = JOBS["miner"]["base_pay"] * 3
                await interaction.response.defer()
                await handle_job_reward(self.ctx, "miner", self.job_data, True, self.message, custom_payout=payout, time_taken=time_taken)
                return
                
            elif spot_type == "lava":
                btn.label = "🔥"
                btn.style = discord.ButtonStyle.danger
                self.stop()
                time_taken = (datetime.utcnow() - self.start_time).total_seconds()
                for item in self.children:
                    item.disabled = True
                
                # Lose money
                await interaction.response.defer()
                await handle_job_reward(self.ctx, "miner", self.job_data, False, self.message, custom_payout=-100, time_taken=time_taken)
                return
                
            else:
                btn.label = "🪨"
                btn.style = discord.ButtonStyle.secondary
                
                if self.picks_left <= 0:
                    self.stop()
                    time_taken = (datetime.utcnow() - self.start_time).total_seconds()
                    for item in self.children:
                        item.disabled = True
                    # Just normal payout for surviving but not finding diamond
                    await interaction.response.defer()
                    await handle_job_reward(self.ctx, "miner", self.job_data, True, self.message, time_taken=time_taken)
                    return
                else:
                    embed = self.message.embeds[0]
                    embed.description = f"**Welcome to the mines!**\nFind the diamond 💎, avoid the lava 🔥.\n\n**Picks left:** {self.picks_left}"
                    await interaction.response.edit_message(embed=embed, view=self)

        return callback

    async def on_timeout(self):
        try:
            await handle_job_reward(self.ctx, "miner", self.job_data, False, self.message)
        except:
            pass


class ThiefGameView(discord.ui.View):
    def __init__(self, ctx, job_data):
        super().__init__(timeout=20.0)
        self.ctx = ctx
        self.job_data = job_data
        self.message = None
        self.start_time = datetime.utcnow()
        self.current_stash = 0
        
        self.stages = [
            {"name": "the front porch", "chance": 0.85, "reward": 50},
            {"name": "the living room", "chance": 0.65, "reward": 150},
            {"name": "the master bedroom", "chance": 0.45, "reward": 300},
            {"name": "the hidden wall safe", "chance": 0.25, "reward": 800}
        ]
        self.stage_idx = 0
        
        self.steal_btn = discord.ui.Button(label="Steal", style=discord.ButtonStyle.danger, custom_id="thief_steal")
        self.steal_btn.callback = self.steal_callback
        self.add_item(self.steal_btn)
        
        self.escape_btn = discord.ui.Button(label="Escape with Stash", style=discord.ButtonStyle.success, custom_id="thief_escape")
        self.escape_btn.callback = self.escape_callback
        self.add_item(self.escape_btn)

    async def steal_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("you are not the thief here.", ephemeral=True)
            return
            
        stage = self.stages[self.stage_idx]
        if random.random() <= stage["chance"]:
            # Success
            self.current_stash += stage["reward"]
            self.stage_idx += 1
            
            if self.stage_idx >= len(self.stages):
                # Max stage reached
                self.stop()
                time_taken = (datetime.utcnow() - self.start_time).total_seconds()
                await interaction.response.defer()
                await handle_job_reward(self.ctx, "thief", self.job_data, True, self.message, custom_payout=self.current_stash, time_taken=time_taken)
                return
                
            next_stage = self.stages[self.stage_idx]
            embed = self.message.embeds[0]
            embed.description = f"**Current Stash:** {self.current_stash} coins\n\nNext target: **{next_stage['name']}**\nRisk of getting caught: {int((1-next_stage['chance'])*100)}%\nPotential gain: {next_stage['reward']} coins\n\ndo you push your luck?"
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Caught
            self.stop()
            time_taken = (datetime.utcnow() - self.start_time).total_seconds()
            for item in self.children:
                item.disabled = True
            
            fine = int(self.current_stash * 0.5) + 50
            await interaction.response.defer()
            await handle_job_reward(self.ctx, "thief", self.job_data, False, self.message, custom_payout=-fine, time_taken=time_taken)

    async def escape_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("you are not the thief here.", ephemeral=True)
            return
            
        self.stop()
        time_taken = (datetime.utcnow() - self.start_time).total_seconds()
        for item in self.children:
            item.disabled = True
            
        await interaction.response.defer()
        if self.current_stash > 0:
            await handle_job_reward(self.ctx, "thief", self.job_data, True, self.message, custom_payout=self.current_stash, time_taken=time_taken)
        else:
            await handle_job_reward(self.ctx, "thief", self.job_data, False, self.message, time_taken=time_taken)

    async def on_timeout(self):
        try:
            await handle_job_reward(self.ctx, "thief", self.job_data, False, self.message)
        except:
            pass


def setup_job(client: commands.Bot):
    @client.hybrid_group(name="job", description="job system commands")
    async def job_group(ctx: commands.Context):
        pass

    @job_group.command(name="list", description="list all available jobs")
    async def job_list(ctx: commands.Context):
        embed = discord.Embed(title="Available Jobs", color=0x3498db)
        for job_id, info in JOBS.items():
            embed.add_field(
                name=f"{info['emoji']} {job_id.title()}",
                value=f"**Pay:** {info['base_pay']} / shift\n**Req Level:** {info['req_level']}\n**Cooldown:** {info['cooldown_minutes']}m\n_{info['description']}_",
                inline=False
            )
        await ctx.reply(embed=embed)

    @job_group.command(name="info", description="check your current job status")
    async def job_info(ctx: commands.Context):
        job_data = await asyncio.to_thread(db.get_user_job, ctx.author.id)
        if not job_data:
            await ctx.reply("you are currently unemployed. use `/job apply <job_name>` to get a job.")
            return
            
        job_name = job_data["job_name"]
        if job_name not in JOBS:
            await asyncio.to_thread(db.remove_user_job, ctx.author.id)
            await ctx.reply("your job no longer exists. you have been fired.")
            return
            
        info = JOBS[job_name]
        level = job_data["job_level"]
        xp = job_data["job_xp"]
        shifts = job_data["shifts_completed"]
        
        title = get_job_title(job_name, level)
        
        xp_needed = level * 100
        progress_bar_length = 10
        filled = int((xp / xp_needed) * progress_bar_length)
        bar = "█" * filled + "░" * (progress_bar_length - filled)
        
        embed = discord.Embed(title=f"Employment Info - {ctx.author.display_name}", color=0x2ecc71)
        embed.add_field(name="Job", value=f"{info['emoji']} {job_name.title()} ({title})", inline=True)
        embed.add_field(name="Level", value=f"{level} / {info['max_level']}", inline=True)
        embed.add_field(name="Shifts Completed", value=str(shifts), inline=True)
        embed.add_field(name="Experience", value=f"`{bar}` ({xp}/{xp_needed} XP)", inline=False)
        embed.add_field(name="Base Pay", value=f"{int(info['base_pay'] * (1 + (level * 0.1)))} coins / shift", inline=False)
        
        await ctx.reply(embed=embed)

    @job_group.command(name="apply", description="apply for a job")
    @app_commands.describe(job_name="the name of the job you want")
    async def job_apply(ctx: commands.Context, job_name: Literal["janitor", "chef", "developer", "hacker", "miner", "thief"]):
        job_name = job_name.lower()
        if job_name not in JOBS:
            await ctx.reply(f"invalid job. use `/job list` to see available jobs.")
            return
            
        req_level = JOBS[job_name]["req_level"]
        fee = req_level * 500
        
        if fee > 0:
            bal = await asyncio.to_thread(db.get_balance, ctx.author.id)
            if bal < fee and ctx.bot.user.id != 1522117141090799697:
                await ctx.reply(f"you need {fee} coins to get the license for this job. you only have {bal}.")
                return
            await asyncio.to_thread(db.update_balance, ctx.author.id, -fee)
            await ctx.reply(f"you paid {fee} coins for the {job_name} license.")
            
        await asyncio.to_thread(db.set_user_job, ctx.author.id, job_name)
        await ctx.reply(f"congratulations! you are now a {JOBS[job_name]['emoji']} {job_name.title()}. use `/job work` to start your shift.")

    @job_group.command(name="quit", description="quit your current job")
    async def job_quit(ctx: commands.Context):
        job_data = await asyncio.to_thread(db.get_user_job, ctx.author.id)
        if not job_data:
            await ctx.reply("you don't even have a job to quit.")
            return
            
        await asyncio.to_thread(db.remove_user_job, ctx.author.id)
        await ctx.reply("you slammed your badge on the desk and walked out. you are now unemployed.")

    @job_group.command(name="work", description="work your shift to earn money")
    async def job_work(ctx: commands.Context):
        job_data = await asyncio.to_thread(db.get_user_job, ctx.author.id)
        if not job_data:
            await ctx.reply("you don't have a job! use `/job apply` first.")
            return
            
        job_name = job_data["job_name"]
        if job_name not in JOBS:
            await ctx.reply("your job is invalid. please apply for a new one.")
            return
            
        info = JOBS[job_name]
        
        # Check cooldown
        if job_data["last_work_time"]:
            last_work = datetime.fromisoformat(job_data["last_work_time"])
            now = datetime.utcnow()
            diff = now - last_work
            cooldown_dt = timedelta(minutes=info["cooldown_minutes"])
            
            if diff < cooldown_dt:
                remaining = cooldown_dt - diff
                mins, secs = divmod(remaining.total_seconds(), 60)
                await ctx.reply(f"you are on break! your next shift starts in {int(mins)}m {int(secs)}s. (try `/job beg` if you're desperate)", ephemeral=True)
                return
                
        title = get_job_title(job_name, job_data["job_level"])
        embed = discord.Embed(title=f"{info['emoji']} {job_name.title()} Shift Started ({title})", color=0x3498db)
        
        if job_name == "janitor":
            embed.description = "oh no! someone made a mess. click the poop emoji to clean it up!"
            view = JanitorGameView(ctx, job_data)
        elif job_name == "chef":
            view = ChefGameView(ctx, job_data)
            embed.description = f"**Recipe:** {' -> '.join(view.target_recipe)}\n\n**Progress:** "
        elif job_name == "developer":
            view = DeveloperGameView(ctx, job_data)
            embed.description = "find the snippet of code that actually compiles without errors:\n\n" + view.snippet_display
        elif job_name == "hacker":
            embed.description = "**TARGET MAINFRAME ENCRYPTED**\nCrack the 3-digit PIN.\n\n**Attempts left:** 3"
            view = HackerGameView(ctx, job_data)
        elif job_name == "miner":
            embed.description = "**Welcome to the mines!**\nFind the diamond 💎, avoid the lava 🔥.\n\n**Picks left:** 3"
            view = MinerGameView(ctx, job_data)
        elif job_name == "thief":
            stage = view.stages[0] if (view := ThiefGameView(ctx, job_data)) else None
            embed.description = f"**Current Stash:** 0 coins\n\nNext target: **{stage['name']}**\nRisk of getting caught: {int((1-stage['chance'])*100)}%\nPotential gain: {stage['reward']} coins\n\ndo you push your luck?"
        else:
            await ctx.reply("job minigame not implemented yet.")
            return
            
        view.message = await ctx.reply(embed=embed, view=view)

    @job_group.command(name="beg", description="beg your boss to let you off break early")
    @commands.cooldown(1, 120, commands.BucketType.user)
    async def job_beg(ctx: commands.Context):
        job_data = await asyncio.to_thread(db.get_user_job, ctx.author.id)
        if not job_data:
            await ctx.reply("you don't even have a job to beg for. go apply first.")
            return
            
        job_name = job_data["job_name"]
        info = JOBS[job_name]
        
        if not job_data["last_work_time"]:
            await ctx.reply("you aren't even on break... get back to work! `/job work`")
            return
            
        last_work = datetime.fromisoformat(job_data["last_work_time"])
        now = datetime.utcnow()
        diff = now - last_work
        cooldown_dt = timedelta(minutes=info["cooldown_minutes"])
        
        if diff >= cooldown_dt:
            await ctx.reply("you are already off break! run `/job work` to start your shift.")
            return
            
        success = random.random() < 0.35  # 35% chance to get off break
        
        if success:
            await asyncio.to_thread(db.update_job_time, ctx.author.id, None)
            await ctx.reply("your boss sighed and told you to get back to work. you are off break! run `/job work`.")
        else:
            penalty = timedelta(minutes=random.randint(1, 3))
            new_last_work = last_work + penalty
            await asyncio.to_thread(db.update_job_time, ctx.author.id, new_last_work.isoformat())
            await ctx.reply(f"your boss got mad and told you to get out of his office. your break was extended by {penalty.total_seconds() // 60:.0f} minutes!")

    @job_beg.error
    async def job_beg_error(ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"your boss is ignoring you right now. try again in {error.retry_after:.1f}s", ephemeral=True)
        else:
            await ctx.reply(f"error: {error}")