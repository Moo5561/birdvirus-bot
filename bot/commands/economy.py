import random
import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from bot.commands import is_admin
from bot.commands.blackjack import BlackjackView, draw_card

async def get_balance_checked(ctx, user_id):
    if ctx.bot.user and ctx.bot.user.id == 1522117141090799697:
        return 999999999999, 999999999999
    return await asyncio.to_thread(db.get_balances, user_id)

def setup_economy(client: commands.Bot):
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
            
        bal, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and ctx.bot.user.id != 1522117141090799697:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
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
            
        balance_val = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance_val < bet:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {balance_val})")
            return
            
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        
        player_hand = [draw_card(), draw_card()]
        dealer_hand = [draw_card(), draw_card()]
        
        player_total = player_hand[0][0] # Dummy logic, calculate_hand is better. But wait, we imported calculat_hand earlier? Let's check calculate_hand and draw_card.
        # Wait, let's use calculate_hand! We should import calculate_hand from blackjack.py as well.
        from bot.commands.blackjack import calculate_hand
        
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
            await ctx.reply("bet must be greater than zero")
            return
            
        bal, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and ctx.bot.user.id != 1522117141090799697:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return
            
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
                multiplier = 1.5
                status = f"two of a kind ({pair})!"
        else:
            multiplier = 0
            status = "no match. unlucky!"
            
        if multiplier > 0:
            net_gain = int(bet * multiplier) - bet
        else:
            net_gain = -bet
            
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)
        
        if net_gain > 0:
            status_text = f"{status}\nyou won {net_gain} {coin_emoji}! (balance: {new_balance})"
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
    async def pure_roulette(ctx: commands.Context, bet: int, guess: str):
        if bet <= 0:
            await ctx.reply("bet must be greater than zero")
            return
            
        bal, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and ctx.bot.user.id != 1522117141090799697:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return
            
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
            net_gain = int(bet * multiplier) - bet
        else:
            net_gain = -bet
            
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)
        
        if win:
            status_text = f"the ball landed on {result_color_emoji} {spin_result}!\nyou won {net_gain} {coin_emoji}! (balance: {new_balance})"
            color = 0x2ecc71
        else:
            status_text = f"the ball landed on {result_color_emoji} {spin_result}.\nyou lost {bet} {coin_emoji}. unlucky (balance: {new_balance})"
            color = 0xe74c3c
            
        embed.color = color
        embed.description = status_text.lower()
        await message.edit(embed=embed)

    @pure_plinko_command := pure_group.command(name="plinko", description="drop the ball down the plinko board")
    @app_commands.describe(bet="amount of coins to bet")
    async def pure_plinko(ctx: commands.Context, bet: int):
        if bet <= 0:
            await ctx.reply("bet must be greater than zero")
            return

        bal_val, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal_val < bet and ctx.bot.user.id != 1522117141090799697:
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal_val})")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        multipliers = [15, 5, 2, 0.5, 2, 5, 15]
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
        embed.description = "```\n  ⬇️\n```\ndropping..."
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
                rows.append(''.join(row_pegs))
            embed.description = "```\n  ⬇️\n" + "\n".join(rows) + "\n```\ndropping..."
            await message.edit(embed=embed)

        await asyncio.sleep(0.5)

        slots_row = ''.join([f'[{s}]' for s in slot_labels])
        mults_row = '  '.join([f'{m}x' for m in multipliers])

        net_gain = int(bet * multiplier) - bet
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, net_gain)

        if net_gain > 0:
            status = f"landed in {slot_labels[final_slot]} ({multiplier}x)\nyou won {net_gain} {coin_emoji} (balance: {new_balance})"
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

    @client.hybrid_command(name="deposit", description="deposit coins into your bank")
    @app_commands.describe(amount="amount to deposit")
    async def deposit(ctx: commands.Context, amount: int):
        if amount <= 0:
            await ctx.reply("amount must be greater than zero")
            return
            
        bal, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < amount and ctx.bot.user.id != 1522117141090799697:
            await ctx.reply(f"you don't have enough coins in your holding (holding: {bal})")
            return
            
        await asyncio.to_thread(db.update_balance, ctx.author.id, -amount)
        new_bank = await asyncio.to_thread(db.update_bank, ctx.author.id, amount)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"deposited {amount} {coin_emoji} into your bank. your bank balance is now {new_bank} {coin_emoji}")

    @client.hybrid_command(name="withdraw", description="withdraw coins from your bank")
    @app_commands.describe(amount="amount to withdraw")
    async def withdraw(ctx: commands.Context, amount: int):
        if amount <= 0:
            await ctx.reply("amount must be greater than zero")
            return
            
        _, bank = await get_balance_checked(ctx, ctx.author.id)
        if bank < amount and ctx.bot.user.id != 1522117141090799697:
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
        bal, bank = await get_balance_checked(ctx, target.id)
        
        embed = discord.Embed(
            title=f"Balance - {target.display_name}",
            color=0x3498db
        )
        
        embed.description = f"**Total Balance: **{coin_emoji} `{bal + bank:,}`\n\n**Holding: **💰`{bal:,}`\n**Bank: **🏦`{bank:,}`\n\n-# birdvirus coin in the bank earn interest!"
        
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)
            
        await ctx.reply(embed=embed)
