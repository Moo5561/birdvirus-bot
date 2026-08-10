import asyncio
import random
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from bot.commands import (
    is_nightly,
    game_lock,
    game_unlock,
    claim_streak_bonus,
    track_gamble,
    _s,
)
from bot.commands.economy import apply_tax, get_balance_checked, _to_bet

HOUSE_EDGE = 0.95  # cashouts pay out bet * mult, edge goes to the house
TICK_TIME = 0.5  # seconds per multiplier tick
MULT_STEP = 0.06  # multiplier added per tick


def _payout(bet, mult):
    if type(mult) is int:
        return bet * mult
    n, d = mult.as_integer_ratio()
    return bet * n // d


def _roll_crash_mult():
    """returns a multiplier the rocket will crash at, with a
    P(> m) = HOUSE_EDGE / m distribution so the house keeps our edge."""
    u = random.random()
    mult = HOUSE_EDGE / (u or 1e-9)
    return max(1.20, min(100.0, mult))


class CrashView(discord.ui.View):
    def __init__(self, ctx, bet, coin_emoji):
        super().__init__(timeout=90.0)
        self.ctx = ctx
        self.bet = bet
        self.coin_emoji = coin_emoji
        self.message = None
        self.mult = 0.00
        self.crash_mult = _roll_crash_mult()
        self._crashed = False
        self._cashed_out = False
        self._task = None

    def _bar(self):
        width = 16
        filled = int(min(1.0, self.mult / 20.0) * width)
        return "🟥" * filled + "⬛" * (width - filled)

    def _embed(self, status="rocket taking off..."):
        embed = discord.Embed(
            title=f"🚀 service it LOADS {self.mult:.2f}x",
            color=0x2f3136,
        )
        embed.description = (
            f"`{self._bar()}`\n"
            f"cash out now to lock in **{_s(_payout(self.bet, self.mult))} {self.coin_emoji}**\n"
            f"bet: **{self.bet} {self.coin_emoji}**"
        )
        embed.set_footer(text=status)
        return embed

    async def start(self, ctx):
        self.message = await ctx.reply(embed=self._embed(), view=self)
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        try:
            while not self._crashed and not self._cashed_out:
                await asyncio.sleep(TICK_TIME)
                self.mult += MULT_STEP
                if self.mult >= self.crash_mult:
                    self._crashed = True
                    await self._settle()
                    return
                await self.message.edit(embed=self._embed(status="📈"))
        except Exception as e:
            print(f"crash loop error: {e}")
            self.stop()

    async def _settle(self, cashed_out: bool = False):
        if self.message is None:
            return

        if cashed_out:
            net_gain = _payout(self.bet, self.mult) - self.bet
            color = 0x2ecc71
            title = f"✅ cashed out at {self.mult:.2f}x"
            text = "you got out before the crash, nice."
        else:
            net_gain = -self.bet
            color = 0xe74c3c
            title = f"💥 the rocket crashed at {self.crash_mult:.2f}x"
            text = f" you were holding at {self.mult:.2f}x. gone."

        new_balance = await asyncio.to_thread(db.update_balance, self.ctx.author.id, net_gain)
        await track_gamble(self.ctx, net_gain)

        embed = discord.Embed(title=title, color=color)
        if net_gain > 0:
            tax = await apply_tax(self.ctx, self.ctx.author.id, net_gain)
            embed.description = (
                f"{text}\n"
                f"won **{_s(net_gain)} {self.coin_emoji}** (balance: **{_s(new_balance)} {self.coin_emoji}**)\n"
                f"tax: {tax} {self.coin_emoji}"
            )
        else:
            embed.description = (
                f"{text}\n"
                f"lost **{_s(abs(net_gain))} {self.coin_emoji}** (balance: **{_s(new_balance)} {self.coin_emoji}**)  "
            )
        await self.message.edit(embed=embed, view=None)
        self.stop()
        game_unlock(self.ctx)

    @discord.ui.button(label="💵 cash out", style=discord.ButtonStyle.green)
    async def cash_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("this is not your rocket dude", ephemeral=True)
            return
        if self._cashed_out or self._crashed:
            return
        self._cashed_out = True
        await interaction.response.defer()
        await self._settle(cashed_out=True)

    async def on_timeout(self):
        self._crashed = True
        if self._task:
            self._task.cancel()
        if self.message:
            try:
                embed = discord.Embed(
                    title="💥 crash view timed out",
                    description=f"you didn't cash out. the rocket crashed at {self.crash_mult:.2f}x.",
                    color=0x95a5a6,
                )
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass
        game_unlock(self.ctx)


def setup_crash(client: commands.Bot):
    @client.hybrid_command(name="crash", description="ride the rocket: cash out before it crashes")
    @app_commands.describe(bet="amount of coins to bet")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def crash_cmd(ctx: commands.Context, bet: str):
        bet = _to_bet(bet)

        bal, _, _ = await get_balance_checked(ctx, ctx.author.id)
        if bal < bet and not is_nightly(ctx.bot):
            await ctx.reply(f"you don't have enough coins to bet {bet} (balance: {bal})")
            return

        await claim_streak_bonus(ctx)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        game_lock(ctx)
        view = CrashView(ctx, bet, coin_emoji)
        await view.start(ctx)