import io
import random
import asyncio
import time
import aiohttp
import discord
import discord.ext.commands as commands
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timezone
import matplotlib.pyplot as plt
import bot.db as db
from bot.commands import is_admin, is_nightly, game_lock, game_unlock, _s

# birdvirus stock exchange — a fake market for fake coins.
# every ticker drifts around on a seeded random walk, persisted in stock_state.
# tickers flagged `real` track their actual stock price instead of a fake walk.

STOCKS = [
    {"ticker": "BIRD", "name": "BirdTech Inc", "emoji": "🐦", "base": 10000, "vol": 0.08, "color": "#00e5ff"},
    {"ticker": "VAC", "name": "VaxCorp Labs", "emoji": "💉", "base": 20000, "vol": 0.12, "color": "#00ff88"},
    {"ticker": "DROID", "name": "DroidSound Co", "emoji": "🤖", "base": 15000, "vol": 0.15, "color": "#ffaa00"},
    {"ticker": "PECK", "name": "PeckCoin Mining", "emoji": "⛏️", "base": 5000, "vol": 0.20, "color": "#ff4444"},
    {"ticker": "FEED", "name": "Seed & Feed", "emoji": "🌻", "base": 8000, "vol": 0.06, "color": "#aa66ff"},
    {"ticker": "SCRAM", "name": "Scramble Jet Fuels", "emoji": "✈️", "base": 18000, "vol": 0.10, "color": "#ff5577"},
    {"ticker": "NEST", "name": "NestEgg Realty", "emoji": "🥚", "base": 30000, "vol": 0.06, "color": "#ffdd66"},
    {"ticker": "SCAM", "name": "Totally Legit Coin", "emoji": "🐍", "base": 2500, "vol": 0.25, "color": "#cc44ff"},
    {"ticker": "PLUG", "name": "Plugs & Feathers", "emoji": "🪶", "base": 12000, "vol": 0.14, "color": "#77ccff"},
    {"ticker": "RBLX", "name": "rblxses.real", "emoji": "🎮", "base": 9000, "vol": 0.18, "color": "#ff8800", "real": True, "symbol": "RBLX"},
]

HIST_LEN = 12

REAL_FETCH_COOLDOWN = 45  # seconds between real price fetches
_real_last_fetch = {}


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


def build_market_chart(all_hist):
    """render each ticker on its own subplot (y = % change) to a BytesIO png."""
    plotted = [(t, h) for t, h in all_hist.items() if h]
    if not plotted and all_hist:
        plotted = [(list(all_hist.keys())[0], [])]
    if not plotted:
        return None
    n = len(plotted)

    cols = min(3, n)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(13, 3.4 * rows), facecolor="#1a1a1a")
    flat = [axes] if n == 1 else [ax for row in axes for ax in row]

    for idx, (ticker, hist) in enumerate(plotted):
        ax = flat[idx]
        ax.set_facecolor("#1a1a1a")
        stock = next((s for s in STOCKS if s["ticker"] == ticker), None)
        color = stock["color"] if stock else "#ffffff"

        if hist and hist[0]:
            pct = [(p / hist[0] - 1) * 100 for p in hist]
        else:
            pct = []

        ax.plot(range(len(pct)), pct, marker="o", markersize=3.5, color=color,
                linewidth=2.2, alpha=0.95)
        if pct:
            ax.fill_between(range(len(pct)), pct, color=color, alpha=0.10)

        current = hist[-1] if hist else (stock["base"] if stock else 0)
        emoji = stock["emoji"] if stock else ""
        name = stock["name"] if stock else ticker
        ax.set_title(f"{emoji} {ticker} · {name} · {current:,}", color="white",
                     fontsize=10, fontweight="bold")

        ax.axhline(0, color="#555555", linewidth=1, linestyle="--")
        ax.tick_params(axis="x", colors="white", labelsize=8)
        ax.tick_params(axis="y", colors="white", labelsize=8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("bottom", "left"):
            ax.spines[spine].set_color("#666666")
        ax.grid(axis="y", alpha=0.15, color="white", linestyle="--")

        if pct:
            lo, hi = min(pct), max(pct)
            pad = (hi - lo) * 0.15 if hi != lo else 1
            ax.set_ylim(lo - pad, hi + pad)

    for idx in range(n, len(flat)):
        flat[idx].axis("off")

    fig.suptitle("📈 birdvirus stock exchange — % change per ticker",
                 color="white", fontsize=15, fontweight="bold", y=1.005)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#1a1a1a")
    buf.seek(0)
    plt.close(fig)
    return buf


def ensure_stock(ticker):
    """seed a ticker's price/history row on first contact."""
    if db.get_stock_price(ticker) is None:
        hist = [s["base"] for s in STOCKS if s["ticker"] == ticker]
        db.set_stock_price(ticker, hist[0], [], utc_now_str())


def record_price(ticker, price):
    """append a price to a ticker's history row and persist it."""
    hist = db.get_stock_history(ticker)
    hist.append(int(price))
    if len(hist) > HIST_LEN:
        hist = hist[-HIST_LEN:]
    db.set_stock_price(ticker, int(price), hist, utc_now_str())


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
    record_price(ticker, price)


async def fetch_real_price(symbol):
    """grab the current market price from yahoo finance."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(
            url,
            params={"range": "1d", "interval": "1m"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            data = await resp.json()
    result = data["chart"]["result"]
    if not result:
        raise ValueError(f"no chart data for {symbol}")
    meta = result[0]["meta"]
    price = meta.get("regularMarketPrice")
    if price is None:
        raise ValueError(f"no price for {symbol}")
    return price


def setup_stocks(client: commands.Bot):
    @tasks.loop(seconds=12.0)
    async def market_loop():
        for s in STOCKS:
            try:
                if s.get("real"):
                    now = time.time()
                    last = _real_last_fetch.get(s["ticker"], 0)
                    if now - last < REAL_FETCH_COOLDOWN:
                        continue
                    price = await fetch_real_price(s["symbol"])
                    _real_last_fetch[s["ticker"]] = now
                    await asyncio.to_thread(record_price, s["ticker"], price)
                else:
                    await asyncio.to_thread(drift_ticker, s["ticker"])
            except Exception as e:
                print(f"error updating {s['ticker']}: {e}")

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
        await ctx.defer()
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        embed = discord.Embed(
            title="📈 Birdvirus Stock Exchange",
            color=0x2f3136,
        )

        lines = []
        all_hist = {}
        for s in STOCKS:
            price = await asyncio.to_thread(db.get_stock_price, s["ticker"])
            if price is None:
                price = s["base"]
            hist = await asyncio.to_thread(db.get_stock_history, s["ticker"]) or []
            all_hist[s["ticker"]] = hist
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
        embed.set_footer(text="live % change chart below • /stock buy <ticker> <shares>")

        chart_buf = await asyncio.to_thread(build_market_chart, all_hist)
        if chart_buf:
            embed.set_image(url="attachment://stocks_chart.png")
            file = discord.File(chart_buf, filename="stocks_chart.png")
            await ctx.reply(embed=embed, file=file)
        else:
            await ctx.reply(embed=embed)

    @stock_group.command(name="buy", description="buy shares of a stock")
    @app_commands.describe(ticker="which stock to buy (BIRD, VAC, DROID, PECK, FEED, SCRAM, NEST, SCAM, PLUG)", shares="how many shares")
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
        if price is None:
            price = stock["base"]
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
