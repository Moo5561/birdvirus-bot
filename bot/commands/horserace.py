import random
import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db

HORSES = [
    {"name": "bolt", "emoji": "🐎", "min_roll": 2, "max_roll": 4, "odds": 2.0, "desc": "lightning fast, never misses a step"},
    {"name": "shadow", "emoji": "🐴", "min_roll": 1, "max_roll": 3, "odds": 2.5, "desc": "steady and silent, a reliable pick"},
    {"name": "blazer", "emoji": "🦄", "min_roll": 1, "max_roll": 4, "odds": 3.0, "desc": "wild and unpredictable, high risk high reward"},
    {"name": "meadow", "emoji": "🦓", "min_roll": 1, "max_roll": 3, "odds": 4.0, "desc": "the underdog who always tries their best"},
    {"name": "dusty", "emoji": "🐂", "min_roll": 1, "max_roll": 2, "odds": 5.0, "desc": "wait, that's not a horse... but he's angry and fast enough"},
]

TRACK_LENGTH = 16


def render_progress_bar(position: int, track_length: int = TRACK_LENGTH) -> str:
    filled = min(position, track_length)
    empty = track_length - filled
    return "▰" * filled + "▱" * empty


class HorseRaceView(discord.ui.View):
    def __init__(self, ctx: commands.Context, bet: int, coin_emoji: str):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.bet = bet
        self.coin_emoji = coin_emoji
        self.message: discord.Message | None = None
        self.selected_horse_idx: int | None = None
        self.horses = list(HORSES)

        options = []
        for i, horse in enumerate(self.horses):
            options.append(
                discord.SelectOption(
                    label=f"{horse['name'].title()} ({horse['odds']}x)",
                    value=str(i),
                    emoji=horse["emoji"],
                    description=f"rolls {horse['min_roll']}-{horse['max_roll']} per tick"
                )
            )
        self.select_horse.options = options

    def get_selection_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🏇 Horse Racing",
            description=f"place your bet of **{self.bet} {self.coin_emoji}**\npick a horse below:",
            color=0x2f3136
        )
        for i, horse in enumerate(self.horses):
            embed.add_field(
                name=f"{i+1}. {horse['emoji']} {horse['name'].title()} — {horse['odds']}x odds",
                value=f"*{horse['desc']}*\n`rolls {horse['min_roll']}-{horse['max_roll']} spaces per tick`",
                inline=False
            )
        embed.set_footer(text="the higher the odds, the riskier the pick...")
        return embed

    def get_race_embed(self, positions: list[int], tick: int = 0, status: str = "") -> discord.Embed:
        embed = discord.Embed(
            title="🏇 Race in Progress!" + (f" (tick {tick})" if tick > 0 else ""),
            color=0x2f3136
        )
        max_pos = max(positions)
        for i, horse in enumerate(self.horses):
            bar = render_progress_bar(positions[i])
            if positions[i] >= TRACK_LENGTH:
                status_icon = "🏁"
            elif positions[i] == max_pos and positions[i] > 0:
                status_icon = "👑"
            else:
                status_icon = horse["emoji"]
            embed.add_field(
                name=f"{i+1}. {horse['name'].title()}",
                value=f"`{status_icon}|{bar}|🏁`",
                inline=False
            )
        if status:
            embed.set_footer(text=status)
        return embed

    def get_result_embed(self, winner_idx: int, net_gain: int, new_balance: int, tied: bool = False) -> discord.Embed:
        winner = self.horses[winner_idx]
        won = net_gain > 0
        if won:
            color = 0xf1c40f if winner["odds"] >= 4.0 else 0x2ecc71
        else:
            color = 0xe74c3c

        if tied:
            title = f"🏁 photo finish! {winner['emoji']} {winner['name'].title()} takes it!"
        else:
            title = f"🏁 {winner['emoji']} {winner['name'].title()} wins by a landslide!"

        embed = discord.Embed(title=title, color=color)

        if won:
            embed.description = (
                f"**🎉 you won! 🎉**\n"
                f"your pick: {self.horses[self.selected_horse_idx]['emoji']} {self.horses[self.selected_horse_idx]['name'].title()}\n"
                f"payout: **{net_gain} {self.coin_emoji}** ({winner['odds']}x odds)\n"
                f"new balance: **{new_balance} {self.coin_emoji}**"
            )
        else:
            embed.description = (
                f"**😢 you lost!**\n"
                f"your pick: {self.horses[self.selected_horse_idx]['emoji']} {self.horses[self.selected_horse_idx]['name'].title()}\n"
                f"winner: {winner['emoji']} {winner['name'].title()}\n"
                f"you lost **{self.bet} {self.coin_emoji}**\n"
                f"balance: **{new_balance} {self.coin_emoji}**"
            )
        return embed

    async def start(self, ctx: commands.Context):
        self.message = await ctx.reply(embed=self.get_selection_embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("this is not your race dude", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="pick your horse...",
        options=[],
        min_values=1,
        max_values=1
    )
    async def select_horse(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_horse_idx = int(select.values[0])

        # safety balance check
        bal = await asyncio.to_thread(db.get_balance, self.ctx.author.id)
        if bal < self.bet and (not self.ctx.bot.user or self.ctx.bot.user.id != 1522117141090799697):
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="insufficient funds",
                    description=f"you need {self.bet} {self.coin_emoji} to race (balance: {bal})",
                    color=0xe74c3c
                ),
                view=None
            )
            self.stop()
            return

        # show starting line
        await interaction.response.edit_message(
            embed=self.get_race_embed([0] * 5, tick=0, status="starting gates open..."),
            view=None
        )

        await asyncio.sleep(1.0)

        positions = [0] * len(self.horses)
        tick = 0
        winner_idx = None

        while winner_idx is None:
            await asyncio.sleep(0.9)
            tick += 1

            for i, horse in enumerate(self.horses):
                if positions[i] < TRACK_LENGTH:
                    roll = random.randint(horse["min_roll"], horse["max_roll"])
                    # stumble / sprint mechanics
                    chance = random.random()
                    if chance < 0.05:
                        roll = max(0, roll - 2)
                    elif chance < 0.10:
                        roll += 1
                    positions[i] += roll

            # determine if race is over
            finished = [i for i, pos in enumerate(positions) if pos >= TRACK_LENGTH]
            if finished:
                max_pos = max(positions)
                leaders = [i for i, pos in enumerate(positions) if pos == max_pos]
                winner_idx = random.choice(leaders)
                break

            chosen = self.horses[self.selected_horse_idx]
            status = f"tick {tick}... {chosen['emoji']} {chosen['name'].title()} is running!"
            await self.message.edit(embed=self.get_race_embed(positions, tick, status))

        # final race frame
        final_status = f"race finished in {tick} ticks!"
        await self.message.edit(embed=self.get_race_embed(positions, tick, final_status))
        await asyncio.sleep(1.0)

        # payout
        won = (winner_idx == self.selected_horse_idx)
        if won:
            net_gain = int(self.bet * self.horses[winner_idx]["odds"]) - self.bet
        else:
            net_gain = -self.bet

        new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, net_gain)
        tied = len([p for p in positions if p == max(positions)]) > 1

        result_embed = self.get_result_embed(winner_idx, net_gain, new_balance, tied=tied)
        await self.message.edit(embed=result_embed)
        self.stop()

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(title="race cancelled", color=0x95a5a6),
            view=None
        )
        self.stop()

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(title="race timed out", description="you took too long to pick a horse", color=0x95a5a6),
                    view=None
                )
            except Exception:
                pass
        self.stop()


def setup_horserace(client: commands.Bot):
    pass
