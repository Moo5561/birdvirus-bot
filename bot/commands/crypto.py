import asyncio
import random
import time
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from bot.commands import is_admin, is_nightly, _s

# crypto miner — a second economy on top of the main one.
# you mine coins into your own wallet with /mine, upgrade the rig,
# and /cashout turns mined coins into real coins (the house keeps a cut).

MINE_TIME = 8  # seconds a mine run takes
MINE_COOLDOWN = 300  # seconds between mines
HASH_EMOJI = "⚡"
CASHOUT_CUT = 0.10  # the house keeps this much of a cashout


def _yield(rig_level: int):
    """coins mined per run, scaled by rig level."""
    base = random.randint(3, 9)
    return base + rig_level * random.randint(1, 4)


def rig_upgrade_cost(rig_level: int) -> int:
    return 200 * rig_level


async def _report(ctx, text: str, title: str | None = None):
    color = 0x2b2d31
    embed = discord.Embed(title=title or "⛏️ crypto miner", description=text, color=color)
    try:
        await ctx.send(embed=embed)
    except Exception:
        await ctx.reply(embed=embed)


def setup_crypto(client: commands.Bot):
    @client.hybrid_command(name="mine", description="mine crypto into your own wallet (timer runs while you mine)")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def mine_cmd(ctx: commands.Context):
        wallet = await asyncio.to_thread(db.get_crypto_wallet, ctx.author.id)
        last = wallet["last_mine"]
        now = time.time()
        if last:
            elapsed = now - float(last)
            if elapsed < MINE_COOLDOWN:
                mins = int((MINE_COOLDOWN - elapsed) // 60) + 1
                await _report(ctx, f"your rig is still cooling down — try again in {mins} min. ")
                return

        msg = await ctx.send(
            f"{HASH_EMOJI} rig is spinning up at level {wallet['rig_level']}... "
        )

        for tick in range(MINE_TIME):
            await asyncio.sleep(1)
            hash_text = "".join(
                random.choice("01")
                for _ in range(wallet["rig_level"] + 3)
            )
            try:
                await msg.edit(
                    content=f"{HASH_EMOJI} `{hash_text}` mining... {tick + 1}/{MINE_TIME}s"
                )
            except Exception:
                pass

        gained = _yield(wallet["rig_level"])
        new_balance = wallet["balance"] + gained
        new_mined = wallet["mined_total"] + gained
        await asyncio.to_thread(
            db.set_crypto_wallet,
            ctx.author.id,
            new_balance,
            wallet["rig_level"],
            new_mined,
            str(now),
        )

        await _report(
            ctx,
            f"mined **{_s(gained)}** crypto in {MINE_TIME}s "
            f"(wallet: **{_s(new_balance)}**, lifetime: **{_s(new_mined)}**)",
            title="⚡ mine complete",
        )

    @client.hybrid_command(name="wallet", description="check your crypto wallet")
    @app_commands.describe(user="whose wallet to check (defaults to yours)")
    async def wallet_cmd(ctx: commands.Context, user: discord.User | None = None):
        target = user or ctx.author
        wallet = await asyncio.to_thread(db.get_crypto_wallet, target.id)
        level = wallet["rig_level"]
        yield_range = f"{3 + level}–{9 + level * 4}"
        embed = discord.Embed(
            title=f"⛏️ {target.display_name}'s wallet",
            color=0x2b2d31,
        )
        embed.add_field(name="crypto", value=f"**{_s(wallet['balance'])}**", inline=True)
        embed.add_field(name="lifetime mined", value=f"**{_s(wallet['mined_total'])}**", inline=True)
        embed.add_field(name="rig level", value=f"**{level}**", inline=True)
        embed.add_field(name="yield / run", value=f"**{yield_range}**", inline=True)
        await ctx.reply(embed=embed)

    @client.hybrid_command(name="rig", description="upgrade your mining rig for real coins")
    @app_commands.describe(level="rig level to buy (defaults to next level)")
    async def rig_cmd(ctx: commands.Context, level: int | None = None):
        wallet = await asyncio.to_thread(db.get_crypto_wallet, ctx.author.id)
        target = level or wallet["rig_level"] + 1
        if target <= wallet["rig_level"]:
            await _report(ctx, f"your rig is already level {wallet['rig_level']}, buy higher. ")
            return
        cost = sum(rig_upgrade_cost(l) for l in range(wallet["rig_level"], target))

        if is_nightly(ctx.bot):
            cost = 0

        bal = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if not is_nightly(ctx.bot) and bal < cost:
            await _report(
                ctx,
                f"upgrade to level {target} costs **{_s(cost)} coins** "
                f"(balance: {_s(bal)}) — mine regular coins first. ",
            )
            return

        await asyncio.to_thread(db.update_balance, ctx.author.id, -cost)
        await asyncio.to_thread(
            db.set_crypto_wallet,
            ctx.author.id,
            wallet["balance"],
            target,
            wallet["mined_total"],
            wallet["last_mine"],
        )
        await _report(
            ctx,
            f"rig upgraded to **level {target}** ({_s(cost)} coins spent). "
            f"new yield per run: **{3 + target}–{9 + target * 4}**",
            title="🛠️ rig upgraded",
        )

    @client.hybrid_command(name="cashout", description="turn mined crypto into real coins (the house keeps 10%)")
    @app_commands.describe(amount="amount of crypto to cash out ('all' for everything)")
    async def cashout_cmd(ctx: commands.Context, amount: str = "all"):
        wallet = await asyncio.to_thread(db.get_crypto_wallet, ctx.author.id)
        avail = wallet["balance"]
        if avail <= 0:
            await _report(ctx, "your wallet is empty — go mine something. ")
            return

        if str(amount).lower() == "all":
            take = avail
        else:
            try:
                take = int(amount)
            except ValueError:
                await _report(ctx, "give me an amount like 50, or 'all'. ")
                return
            if take <= 0:
                await _report(ctx, "that's not a real amount. ")
                return
            take = min(take, avail)

        cut = int(take * CASHOUT_CUT)
        payout = take - cut
        try:
            new_balance = await asyncio.to_thread(
                db.cashout_crypto, ctx.author.id, take, payout
            )
        except ValueError:
            await _report(ctx, "your wallet ran out of crypto mid-cashout — try again. ")
            return
        await _report(
            ctx,
            f"cashed out **{_s(payout)} coins** ({_s(take)} crypto, "
            f"the house kept {_s(cut)}). wallet: **{_s(avail - take)}**. "
            f"balance: **{_s(new_balance)}**",
            title="💰 cashout complete",
        )

    @client.hybrid_command(name="ctop", description="crypto miner leaderboard")
    async def ctop_cmd(ctx: commands.Context):
        rows = await asyncio.to_thread(db.get_crypto_leaderboard)
        if not rows:
            await _report(ctx, "nobody has mined anything yet. ")
            return
        lines = []
        for i, (uid, balance, mined) in enumerate(rows, 1):
            name = ctx.bot.get_user(uid).display_name if ctx.bot.get_user(uid) else f"<@{uid}>"
            lines.append(f"**{i}.** {name} — **{_s(mined)}** mined (wallet: {_s(balance)})")
        await _report(ctx, "\n".join(lines), title="⛏️ crypto miner leaderboard")