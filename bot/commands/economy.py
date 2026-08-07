import random
import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from bot.commands import is_admin, is_nightly, game_lock, game_unlock, _s, claim_streak_bonus, track_gamble, is_dev
from bot.commands.blackjack import BlackjackView, draw_card
from bot.commands.horserace import HorseRaceView
from bot.commands.catrace import CatRaceView
from bot.commands.shop import take_cheat


def _payout(bet, mult):
    """exact integer multiplication, no float precision loss."""
    if type(mult) is int:
        return bet * mult
    n, d = mult.as_integer_ratio()
    return bet * n // d


def _to_bet(val):
    """convert string bet to int, supports arbitrarily large numbers."""
    try:
        v = int(val)
    except (ValueError, TypeError):
        raise commands.BadArgument("bet must be a valid integer")
    if v <= 0:
        raise commands.BadArgument("bet must be greater than zero")
    return v

async def get_balance_checked(ctx, user_id):
    if is_nightly(ctx.bot):
        return 999999999999999999999999999, 999999999999999999999999999, 0
    bal, bank, debt = await asyncio.to_thread(db.get_balances, user_id)
    return bal, bank, debt

async def apply_tax(ctx, user_id, net_gain):
    if net_gain <= 0:
        return 0
    tax_rate_str = await asyncio.to_thread(db.get_config, "tax_rate", "0")
    tax_rate = int(tax_rate_str)
    if tax_rate <= 0:
        return 0
    if is_nightly(ctx.bot):
        return 0
    tax_amount = max(1, int(net_gain * tax_rate / 100))
    await asyncio.to_thread(db.update_balance, user_id, -tax_amount)
    await asyncio.to_thread(db.update_house, tax_amount)
    collected = await asyncio.to_thread(db.get_config, "tax_collected", "0")
    await asyncio.to_thread(db.set_config, "tax_collected", str(int(collected) + tax_amount))
    return tax_amount

def update_with_tax(ctx, user_id, net_gain):
    async def wrapper():
        new_bal = await asyncio.to_thread(db.update_balance, user_id, net_gain)
        tax = 0
        if net_gain > 0:
            tax = await apply_tax(ctx, user_id, net_gain)
        return new_bal, tax
    return wrapper()

async def build_leaderboard_embed(ctx, all_users, page, total_pages, coin_emoji):
    PAGE_SIZE = 10
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    start = (page - 1) * PAGE_SIZE
    page_users = all_users[start:start + PAGE_SIZE]

    lines = []
    for i, user in enumerate(page_users):
        rank = start + i + 1
        medal = medals.get(rank, f"`#{rank}`")

        try:
            member = ctx.guild.get_member(user["user_id"])
            if member is None:
                try:
                    member = await ctx.guild.fetch_member(user["user_id"])
                    name = discord.utils.escape_markdown(member.display_name)
                except (discord.NotFound, discord.HTTPException):
                    try:
                        global_user = await ctx.bot.fetch_user(user["user_id"])
                        name = discord.utils.escape_markdown(global_user.display_name or global_user.name)
                    except (discord.NotFound, discord.HTTPException):
                        name = f"Deleted User ({user['user_id']})"
            else:
                name = discord.utils.escape_markdown(member.display_name)
        except Exception:
            name = f"Deleted User ({user['user_id']})"

        total = user["balance"] + user["bank"]
        lines.append(
            f"{medal} **{name}**\n"
            f"┣ total: {coin_emoji} `{_s(total)}`\n"
            f"┣ holding: 💰 `{_s(user['balance'])}`\n"
            f"┗ bank: 🏦 `{_s(user['bank'])}`"
        )

    embed = discord.Embed(
        title="🏆 Leaderboard",
        description="\n\n".join(lines),
        color=0xf1c40f
    )
    embed.set_footer(text=f"page {page}/{total_pages} • {len(all_users)} players total")
    return embed

class LeaderboardView(discord.ui.View):
    def __init__(self, ctx, all_users, current_page, total_pages, coin_emoji):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.all_users = all_users
        self.current_page = current_page
        self.total_pages = total_pages
        self.coin_emoji = coin_emoji
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="< prev", style=discord.ButtonStyle.grey)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("this is not your leaderboard dude", ephemeral=True)
            return
        await interaction.response.defer()
        self.current_page -= 1
        self._update_buttons()
        embed = await build_leaderboard_embed(self.ctx, self.all_users, self.current_page, self.total_pages, self.coin_emoji)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="next >", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("this is not your leaderboard dude", ephemeral=True)
            return
        await interaction.response.defer()
        self.current_page += 1
        self._update_buttons()
        embed = await build_leaderboard_embed(self.ctx, self.all_users, self.current_page, self.total_pages, self.coin_emoji)
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

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

def setup_economy(client: commands.Bot):
    # Pure Group
    @client.hybrid_group(name="pure", description="pure economy commands")
    async def pure_group(ctx: commands.Context):
        pass

    @pure_chance_command := pure_group.command(name="chance", description="gamble your coins on pure chance")
    @app_commands.describe(bet="amount of coins to bet")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def pure_chance(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)
            
        bal, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return

        await claim_streak_bonus(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        win = random.choice([True, False])
        
        if win:
            net_gain = bet
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, bet)
            tax = await apply_tax(ctx, ctx.author.id, net_gain)
            await track_gamble(ctx, net_gain)
            await ctx.reply(f"you won! doubled your bet of {bet} {coin_emoji} (balance: {new_balance}) (tax: {tax} {coin_emoji})")
        else:
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, -bet)
            await track_gamble(ctx, -bet)
            await ctx.reply(f"you lost {bet} {coin_emoji} unlucky dude (balance: {new_balance})")

    @pure_blackjack_command := pure_group.command(name="blackjack", description="play a game of blackjack against the dealer")
    @app_commands.describe(bet="the amount of coins to bet")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pure_blackjack(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)
            
        balance_val = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance_val < bet:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {balance_val})")
            return

        await claim_streak_bonus(ctx)
        game_lock(ctx)
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        
        player_hand = [draw_card(), draw_card()]
        dealer_hand = [draw_card(), draw_card()]
        
        from bot.commands.blackjack import calculate_hand
        
        player_total = calculate_hand(player_hand)
        dealer_total = calculate_hand(dealer_hand)
        
        if player_total == 21:
            game_unlock(ctx)
            if dealer_total == 21:
                await ctx.reply(f"both got natural blackjack! it's a tie. bet refunded")
            else:
                payout = _payout(bet, 1.5)
                new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, payout)
                tax = await apply_tax(ctx, ctx.author.id, payout)
                await track_gamble(ctx, payout)
                await ctx.reply(f"natural blackjack! you won {payout} {coin_emoji} (balance: {new_balance}) (tax: {tax} {coin_emoji})")
            return

        view = BlackjackView(ctx, bet, player_hand, dealer_hand, coin_emoji, game_unlock)
        await view.start(ctx)

    @pure_slots_command := pure_group.command(name="slots", description="play slots and try to win big")
    @app_commands.describe(bet="the amount of coins to bet")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def pure_slots(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)
            
        bal, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return

        await claim_streak_bonus(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        emojis = ['🍒', '🍋', '🍇', '🔔', '💎', '7️⃣']
        
        embed = discord.Embed(title="slots", color=0x2f3136)
        embed.description = "```\n[  🪙  |  🪙  |  🪙  ]\n```\nspinning..."
        message = await ctx.reply(embed=embed)
        
        await asyncio.sleep(0.8)
        spin1 = [random.choice(emojis) for _ in range(3)]
        embed.description = f"```\n[  {spin1[0]}  |  {spin1[1]}  |  {spin1[2]}  ]\n```\nspinning..."
        await message.edit(embed=embed)
        
        await asyncio.sleep(0.8)
        spin2 = [random.choice(emojis) for _ in range(3)]
        embed.description = f"```\n[  {spin2[0]}  |  {spin2[1]}  |  {spin2[2]}  ]\n```\nspinning..."
        await message.edit(embed=embed)
        
        await asyncio.sleep(0.8)
        
        reels = [random.choice(emojis) for _ in range(3)]

        cheat = take_cheat(ctx.author.id, "slot_cheat")
        if cheat:
            match = random.choice(emojis)
            reels = [match, match, match]
        unique_count = len(set(reels))
        
        if unique_count == 1:
            match = reels[0]
            if match == '7️⃣':
                multiplier = 15
                status = "jackpot! three 7️⃣s!"
            elif match == '💎':
                multiplier = 10
                status = "mega win! three diamonds!"
            elif match == '🔔':
                multiplier = 7
                status = "big win! three bells!"
            else:
                multiplier = 5
                status = f"three of a kind ({match})!"
        elif unique_count == 2:
            if reels[0] == reels[1] or reels[0] == reels[2]:
                pair = reels[0]
            else:
                pair = reels[1]
                
            if pair in ['7️⃣', '💎']:
                multiplier = 2.5
                status = f"two of a kind ({pair})!"
            else:
                multiplier = 2
                status = f"two of a kind ({pair})!"
        else:
            multiplier = 0
            status = "no match. unlucky!"
            
        if multiplier > 0:
            net_gain = _payout(bet, multiplier) - bet
        else:
            net_gain = -bet

        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)
        await track_gamble(ctx, net_gain)

        if net_gain > 0:
            tax = await apply_tax(ctx, ctx.author.id, net_gain)
            status_text = f"{status}\nyou won {net_gain} {coin_emoji}! (balance: {new_balance}) (tax: {tax} {coin_emoji})"
            color = 0xf1c40f if multiplier >= 5 else 0x2ecc71
        else:
            status_text = f"{status}\nyou lost {bet} {coin_emoji}. unlucky (balance: {new_balance})"
            color = 0xe74c3c
            
        embed.color = color
        embed.description = f"```\n[  {reels[0]}  |  {reels[1]}  |  {reels[2]}  ]\n```\n{status_text.lower()}"
        await message.edit(embed=embed)

    @pure_roulette_command := pure_group.command(name="roulette", description="gamble your coins on a roulette wheel spin")
    @app_commands.describe(
        bet="the amount of coins to bet",
        guess="where to bet: red, black, even, odd, high (19-36), low (1-18), or a specific number (0-36)"
    )
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def pure_roulette(ctx: commands.Context, bet: str, guess: str):
        bet = _to_bet(bet)
            
        bal, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return

        await claim_streak_bonus(ctx)
        guess_clean = guess.strip().lower()
        
        is_number = False
        target_number = -1
        try:
            target_number = int(guess_clean)
            if 0 <= target_number <= 36:
                is_number = True
            else:
                await ctx.reply("number must be between 0 and 36")
                return
        except ValueError:
            pass
            
        valid_bets = ["red", "black", "even", "odd", "high", "low"]
        if not is_number and guess_clean not in valid_bets:
            await ctx.reply("invalid guess. choose red, black, even, odd, high, low, or a number from 0 to 36")
            return
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        
        embed = discord.Embed(title="roulette", color=0x2f3136)
        embed.description = "spinning the wheel..."
        message = await ctx.reply(embed=embed)
        
        await asyncio.sleep(0.8)
        dummy_spin1 = random.randint(0, 36)
        dummy_color1 = "🟢" if dummy_spin1 == 0 else "🔴" if dummy_spin1 in red_numbers else "⚫"
        embed.description = f"the ball is rolling...\npassing {dummy_color1} {dummy_spin1}..."
        await message.edit(embed=embed)
        
        await asyncio.sleep(0.8)
        dummy_spin2 = random.randint(0, 36)
        dummy_color2 = "🟢" if dummy_spin2 == 0 else "🔴" if dummy_spin2 in red_numbers else "⚫"
        embed.description = f"the ball is slowing down...\npassing {dummy_color2} {dummy_spin2}..."
        await message.edit(embed=embed)
        
        await asyncio.sleep(0.8)
        
        spin_result = random.randint(0, 36)
        if spin_result == 0:
            result_color = "green"
            result_color_emoji = "🟢"
        elif spin_result in red_numbers:
            result_color = "red"
            result_color_emoji = "🔴"
        else:
            result_color = "black"
            result_color_emoji = "⚫"
            
        win = False
        multiplier = 0
        
        if is_number:
            if spin_result == target_number:
                win = True
                multiplier = 36
        elif guess_clean == "red":
            if result_color == "red":
                win = True
                multiplier = 2
        elif guess_clean == "black":
            if result_color == "black":
                win = True
                multiplier = 2
        elif guess_clean == "even":
            if spin_result != 0 and spin_result % 2 == 0:
                win = True
                multiplier = 2
        elif guess_clean == "odd":
            if spin_result % 2 != 0:
                win = True
                multiplier = 2
        elif guess_clean == "high":
            if 19 <= spin_result <= 36:
                win = True
                multiplier = 2
        elif guess_clean == "low":
            if 1 <= spin_result <= 18:
                win = True
                multiplier = 2
                
        if win:
            net_gain = _payout(bet, multiplier) - bet
        else:
            net_gain = -bet

        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)
        await track_gamble(ctx, net_gain)

        if win:
            tax = await apply_tax(ctx, ctx.author.id, net_gain)
            status_text = f"the ball landed on {result_color_emoji} {spin_result}!\nyou won {net_gain} {coin_emoji}! (balance: {new_balance}) (tax: {tax} {coin_emoji})"
            color = 0x2ecc71
        else:
            status_text = f"the ball landed on {result_color_emoji} {spin_result}.\nyou lost {bet} {coin_emoji}. unlucky (balance: {new_balance})"
            color = 0xe74c3c
            
        embed.color = color
        embed.description = status_text.lower()
        await message.edit(embed=embed)

    @pure_insaneroll_command := pure_group.command(name="insaneroll", description="roll a d20 with insane stakes")
    @app_commands.describe(bet="amount of coins to bet")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def pure_insaneroll(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)
            
        bal, bank, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return

        await claim_streak_bonus(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "dYT")
        
        roll = random.randint(1, 20)

        cheat = take_cheat(ctx.author.id, "rigged_dice")
        if cheat:
            roll = 20
        
        if roll == 1:
            multiplier = -5
            status = "CRITICAL FAILURE! you rolled a 1. you lost 5x your bet!"
        elif 2 <= roll <= 9:
            multiplier = 0
            status = f"failure. you rolled a {roll}. lost your bet."
        elif 10 <= roll <= 15:
            multiplier = 2
            status = f"success. you rolled a {roll}. doubled your bet."
        elif 16 <= roll <= 19:
            multiplier = 5
            status = f"great success! you rolled a {roll}. 5x your bet."
        else: # 20
            multiplier = 20
            status = "NATURAL 20! INSANE SUCCESS! 20x your bet!"
            
        if multiplier < 0:
            net_gain = _payout(bet, multiplier) # -5x
            # check if we need to drain bank
            if bal + bank < abs(net_gain):
                net_gain = -(bal + bank) # drain everything
            
            # update holding first
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, -bal if bal < abs(net_gain) else net_gain)
            remaining_debt = abs(net_gain) - bal if bal < abs(net_gain) else 0
            if remaining_debt > 0:
                await asyncio.to_thread(db.update_bank, ctx.author.id, -remaining_debt)
                new_balance = 0
        elif multiplier == 0:
            net_gain = -bet
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)
        else:
            net_gain = _payout(bet, multiplier) - bet
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)
            tax = await apply_tax(ctx, ctx.author.id, net_gain)

        await track_gamble(ctx, net_gain)

        if multiplier <= 0:
            color = 0xe74c3c if roll != 1 else 0x992d22
            status_text = f"**d20 ROLL: {roll}**\n{status}\nyou lost {abs(net_gain)} {coin_emoji}. (holding balance: {new_balance})"
        else:
            color = 0x2ecc71 if roll != 20 else 0xf1c40f
            status_text = f"**d20 ROLL: {roll}**\n{status}\nyou won {net_gain} {coin_emoji}! (holding balance: {new_balance}) (tax: {tax} {coin_emoji})"
            
        embed = discord.Embed(title="insane dice roll", description=status_text.lower(), color=color)
        await ctx.reply(embed=embed)

    @pure_birdvirus_command := pure_group.command(name="birdvirus", description="guess how many birds have the virus")
    @app_commands.describe(bet="amount of coins to bet")
    async def pure_birdvirus(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)

        bal_val, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal_val < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal_val})")
            return

        await claim_streak_bonus(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        game_lock(ctx)

        high_risk_locs = ["a quarantined zone", "a biohazard waste dump", "a glowing green puddle", "an abandoned testing lab", "the sewer drains"]
        low_risk_locs = ["a clean park", "a fresh bird feeder", "someone's balcony", "a nice oak tree", "a local garden"]
        
        high_risk_foods = ["a glowing worm", "discarded medical waste", "a suspicious radioactive berry", "pure plutonium", "a moldy french fry"]
        low_risk_foods = ["fresh seeds", "a normal earthworm", "a breadcrumb", "a standard bug", "some grass"]

        num_birds = 5
        infected_count = random.randint(0, num_birds)
        
        statuses = [True] * infected_count + [False] * (num_birds - infected_count)
        random.shuffle(statuses)
        
        birds_data = []
        for is_infected in statuses:
            if is_infected:
                loc = random.choice(high_risk_locs) if random.random() < 0.7 else random.choice(low_risk_locs)
                food = random.choice(high_risk_foods) if random.random() < 0.7 else random.choice(low_risk_foods)
            else:
                loc = random.choice(high_risk_locs) if random.random() < 0.1 else random.choice(low_risk_locs)
                food = random.choice(high_risk_foods) if random.random() < 0.1 else random.choice(low_risk_foods)
            
            birds_data.append({
                "infected": is_infected,
                "location": loc,
                "food": food
            })
        
        embed = discord.Embed(title="birdvirus scanner", color=0x2f3136)
        embed.description = f"a flock of 5 birds appeared! some of them might have the birdvirus.\nuse the dropdown menu to inspect each bird's history, then guess how many are infected.\n\nbet: {bet} {coin_emoji}"
        
        view = BirdvirusGameView(ctx, bet, birds_data, infected_count, coin_emoji)
        view.message = await ctx.reply(embed=embed, view=view)

    @pure_plinko_command := pure_group.command(name="plinko", description="drop the ball down the plinko board")
    @app_commands.describe(bet="amount of coins to bet")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def pure_plinko(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)

        bal_val, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal_val < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal_val})")
            return

        await claim_streak_bonus(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        multipliers = [15, 5, 2, 1, 2, 5, 15]
        slot_labels = ['💀', '🔴', '🟠', '🟡', '🟠', '🔴', '💀']

        pos = 3
        path = [pos]
        for _ in range(7):
            pos += random.choice([-1, 1])
            pos = max(0, min(6, pos))
            path.append(pos)

        final_slot = path[-1]
        multiplier = multipliers[final_slot]

        embed = discord.Embed(title="plinko", color=0x2f3136)
        embed.description = "```\n          ⬇️\n```\ndropping..."
        message = await ctx.reply(embed=embed)

        for frame in range(1, 8):
            await asyncio.sleep(0.4)
            rows = []
            for r in range(frame):
                row_pegs = []
                for c in range(7):
                    if c == path[r]:
                        row_pegs.append('🔴')
                    else:
                        row_pegs.append('⚪')
                rows.append(' '.join(row_pegs))
            embed.description = "```\n          ⬇️\n" + "\n".join(rows) + "\n```\ndropping..."
            await message.edit(embed=embed)

        await asyncio.sleep(0.5)

        slots_row = ' '.join(slot_labels)
        mults_row = '15x 5x 2x 1x 2x 5x 15x'

        net_gain = _payout(bet, multiplier) - bet
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)
        await track_gamble(ctx, net_gain)

        if net_gain > 0:
            tax = await apply_tax(ctx, ctx.author.id, net_gain)
            status = f"landed in {slot_labels[final_slot]} ({multiplier}x)\nyou won {net_gain} {coin_emoji} (balance: {new_balance}) (tax: {tax} {coin_emoji})"
            color = 0xf1c40f if multiplier >= 5 else 0x2ecc71
        elif net_gain == 0:
            status = f"landed in {slot_labels[final_slot]} ({multiplier}x)\nbroke even (balance: {new_balance})"
            color = 0x95a5a6
        else:
            status = f"landed in {slot_labels[final_slot]} ({multiplier}x)\nyou lost {abs(net_gain)} {coin_emoji} (balance: {new_balance})"
            color = 0xe74c3c

        embed.color = color
        rows = []
        for r in range(8):
            row_pegs = []
            for c in range(7):
                if c == path[r]:
                    row_pegs.append('🔴')
                else:
                    row_pegs.append('⚪')
            rows.append(' '.join(row_pegs))
        embed.description = "```\n          ⬇️\n" + "\n".join(rows) + f"\n{slots_row}\n{mults_row}\n```\n{status.lower()}"
        await message.edit(embed=embed)

    @pure_plinkohard_command := pure_group.command(name="plinkohard", description="HARD MODE plinko - higher risk, higher reward")
    @app_commands.describe(bet="amount of coins to bet")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def pure_plinkohard(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)

        bal_val, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal_val < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal_val})")
            return

        await claim_streak_bonus(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        multipliers = [50, 15, 3, 0.3, 0.3, 3, 15, 50]
        slot_labels = ['💀', '🔴', '🟠', '🟡', '🟡', '🟠', '🔴', '💀']

        pos = 3
        path = [pos]
        rows = 10
        for _ in range(rows):
            pos += random.choice([-1, 1])
            pos = max(0, min(7, pos))
            path.append(pos)

        final_slot = path[-1]
        multiplier = multipliers[final_slot]

        embed = discord.Embed(title="plinko HARD MODE", color=0x2f3136)
        embed.description = "```\n          ⬇️\n```\ndropping..."
        message = await ctx.reply(embed=embed)

        for frame in range(1, rows + 1):
            await asyncio.sleep(0.3)
            rows_display = []
            for r in range(frame):
                row_pegs = []
                for c in range(8):
                    if c == path[r]:
                        row_pegs.append('🔴')
                    else:
                        row_pegs.append('⚪')
                rows_display.append(' '.join(row_pegs))
            embed.description = "```\n          ⬇️\n" + "\n".join(rows_display) + "\n```\ndropping..."
            await message.edit(embed=embed)

        await asyncio.sleep(0.5)

        slots_row = ' '.join(slot_labels)
        mults_row = '50x 15x 3x .3 .3 3x 15x 50x'

        net_gain = _payout(bet, multiplier) - bet
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)
        await track_gamble(ctx, net_gain)

        if net_gain > 0:
            tax = await apply_tax(ctx, ctx.author.id, net_gain)
            status = f"landed in {slot_labels[final_slot]} ({multiplier}x)\nyou won {net_gain} {coin_emoji} (balance: {new_balance}) (tax: {tax} {coin_emoji})"
            color = 0xf1c40f if multiplier >= 15 else 0x2ecc71
        elif net_gain == 0:
            status = f"landed in {slot_labels[final_slot]} ({multiplier}x)\nbroke even (balance: {new_balance})"
            color = 0x95a5a6
        else:
            status = f"landed in {slot_labels[final_slot]} ({multiplier}x)\nyou lost {abs(net_gain)} {coin_emoji} (balance: {new_balance})"
            color = 0x992d22

        embed.color = color
        rows_display = []
        for r in range(rows + 1):
            row_pegs = []
            for c in range(8):
                if c == path[r]:
                    row_pegs.append('🔴')
                else:
                    row_pegs.append('⚪')
            rows_display.append(' '.join(row_pegs))
        embed.description = "```\n          ⬇️\n" + "\n".join(rows_display) + f"\n{slots_row}\n{mults_row}\n```\n{status.lower()}"
        await message.edit(embed=embed)

    @pure_horse_command := pure_group.command(name="horse", description="bet on a horse race at the birdvirus track")
    @app_commands.describe(bet="the amount of coins to bet")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pure_horse(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)

        bal, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return

        await claim_streak_bonus(ctx)
        game_lock(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        cheat = take_cheat(ctx.author.id, "race_boost")
        boost = cheat["value"] if cheat else 0
        view = HorseRaceView(ctx, bet, coin_emoji, game_unlock, cheat_boost=boost)
        await view.start(ctx)

    @pure_catrace_command := pure_group.command(name="catrace", description="bet on a cat race at the birdvirus track")
    @app_commands.describe(bet="the amount of coins to bet")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def pure_catrace(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)

        bal, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return

        await claim_streak_bonus(ctx)
        game_lock(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        cheat = take_cheat(ctx.author.id, "race_boost")
        boost = cheat["value"] if cheat else 0
        view = CatRaceView(ctx, bet, coin_emoji, game_unlock, cheat_boost=boost)
        await view.start(ctx)

    @pure_insurance_command := pure_group.command(name="insurance", description="claim a partial refund on today's net gambling losses")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def pure_insurance(ctx: commands.Context):
        if is_nightly(ctx.bot):
            await ctx.reply("nightly bot doesn't need insurance")
            return
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        refund, eligible, claimed = await asyncio.to_thread(db.claim_insurance, ctx.author.id)
        if claimed:
            await ctx.reply(f"you already claimed today's insurance. come back tomorrow 📉")
            return
        if refund <= 0:
            await ctx.reply(f"no net gambling losses to insure today yet. lose some more then try again 😏")
            return
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, refund)
        await asyncio.to_thread(db.update_house, -refund)
        await ctx.reply(f"🛡️ insurance payout! you lost {eligible} {coin_emoji} net today, refunded {refund} {coin_emoji} (10%, capped at 500). balance: {new_balance}")

    @pure_house_command := pure_group.command(name="house", description="check the birdvirus house wallet balance")
    async def pure_house(ctx: commands.Context):
        house = await asyncio.to_thread(db.get_house)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        tax_collected = await asyncio.to_thread(db.get_config, "tax_collected", "0")
        rake_pct = await asyncio.to_thread(db.get_config, "house_rake", "25")
        status = "📈 the house is up" if house >= 0 else "📉 the house is in the hole"
        devs = await asyncio.to_thread(db.get_config, "house_devs", "the devs")
        await ctx.reply(f"🏦 **house wallet:** {_s(house)} {coin_emoji} ({status})\n"
                        f"👑 **house owners:** {devs}\n"
                        f"🪒 **house rake:** {rake_pct}% on all wins\n"
                        f"💰 lifetime tax collected: {_s(int(tax_collected))} {coin_emoji}\n"
                        f"_gambling losses flow in, wins + streaks + insurance flow out_")

    @pure_houseclaim_command := pure_group.command(name="houseclaim", description="dev-only: claim the house wallet earnings")
    @is_dev()
    async def pure_houseclaim(ctx: commands.Context, amount: str = None):
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        house = await asyncio.to_thread(db.get_house)
        if house <= 0:
            await ctx.reply("nothing to claim, the house is broke or in the hole right now 😔")
            return
        if amount and amount.lower() == "all":
            claim = house
        elif amount:
            try:
                claim = min(int(amount), house)
            except ValueError:
                await ctx.reply("amount must be a number or 'all'")
                return
        else:
            claim = house
        if claim <= 0:
            return
        await asyncio.to_thread(db.update_house, -claim)
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, claim)
        await ctx.reply(f"🏦 claimed {claim} {coin_emoji} from the house. your balance: {new_balance} {coin_emoji}")

    @pure_bailout_command := pure_group.command(name="bailout", description="dev-only: inject or reset the house wallet")
    @is_dev()
    async def pure_bailout(ctx: commands.Context, amount: str = None):
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        house = await asyncio.to_thread(db.get_house)
        if amount and amount.lower() == "wipe":
            await asyncio.to_thread(db.set_config, "house_wallet", "0")
            await ctx.reply(f"🧹 house wallet wiped to 0 {coin_emoji}. fresh start")
            return
        if amount:
            try:
                injection = int(amount)
            except ValueError:
                await ctx.reply("amount must be a number or 'wipe'")
                return
            new_house = await asyncio.to_thread(db.update_house, injection)
            await ctx.reply(f"💉 injected {injection} {coin_emoji} into the house. new balance: {new_house} {coin_emoji}")
        else:
            await ctx.reply(f"house: {house} {coin_emoji}\nusage: `/pure bailout <amount>` to inject, `/pure bailout wipe` to zero it")

    @client.hybrid_command(name="leaderboard", description="view the richest players")
    @app_commands.describe(page="page number to view")
    async def leaderboard(ctx: commands.Context, page: int = 1):
        if ctx.guild is None:
            await ctx.reply("this command can only be used in a server")
            return

        await ctx.defer()

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        all_users = await asyncio.to_thread(db.get_all_balances)

        if not all_users:
            await ctx.reply("no one has any coins yet!")
            return

        all_users.sort(key=lambda u: u["balance"] + u["bank"], reverse=True)

        PAGE_SIZE = 10
        total_pages = max(1, (len(all_users) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(1, min(page, total_pages))

        embed = await build_leaderboard_embed(ctx, all_users, page, total_pages, coin_emoji)
        view = LeaderboardView(ctx, all_users, page, total_pages, coin_emoji)
        view.message = await ctx.reply(embed=embed, view=view)
        
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

        cheat = take_cheat(ctx.author.id, "fish_boost")
        fish_mult = cheat["value"] if cheat else 1
        
        if caught["max"] > 0:
            amount = random.randint(caught["min"], caught["max"]) * fish_mult
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

    @client.hybrid_command(name="deposit", description="deposit coins into your bank")
    @app_commands.describe(amount="amount to deposit")
    async def deposit(ctx: commands.Context, amount: str):
        amount = _to_bet(amount)
        if amount <= 0:
            await ctx.reply("amount must be greater than zero")
            return
            
        bal, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < amount and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins in your holding (holding: {bal})")
            return
            
        await asyncio.to_thread(db.update_balance, ctx.author.id, -amount)
        new_bank = await asyncio.to_thread(db.update_bank, ctx.author.id, amount)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"deposited {amount} {coin_emoji} into your bank. your bank balance is now {new_bank} {coin_emoji}")

    @client.hybrid_command(name="withdraw", description="withdraw coins from your bank")
    @app_commands.describe(amount="amount to withdraw")
    async def withdraw(ctx: commands.Context, amount: str):
        amount = _to_bet(amount)
        if amount <= 0:
            await ctx.reply("amount must be greater than zero")
            return
            
        _, bank, _ = await get_balance_checked(ctx, ctx.author.id)
        if bank < amount and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins in your bank (bank: {bank})")
            return
            
        await asyncio.to_thread(db.update_bank, ctx.author.id, -amount)
        new_bal = await asyncio.to_thread(db.update_balance, ctx.author.id, amount)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"withdrew {amount} {coin_emoji} from your bank. your holding balance is now {new_bal} {coin_emoji}")
    @client.hybrid_command(name="balance", description="view coin balance")
    @app_commands.describe(user="the user whose balance you want to check")
    async def balance(ctx: commands.Context, user: discord.Member = None):
        target = user or ctx.author
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        bal, bank, debt = await get_balance_checked(ctx, target.id)
        
        embed = discord.Embed(
            title=f"Balance - {target.display_name}",
            color=0x3498db
        )
        
        debt_line = f"\n**Debt: **💳`{_s(debt)}`" if debt > 0 else ""
        net = bal + bank - debt
        embed.description = f"**Net Worth: **{coin_emoji} `{_s(net)}`\n\n**Holding: **💰`{_s(bal)}`\n**Bank: **🏦`{_s(bank)}`{debt_line}\n\n-# birdvirus coin in the bank earn interest!"
        
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)
            
        await ctx.reply(embed=embed)

    # Loan command
    @client.hybrid_command(name="loan", description="take out a loan. interest is 10%")
    @app_commands.describe(amount="how many coins to borrow")
    async def loan(ctx: commands.Context, amount: str):
        amount = _to_bet(amount)
        if amount <= 0:
            await ctx.reply("amount must be greater than zero")
            return

        if amount > 10000:
            await ctx.reply("max loan is 10,000 coins")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        interest = int(amount * 0.1)
        total_debt = amount + interest

        await asyncio.to_thread(db.update_balance, ctx.author.id, amount)
        new_debt = await asyncio.to_thread(db.update_debt, ctx.author.id, total_debt)

        await ctx.reply(f"you took a loan of {amount} {coin_emoji} (10% interest = {interest} {coin_emoji}). total debt: {new_debt} {coin_emoji}")

    # Repay command
    @client.hybrid_command(name="repay", description="repay your debt")
    @app_commands.describe(amount="how many coins to put toward your debt")
    async def repay(ctx: commands.Context, amount: str):
        amount = _to_bet(amount)
        if amount <= 0:
            await ctx.reply("amount must be greater than zero")
            return

        bal, _, debt = await get_balance_checked(ctx, ctx.author.id)
        if debt <= 0:
            await ctx.reply("you have no debt")
            return

        if bal < amount:
            await ctx.reply(f"you don't have enough coins in your holding (holding: {bal}, debt: {debt})")
            return

        actual = min(amount, debt)
        await asyncio.to_thread(db.update_balance, ctx.author.id, -actual)
        new_debt = await asyncio.to_thread(db.update_debt, ctx.author.id, -actual)

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"you repaid {actual} {coin_emoji} of your debt. remaining debt: {new_debt} {coin_emoji}")

    # Debt check command
    @client.hybrid_command(name="debt", description="check your debt")
    async def debt_cmd(ctx: commands.Context):
        _, _, debt = await get_balance_checked(ctx, ctx.author.id)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        if debt <= 0:
            await ctx.reply(f"you have no debt {coin_emoji}")
        else:
            bal, bank, _ = await get_balance_checked(ctx, ctx.author.id)
            net = bal + bank - debt
            await ctx.reply(f"your debt: {debt} {coin_emoji} | holding: {bal} | bank: {bank} | net worth: {net} {coin_emoji}")
