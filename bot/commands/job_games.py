"""the six job minigame views."""

import random
import asyncio
import discord
from bot.commands.job_rewards import JOBS, handle_job_reward
from datetime import datetime

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
