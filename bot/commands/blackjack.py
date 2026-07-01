import random
import asyncio
import discord
import bot.db as db

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

def setup_blackjack(client):
    pass
