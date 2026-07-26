import random
import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db

CATS = [
    {
        "name": "whiskers",
        "emoji": "🐈",
        "min_roll": 2,
        "max_roll": 4,
        "odds": 2.0,
        "desc": "a sleek tabby with laser focus. always on the prowl.",
    },
    {
        "name": "mittens",
        "emoji": "😸",
        "min_roll": 1,
        "max_roll": 4,
        "odds": 3.0,
        "desc": "chaotic ginger energy. either zooms or naps, no in between.",
    },
    {
        "name": "shadow",
        "emoji": "🐈‍⬛",
        "min_roll": 1,
        "max_roll": 3,
        "odds": 2.5,
        "desc": "a mysterious black cat. moves silently, strikes fast.",
    },
    {
        "name": "smoosh",
        "emoji": "😻",
        "min_roll": 1,
        "max_roll": 3,
        "odds": 4.0,
        "desc": "a persian with a flat face and big dreams.",
    },
    {
        "name": "noodle",
        "emoji": "🐱",
        "min_roll": 1,
        "max_roll": 2,
        "odds": 5.0,
        "desc": "long. skinny. confused. somehow still racing.",
    },
]

TRACK_LENGTH = 16


def render_progress_bar(position: int, track_length: int = TRACK_LENGTH) -> str:
    filled = min(position, track_length)
    empty = track_length - filled
    return "▰" * filled + "▱" * empty


# event hooks that can modify a cat's movement each tick
def cat_event(roll: int, cat: dict, tick: int) -> tuple[int, str]:
    """returns (modified_roll, event_message). event_message is '' if nothing happened."""
    chance = random.random()

    # 8% chance: cat sees a laser pointer and zooms
    if chance < 0.08:
        return roll + 2, "🔴 laser pointer sighting! zoomies!"

    # 8% chance: cat gets distracted by a box
    if chance < 0.16:
        return max(0, roll - 2), "📦 got distracted by a cardboard box"

    # 5% chance: catnip boost
    if chance < 0.21:
        return roll + 1, "🌿 found some catnip on the track"

    # 5% chance: cat stops to groom itself
    if chance < 0.26:
        return max(0, roll - 1), "🧹 stopped to groom itself mid-race"

    # 3% chance: cat knocks something over and gains momentum
    if chance < 0.29:
        return roll + 3, "💥 knocked over a trash can and gained momentum!"

    # 2% chance: cat falls asleep
    if chance < 0.31:
        return 0, "😴 fell asleep on the track..."

    return roll, ""


class CatRaceView(discord.ui.View):
    def __init__(self, ctx: commands.Context, bet: int, coin_emoji: str):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.bet = bet
        self.coin_emoji = coin_emoji
        self.message: discord.Message | None = None
        self.selected_cat_idx: int | None = None
        self.cats = list(CATS)

        options = []
        for i, cat in enumerate(self.cats):
            options.append(
                discord.SelectOption(
                    label=f"{cat['name'].title()} ({cat['odds']}x)",
                    value=str(i),
                    emoji=cat["emoji"],
                    description=f"rolls {cat['min_roll']}-{cat['max_roll']} per tick",
                )
            )
        self.select_cat.options = options

    def get_selection_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🐱 Cat Racing",
            description=(
                f"place your bet of **{self.bet} {self.coin_emoji}**\n"
                f"pick your champion below:"
            ),
            color=0x2f3136,
        )
        for i, cat in enumerate(self.cats):
            embed.add_field(
                name=f"{i+1}. {cat['emoji']} {cat['name'].title()} — {cat['odds']}x odds",
                value=f"*{cat['desc']}*\n`rolls {cat['min_roll']}-{cat['max_roll']} spaces per tick`",
                inline=False,
            )
        embed.set_footer(text="expect chaos... cats are unpredictable")
        return embed

    def get_race_embed(
        self, positions: list[int], events: list[str], tick: int = 0, status: str = ""
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🐾 Cat Race in Progress!" + (f" (tick {tick})" if tick > 0 else ""),
            color=0x2f3136,
        )
        max_pos = max(positions) if positions else 0
        for i, cat in enumerate(self.cats):
            bar = render_progress_bar(positions[i])
            if positions[i] >= TRACK_LENGTH:
                status_icon = "🏁"
            elif positions[i] == max_pos and positions[i] > 0:
                status_icon = "👑"
            else:
                status_icon = cat["emoji"]

            event_text = f"\n*{events[i]}*" if events[i] else ""
            embed.add_field(
                name=f"{i+1}. {cat['name'].title()}",
                value=f"`{status_icon}|{bar}|🏁`{event_text}",
                inline=False,
            )
        if status:
            embed.set_footer(text=status)
        return embed

    def get_result_embed(
        self,
        winner_idx: int,
        net_gain: int,
        new_balance: int,
        tied: bool = False,
    ) -> discord.Embed:
        winner = self.cats[winner_idx]
        won = net_gain > 0

        if won:
            color = 0xf1c40f if winner["odds"] >= 4.0 else 0x2ecc71
        else:
            color = 0xe74c3c

        if tied:
            title = f"🏁 photo finish! {winner['emoji']} {winner['name'].title()} takes it!"
        else:
            title = f"🏁 {winner['emoji']} {winner['name'].title()} crosses the line first!"

        embed = discord.Embed(title=title, color=color)

        if won:
            embed.description = (
                f"**🎉 you won! 🎉**\n"
                f"your pick: {self.cats[self.selected_cat_idx]['emoji']} {self.cats[self.selected_cat_idx]['name'].title()}\n"
                f"payout: **{net_gain} {self.coin_emoji}** ({winner['odds']}x odds)\n"
                f"new balance: **{new_balance} {self.coin_emoji}**"
            )
        else:
            embed.description = (
                f"**😢 you lost!**\n"
                f"your pick: {self.cats[self.selected_cat_idx]['emoji']} {self.cats[self.selected_cat_idx]['name'].title()}\n"
                f"winner: {winner['emoji']} {winner['name'].title()}\n"
                f"you lost **{self.bet} {self.coin_emoji}**\n"
                f"balance: **{new_balance} {self.coin_emoji}**"
            )
        return embed

    async def start(self, ctx: commands.Context):
        self.message = await ctx.reply(embed=self.get_selection_embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "this is not your race dude", ephemeral=True
            )
            return False
        return True

    @discord.ui.select(
        placeholder="pick your cat...",
        options=[],
        min_values=1,
        max_values=1,
    )
    async def select_cat(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        self.selected_cat_idx = int(select.values[0])

        # safety balance check
        bal = await asyncio.to_thread(db.get_balance, self.ctx.author.id)
        if (
            bal < self.bet
            and (
                not self.ctx.bot.user
                or self.ctx.bot.user.id != 1522117141090799697
            )
        ):
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="insufficient funds",
                    description=f"you need {self.bet} {self.coin_emoji} to race (balance: {bal})",
                    color=0xe74c3c,
                ),
                view=None,
            )
            self.stop()
            return

        # show starting line
        await interaction.response.edit_message(
            embed=self.get_race_embed(
                [0] * len(self.cats),
                [""] * len(self.cats),
                tick=0,
                status="the gates open... the cats are sizing each other up",
            ),
            view=None,
        )

        await asyncio.sleep(1.0)

        positions = [0] * len(self.cats)
        tick = 0
        winner_idx = None

        while winner_idx is None:
            await asyncio.sleep(0.9)
            tick += 1

            events = [""] * len(self.cats)

            for i, cat in enumerate(self.cats):
                if positions[i] < TRACK_LENGTH:
                    roll = random.randint(cat["min_roll"], cat["max_roll"])
                    modified_roll, event_msg = cat_event(roll, cat, tick)
                    positions[i] += modified_roll
                    if event_msg:
                        events[i] = f"{cat['emoji']} {event_msg}"

            # determine if race is over
            finished = [
                i for i, pos in enumerate(positions) if pos >= TRACK_LENGTH
            ]
            if finished:
                max_pos = max(positions)
                leaders = [
                    i for i, pos in enumerate(positions) if pos == max_pos
                ]
                winner_idx = random.choice(leaders)
                break

            chosen = self.cats[self.selected_cat_idx]
            status = f"tick {tick}... {chosen['emoji']} {chosen['name'].title()} is on the move!"
            await self.message.edit(
                embed=self.get_race_embed(positions, events, tick, status)
            )

        # final race frame
        final_events = [""] * len(self.cats)
        for i in range(len(self.cats)):
            if i == winner_idx:
                final_events[i] = f"{self.cats[i]['emoji']} 🏆 winner!"
        final_status = f"race finished in {tick} ticks!"
        await self.message.edit(
            embed=self.get_race_embed(
                positions, final_events, tick, final_status
            )
        )
        await asyncio.sleep(1.0)

        # payout
        won = winner_idx == self.selected_cat_idx
        if won:
            net_gain = int(self.bet * self.cats[winner_idx]["odds"]) - self.bet
        else:
            net_gain = -self.bet

        new_balance = await asyncio.to_thread(
            db.update_balance, self.ctx.author.id, net_gain
        )
        tied = len([p for p in positions if p == max(positions)]) > 1

        result_embed = self.get_result_embed(
            winner_idx, net_gain, new_balance, tied=tied
        )
        await self.message.edit(embed=result_embed)
        self.stop()

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.red)
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="race cancelled", color=0x95a5a6
            ),
            view=None,
        )
        self.stop()

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(
                        title="race timed out",
                        description="you took too long to pick a cat",
                        color=0x95a5a6,
                    ),
                    view=None,
                )
            except Exception:
                pass
        self.stop()


def setup_catrace(client: commands.Bot):
    pass
