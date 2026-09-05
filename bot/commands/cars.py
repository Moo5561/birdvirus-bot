import asyncio
import random
import time
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from bot.commands import _s, credit_income, is_nightly


DRIVE_COOLDOWN = 1800

CARS = [
    {
        "key": "beater",
        "name": "rust bucket",
        "emoji": "🚗",
        "tier": 1,
        "price": 2500,
        "miles": (3, 9),
        "payout": (45, 110),
        "wear": (7, 15),
    },
    {
        "key": "compact",
        "name": "tiny terror",
        "emoji": "🚙",
        "tier": 2,
        "price": 12000,
        "miles": (6, 14),
        "payout": (120, 260),
        "wear": (5, 12),
    },
    {
        "key": "muscle",
        "name": "angry brick",
        "emoji": "🏎️",
        "tier": 3,
        "price": 55000,
        "miles": (10, 22),
        "payout": (330, 760),
        "wear": (4, 10),
    },
    {
        "key": "supercar",
        "name": "tax evader",
        "emoji": "🏁",
        "tier": 4,
        "price": 220000,
        "miles": (18, 35),
        "payout": (950, 2100),
        "wear": (3, 8),
    },
]

CAR_BY_KEY = {car["key"]: car for car in CARS}
CAR_ALIASES = {car["key"]: car["key"] for car in CARS}
CAR_ALIASES.update({car["name"]: car["key"] for car in CARS})


def _car_key(value: str | None):
    if value is None:
        return None
    return CAR_ALIASES.get(value.strip().lower())


def _wear_bar(wear: int):
    filled = "█" * (wear // 10)
    empty = "░" * (10 - wear // 10)
    return filled + empty


def _repair_cost(car):
    return car["wear"] * car["tier"] * 35


async def _report(ctx, text: str, title="cars", color=0x2b2d31):
    embed = discord.Embed(title=title, description=text, color=color)
    await ctx.reply(embed=embed)


def setup_cars(client: commands.Bot):
    @client.hybrid_command(name="dealership", description="browse cars you can buy")
    async def dealership(ctx: commands.Context):
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        lines = []
        for car in CARS:
            lines.append(
                f"{car['emoji']} **{car['name']}** (`{car['key']}`) - {_s(car['price'])} {coin_emoji}\n"
                f"tier {car['tier']} | drive payout {_s(car['payout'][0])}-{_s(car['payout'][1])} {coin_emoji}"
            )
        await _report(
            ctx,
            "\n\n".join(lines) + "\n\nuse `/buycar <car>` to buy one.",
            title="used car lot",
        )

    @client.hybrid_command(name="buycar", description="buy a car from the dealership")
    @app_commands.describe(car="car key or name from /dealership")
    async def buycar(ctx: commands.Context, car: str):
        key = _car_key(car)
        if not key:
            await _report(ctx, "that car isn't on the lot. check `/dealership`.")
            return

        car_data = CAR_BY_KEY[key]
        if await asyncio.to_thread(db.get_car, ctx.author.id, key):
            await _report(ctx, f"you already own the **{car_data['name']}**.")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        cost = 0 if is_nightly(ctx.bot) else car_data["price"]
        bal = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if bal < cost and not is_nightly(ctx.bot):
            await _report(ctx, f"the **{car_data['name']}** costs {_s(cost)} {coin_emoji}. you have {_s(bal)}.")
            return

        inserted = await asyncio.to_thread(db.add_car, ctx.author.id, key, car_data["name"], car_data["tier"])
        if not inserted:
            await _report(ctx, "garage paperwork got weird. you probably already own that.")
            return
        if cost:
            await asyncio.to_thread(db.update_balance, ctx.author.id, -cost)

        await _report(
            ctx,
            f"you bought {car_data['emoji']} **{car_data['name']}** for {_s(cost)} {coin_emoji}. use `/drive {key}` to take it out.",
            title="keys acquired",
            color=0x2ecc71,
        )

    @client.hybrid_command(name="garage", description="check your cars")
    @app_commands.describe(user="whose garage to check")
    async def garage(ctx: commands.Context, user: discord.User | None = None):
        target = user or ctx.author
        cars = await asyncio.to_thread(db.get_user_cars, target.id)
        if not cars:
            await _report(ctx, f"{target.display_name} has no cars. `/dealership` has questionable options.")
            return

        lines = []
        for owned in cars:
            car_data = CAR_BY_KEY.get(owned["car_key"], {"emoji": "🚗"})
            lines.append(
                f"{car_data['emoji']} **{owned['name']}** (`{owned['car_key']}`)\n"
                f"tier {owned['tier']} | mileage {_s(owned['mileage'])} mi | earned {_s(owned['earned_total'])}\n"
                f"wear {_wear_bar(owned['wear'])} **{owned['wear']}%**"
            )
        await _report(ctx, "\n\n".join(lines), title=f"{target.display_name}'s garage")

    @client.hybrid_command(name="drive", description="drive one of your cars for coins")
    @commands.cooldown(1, 20, commands.BucketType.user)
    @app_commands.describe(car="car key or name from your garage")
    async def drive(ctx: commands.Context, car: str = None):
        owned_cars = await asyncio.to_thread(db.get_user_cars, ctx.author.id)
        if not owned_cars:
            await _report(ctx, "you don't own a car. go suffer at `/dealership`.")
            return

        key = _car_key(car) if car else owned_cars[0]["car_key"]
        if not key:
            await _report(ctx, "can't find that car. check `/garage`.")
            return

        owned = await asyncio.to_thread(db.get_car, ctx.author.id, key)
        if not owned:
            await _report(ctx, "you don't own that car. check `/garage`.")
            return

        car_data = CAR_BY_KEY[key]
        now = time.time()
        if owned["last_drive"]:
            elapsed = now - float(owned["last_drive"])
            if elapsed < DRIVE_COOLDOWN:
                mins = int((DRIVE_COOLDOWN - elapsed) // 60) + 1
                await _report(ctx, f"that engine is still hot. try again in {mins} min.")
                return

        if owned["wear"] >= 100:
            await _report(ctx, f"the **{owned['name']}** is cooked. repair it with `/repaircar {key}`.")
            return

        miles = random.randint(*car_data["miles"])
        gross = random.randint(*car_data["payout"])
        wear_gain = random.randint(*car_data["wear"])
        if owned["wear"] >= 70:
            gross = int(gross * 0.75)

        new_balance, tax = await credit_income(ctx, ctx.author.id, gross)
        updated = await asyncio.to_thread(db.record_car_drive, ctx.author.id, key, miles, wear_gain, gross, str(now))
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        trip = random.choice([
            "delivered suspicious soup",
            "won a parking lot drag race",
            "drove someone to court",
            "hauled birdseed across town",
            "taxied a guy who smelled like pennies",
        ])
        await _report(
            ctx,
            f"{car_data['emoji']} {trip} in the **{owned['name']}**.\n"
            f"drove **{miles} mi** and made **{_s(gross)} {coin_emoji}**"
            + (f" (tax: {_s(tax)} {coin_emoji})" if tax else "")
            + f".\nbalance: **{_s(new_balance)}** | wear: **{updated['wear']}%**",
            title="drive complete",
            color=0x3498db,
        )

    @client.hybrid_command(name="repaircar", description="repair one of your cars")
    @app_commands.describe(car="car key or name from your garage")
    async def repaircar(ctx: commands.Context, car: str = None):
        owned_cars = await asyncio.to_thread(db.get_user_cars, ctx.author.id)
        if not owned_cars:
            await _report(ctx, "you have no car to repair.")
            return
        key = _car_key(car) if car else owned_cars[0]["car_key"]
        if not key:
            await _report(ctx, "can't find that car. check `/garage`.")
            return
        owned = await asyncio.to_thread(db.get_car, ctx.author.id, key)
        if not owned:
            await _report(ctx, "you don't own that car.")
            return
        if owned["wear"] <= 0:
            await _report(ctx, f"the **{owned['name']}** is already fine. suspicious, but fine.")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        cost = 0 if is_nightly(ctx.bot) else _repair_cost(owned)
        bal = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if bal < cost and not is_nightly(ctx.bot):
            await _report(ctx, f"repairs cost {_s(cost)} {coin_emoji}. you have {_s(bal)}.")
            return
        if cost:
            await asyncio.to_thread(db.update_balance, ctx.author.id, -cost)
        await asyncio.to_thread(db.repair_car, ctx.author.id, key)
        await _report(ctx, f"repaired **{owned['name']}** for {_s(cost)} {coin_emoji}.", title="car repaired", color=0x2ecc71)

    @client.hybrid_command(name="cartop", description="car earnings leaderboard")
    async def cartop(ctx: commands.Context):
        rows = await asyncio.to_thread(db.get_all_car_earnings)
        if not rows:
            await _report(ctx, "nobody has driven enough to flex yet.")
            return
        lines = []
        for i, row in enumerate(rows, 1):
            user = ctx.bot.get_user(row["user_id"])
            name = user.display_name if user else f"<@{row['user_id']}>"
            lines.append(f"**{i}.** {name} - **{_s(row['earned_total'])}** earned, {_s(row['mileage'])} mi")
        await _report(ctx, "\n".join(lines), title="car leaderboard")


def setup_car(client: commands.Bot):
    setup_cars(client)
