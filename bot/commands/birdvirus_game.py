"""the /pure birdvirus guessing game view."""

import asyncio
import discord
import bot.db as db
from bot.commands import game_unlock, track_gamble
from bot.commands.money import _payout, apply_tax


class BirdvirusGameView(discord.ui.View):
    def __init__(self, ctx, bet, birds_data, correct_count, coin_emoji):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.bet = bet
        self.birds_data = birds_data
        self.correct_count = correct_count
        self.coin_emoji = coin_emoji
        self.message = None

        options = [
            discord.SelectOption(label=f"Inspect Bird {i+1}", value=str(i), description="Check where it's been and what it ate")
            for i in range(len(birds_data))
        ]
        self.select = discord.ui.Select(placeholder="Select a bird to inspect...", options=options, row=0)
        self.select.callback = self.select_callback
        self.add_item(self.select)

        for i in range(6):
            button = discord.ui.Button(label=str(i), style=discord.ButtonStyle.blurple, custom_id=f"guess_{i}", row=1 if i < 5 else 2)
            button.callback = self.make_callback(i)
            self.add_item(button)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("this is not your game dude", ephemeral=True)
            return
            
        bird_idx = int(self.select.values[0])
        bird = self.birds_data[bird_idx]
        
        embed = self.message.embeds[0]
        embed.clear_fields()
        embed.add_field(name=f"Bird {bird_idx + 1} Dossier", value=f"**Location History:** {bird['location']}\n**Recent Diet:** {bird['food']}\n**Status:** ❓ Unknown", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)

    def make_callback(self, guess):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message("this is not your game dude", ephemeral=True)
                return
            
            self.stop()
            game_unlock(self.ctx)
            for item in self.children:
                item.disabled = True
            
            if guess == self.correct_count:
                multiplier = 5 
                net_gain = _payout(self.bet, multiplier) - self.bet
                new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, net_gain)
                tax = await apply_tax(self.ctx, self.ctx.author.id, net_gain)
                await track_gamble(self.ctx, net_gain)
                status = f"correct! there were {self.correct_count} infected birds. you won {net_gain} {self.coin_emoji} (balance: {new_balance}) (tax: {tax} {self.coin_emoji})"
                color = 0x2ecc71
            else:
                net_gain = -self.bet
                new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, net_gain)
                await track_gamble(self.ctx, net_gain)
                status = f"wrong! there were {self.correct_count} infected birds. you lost {self.bet} {self.coin_emoji} (balance: {new_balance})"
                color = 0xe74c3c
                
            embed = self.message.embeds[0]
            embed.color = color
            embed.clear_fields()
            
            reveal_text = ""
            for i, bird in enumerate(self.birds_data):
                status_emoji = "🦠 infected" if bird['infected'] else "✅ healthy"
                reveal_text += f"Bird {i+1}: {status_emoji}\n"
            
            embed.add_field(name="Final Results", value=reveal_text, inline=False)
            embed.set_footer(text=status)
            await interaction.response.edit_message(embed=embed, view=self)
        return callback

    async def on_timeout(self):
        game_unlock(self.ctx)
        for item in self.children:
            item.disabled = True
        net_gain = -self.bet
        new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, net_gain)
        await track_gamble(self.ctx, net_gain)
        embed = self.message.embeds[0]
        embed.color = 0xe74c3c
        embed.set_footer(text=f"timed out! you lost {self.bet} {self.coin_emoji} (balance: {new_balance})")
        try:
            await self.message.edit(embed=embed, view=self)
        except:
            pass

