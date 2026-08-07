import random
import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timezone
import bot.db as db
from bot.commands import is_admin, is_nightly, game_lock, game_unlock, _s

# birdvirus stock exchange — a fake market for fake coins.
# every ticker drifts around on a seeded random walk, persisted in stock_state.

STOCKS = [
    {"ticker": "BIRD", "name": "BirdTech Inc", "emoji": "🐦", "base": 10000, "vol": 0.08},
    {"ticker": "VAC", "name": "VaxCorp Labs", "emoji": "💉", "base": 20000, "vol": 0.12},
    {"ticker": "DROID", "name": "DroidSound Co", "emoji": "🤖", "base": 15000, "vol": 0.15},
    {"ticker": "PECK", "name": "PeckCoin Mining", "emoji": "⛏️", "base": 5000, "vol": 0.20},
    {"ticker": "FEED", "name": "Seed & Feed", "emoji": "🌻", "base": 8000, "vol": 0.06},
]

HIST_LEN = 12


def utc_now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def sparkline(hist):
    if not hist:
        return ""
    lo, hi = min(hist), max(hist)
    if hi == lo:
        return "▬" * min(len(hist), 12)
    bars = "▁▂▃▄▅▆▇█"
    return "".join(bars[min(7, int((p - lo) / (hi - lo) * 8))] for p in hist)


def ensure_stock(ticker):
    """seed a ticker's price/history row on first contact."""
    if db.get_stock_price(ticker) is None:
        hist = [s["base"] for s in STOCKS if s["ticker"] == ticker]
        db.set_stock_price(ticker, hist[0], [], utc_now_str())


def drift_ticker(ticker, force_trend=None):
    """random walk the ticker. force_trend (0..1) biases direction for crashes."""
    s = next((x for x in STOCKS if x["ticker"] == ticker), None)
    if s is None:
        return
    price = db.get_stock_price(ticker) or s["base"]
    vol = s["vol"]
    if force_trend is None:
        drift = random.gauss(0, vol)
    else:
        drift = random.gauss(force_trend - 0.5, vol)
    drift = max(-0.5, min(0.5, drift))
    price = max(100, int(price * (1 + drift)))
    hist = db.get_stock_history(ticker)
    hist.append(price)
    if len(hist) > HIST_LEN:
        hist = hist[-HIST_LEN:]
    db.set_stock_price(ticker, price, hist, utc_now_str())


def setup_stocks(client: commands.Bot):
    @tasks.loop(seconds=12.0)
    async def market_loop():
        for s in STOCKS:
            try:
                await asyncio.to_thread(drift_ticker, s["ticker"])
            except Exception as e:
                print(f"error drifting {s['ticker']}: {e}")

    @client.listen("on_ready")
    async def start_market_loop():
        for s in STOCKS:
            try:
                await asyncio.to_thread(ensure_stock, s["ticker"])
            except Exception as e:
                print(f"error seeding {s['ticker']}: {e}")
        if not market_loop.is_running():
            market_loop.start()

    @client.hybrid_group(name="stock", description="birdvirus stock exchange")
    async def stock_group(ctx: commands.Context):
        pass

    @stock_group.command(name="market", description="view live stock prices")
    async def stock_market(ctx: commands.Context):
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        embed = discord.Embed(
            title="📈 Birdvirus Stock Exchange",
            description="prices drift in real time. buy low, sell high, lose everything.",
            color=0x2f3136,
        )

        lines = []
        for s in STOCKS:
            price = await asyncio.to_thread(db.get_stock_price, s["ticker"])
            hist = await asyncio.to_thread(db.get_stock_history, s["ticker"])
            change = ""
            if len(hist) >= 2:
                diff = price - hist[0]
                arrow = "📈" if diff >= 0 else "📉"
                change = f" {arrow} {_s(abs(diff))}"
            lines.append(
                f"{s['emoji']} **{s['ticker']}** · *{s['name']}*\n"
                f"┣ price: {coin_emoji} `{_s(price)}`{change}\n"
                f"┗ `{sparkline(hist)}`"
            )
        embed.description = "\n\n".join(lines)
        embed.set_footer(text="buy/sell with /stock buy <ticker> <shares>")
        await ctx.reply(embed=embed)

    @stock_group.command(name="buy", description="buy shares of a stock")
    @app_commands.describe(ticker="which stock to buy (BIRD, VAC, DROID, PECK, FEED)", shares="how many shares")
    async def stock_buy(ctx: commands.Context, ticker: str, shares: int):
        ticker = ticker.strip().upper()
        stock = next((s for s in STOCKS if s["ticker"] == ticker), None)
        if stock is None:
            valid = ", ".join(s["ticker"] for s in STOCKS)
            await ctx.reply(f"unknown ticker `{ticker}`. valid: {valid}")
            return
        if shares <= 0:
            await ctx.reply("shares must be a positive number")
            return

        await asyncio.to_thread(ensure_stock, ticker)
        price = await asyncio.to_thread(db.get_stock_price, ticker)
        cost = price * shares

        bal, _, _ = await asyncio.to_thread(db.get_balances, ctx.author.id)
        if bal < cost and not is_nightly(ctx.bot):
            await ctx.reply(f"you can't afford {shares} shares of {ticker} ({cost} coins, balance: {bal})")
            return

        game_lock(ctx)
        try:
            await asyncio.to_thread(db.update_balance, ctx.author.id, -cost)
            await asyncio.to_thread(db.update_house, cost)
            holdings = await asyncio.to_thread(db.get_stock_holdings, ctx.author.id)
            holdings[ticker] = holdings.get(ticker, 0) + shares
            await asyncio.to_thread(db.set_stock_shares, ctx.author.id, ticker, holdings[ticker])
            coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
            new_balance = await asyncio.to_thread(db.get_balance, ctx.author.id)
            await ctx.reply(
                f"📈 bought {shares} share(s) of {stock['emoji']} **{ticker}** @ {coin_emoji} {_s(price)} each "
                f"({_s(cost)} total). now holding {holdings[ticker]} shares. balance: {_s(new_balance)} {coin_emoji}"
            )
        finally:
            game_unlock(ctx)

    @stock_group.command(name="sell", description="sell shares of a stock")
    @app_commands.describe(ticker="which stock to sell", shares="how many shares")
    async def stock_sell(ctx: commands.Context, ticker: str, shares: int):
        ticker = ticker.strip().upper()
        stock = next((s for s in STOCKS if s["ticker"] == ticker), None)
        if stock is None:
            valid = ", ".join(s["ticker"] for s in STOCKS)
            await ctx.reply(f"unknown ticker `{ticker}`. valid: {valid}")
            return
        if shares <= 0:
            await ctx.reply("shares must be a positive number")
            return

        holdings = await asyncio.to_thread(db.get_stock_holdings, ctx.author.id)
        held = holdings.get(ticker, 0)
        if held <= 0:
            await ctx.reply(f"you don't hold any {ticker}")
            return

        shares = min(shares, held)
        price = await asyncio.to_thread(db.get_stock_price, ticker)
        proceeds = price * shares

        game_lock(ctx)
        try:
            await asyncio.to_thread(db.update_balance, ctx.author.id, proceeds)
            await asyncio.to_thread(db.update_house, -proceeds)
            holdings[ticker] = held - shares
            if holdings[ticker] <= 0:
                del holdings[ticker]
                await asyncio.to_thread(db.set_stock_shares, ctx.author.id, ticker, 0)
            else:
                await asyncio.to_thread(db.set_stock_shares, ctx.author.id, ticker, holdings[ticker])
            coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
            new_balance = await asyncio.to_thread(db.get_balance, ctx.author.id)
            await ctx.reply(
                f"📉 sold {shares} share(s) of {stock['emoji']} **{ticker}** @ {coin_emoji} {_s(price)} each "
                f"({_s(proceeds)} total). remaining: {holdings.get(ticker, 0)} shares. balance: {_s(new_balance)} {coin_emoji}"
            )
        finally:
            game_unlock(ctx)

    @stock_group.command(name="portfolio", description="view your stock holdings")
    async def stock_portfolio(ctx: commands.Context):
        holdings = await asyncio.to_thread(db.get_stock_holdings, ctx.author.id)
        if not holdings:
            await ctx.reply("you don't hold any stocks yet. use `/stock buy` to get in the game")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        embed = discord.Embed(
            title=f"💼 {ctx.author.display_name}'s portfolio",
            color=0x2f3136,
        )
        total = 0
        lines = []
        for ticker, shares in holdings.items():
            if shares <= 0:
                continue
            stock = next((s for s in STOCKS if s["ticker"] == ticker), None)
            if stock is None:
                continue
            price = await asyncio.to_thread(db.get_stock_price, ticker)
            value = price * shares
            total += value
            lines.append(
                f"{stock['emoji']} **{ticker}** · {shares} share(s)\n"
                f"┗ value: {coin_emoji} `{_s(value)}` (at `{_s(price)}`/share)"
            )
        embed.description = "\n\n".join(lines)
        embed.set_footer(text=f"total value: {coin_emoji} {_s(total)}")
        await ctx.reply(embed=embed)
