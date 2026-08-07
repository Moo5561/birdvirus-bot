import asyncio
from datetime import datetime, time as dt_time
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from bot.commands import is_admin, is_nightly

SHOP_OPEN = dt_time(6, 0)
SHOP_CLOSE = dt_time(0, 0)
ILLEGAL_START = dt_time(18, 0)
ILLEGAL_END = dt_time(20, 0)

ACTIVE_CHEATS = {}
SHOP_OVERRIDE = None  # None = auto, "open" = force open, "closed" = force closed


def take_cheat(user_id, cheat_type):
    """consume the user's active cheat only if it matches cheat_type.

    plain ACTIVE_CHEATS.pop() would burn an unrelated item — activating a lucky
    charm and then fishing used to silently eat the charm.
    """
    cheat = ACTIVE_CHEATS.get(user_id)
    if cheat and cheat.get("type") == cheat_type:
        return ACTIVE_CHEATS.pop(user_id)
    return None

NORMAL_ITEMS = [
    {"name": "lucky charm", "emoji": "🍀", "price": 5000, "desc": "your horse/cat gets +3 each tick in the next race"},
    {"name": "xp boost", "emoji": "📚", "price": 3000, "desc": "double XP on your next job shift"},
    {"name": "fishing net", "emoji": "🕸️", "price": 2000, "desc": "next fish you catch is worth 3x"},
]

ILLEGAL_ITEMS = [
    {"name": "rigged dice", "emoji": "🎲", "price": 15000, "desc": "next insaneroll lands a natural 20"},
    {"name": "slot cheat", "emoji": "🎰", "price": 25000, "desc": "next slots spin gives 3 matching symbols"},
]

ALL_ITEMS = {item["name"]: item for item in NORMAL_ITEMS + ILLEGAL_ITEMS}

# item name -> (cheat stored in ACTIVE_CHEATS, message shown on activation)
ITEM_EFFECTS = {
    "lucky charm": (
        {"type": "race_boost", "value": 3},
        "🍀 lucky charm activated! your next race pick gets +3 speed each tick!",
    ),
    "xp boost": (
        {"type": "xp_boost", "value": 2},
        "📚 xp boost activated! your next job shift gives double XP!",
    ),
    "fishing net": (
        {"type": "fish_boost", "value": 3},
        "🕸️ fishing net activated! your next catch is worth 3x!",
    ),
    "rigged dice": (
        {"type": "rigged_dice"},
        "🎲 rigged dice activated! next insaneroll is a guaranteed natural 20!",
    ),
    "slot cheat": (
        {"type": "slot_cheat"},
        "🎰 slot cheat activated! next slots spin lands 3 matching symbols!",
    ),
}

ACTIVE_CHEAT_NAMES = {cheat["type"]: name for name, (cheat, _) in ITEM_EFFECTS.items()}


def is_shop_open():
    if SHOP_OVERRIDE == "open":
        return True
    if SHOP_OVERRIDE == "closed":
        return False
    now = datetime.utcnow().time()
    if SHOP_OPEN <= SHOP_CLOSE:
        return SHOP_OPEN <= now <= SHOP_CLOSE
    return now >= SHOP_OPEN or now <= SHOP_CLOSE


async def get_illegal_hours():
    """back alley hours, honouring whatever /setillegal wrote to config."""
    start, end = ILLEGAL_START.hour, ILLEGAL_END.hour
    for key, fallback in (("illegal_start", start), ("illegal_end", end)):
        raw = await asyncio.to_thread(db.get_config, key)
        try:
            hour = int(raw)
        except (TypeError, ValueError):
            hour = fallback
        if not 0 <= hour <= 23:
            hour = fallback
        if key == "illegal_start":
            start = hour
        else:
            end = hour
    return start, end


async def is_illegal_open():
    start, end = await get_illegal_hours()
    hour = datetime.utcnow().hour
    if start <= end:
        return start <= hour <= end
    # window wraps past midnight
    return hour >= start or hour <= end


async def get_balance_safe(ctx, user_id):
    if is_nightly(ctx.bot):
        return 999999999999999999999999999
    return (await asyncio.to_thread(db.get_balance, user_id))


def setup_shop(client: commands.Bot):
    @client.hybrid_command(name="shop", description="browse the shop for equipment and other goods")
    async def shop(ctx: commands.Context):
        if not is_shop_open():
            await ctx.reply("shop is closed. open from 6am to midnight (utc)")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        embed = discord.Embed(
            title="🏪 Shop",
            description=f"open 06:00–00:00 utc | pay with {coin_emoji}\nuse `%buy <item>` to purchase",
            color=0x2f3136,
        )

        items_text = ""
        for i, item in enumerate(NORMAL_ITEMS):
            items_text += f"{i+1}. {item['emoji']} **{item['name'].title()}** — {item['price']} {coin_emoji}\n*{item['desc']}*\n\n"
        embed.add_field(name="Equipment", value=items_text or "none", inline=False)

        if await is_illegal_open():
            shady_text = ""
            for i, item in enumerate(ILLEGAL_ITEMS):
                shady_text += f"{i+1}. {item['emoji']} **{item['name'].title()}** — {item['price']} {coin_emoji}\n*{item['desc']}*\n\n"
            embed.add_field(
                name="⬛ BACK ALLEY (illegal gambling cheats)",
                value=f"> *a hooded figure lurks in the shadows...*\n{shady_text}only available for a limited time!",
                inline=False,
            )
            embed.set_footer(text="⚠️ using illegal items in gambling is cheating! ...but we don't judge")
        else:
            start, end = await get_illegal_hours()
            embed.set_footer(text=f"the back alley is empty... come back between {start:02d}:00-{end:02d}:00 utc")

        await ctx.reply(embed=embed)

    @client.hybrid_command(name="buy", description="buy an item from the shop")
    @app_commands.describe(item="the item to buy")
    async def buy(ctx: commands.Context, item: str):
        if not is_shop_open():
            await ctx.reply("shop is closed. come back between 6am and midnight (utc)")
            return

        item_key = item.strip().lower()
        if item_key not in ALL_ITEMS:
            await ctx.reply(f"no item called \"{item_key}\" in the shop. check `%shop`")
            return

        item_data = ALL_ITEMS[item_key]

        if item_data in ILLEGAL_ITEMS and not await is_illegal_open():
            start, end = await get_illegal_hours()
            await ctx.reply(f"that item is only available from the back alley between {start:02d}:00-{end:02d}:00 utc")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")

        bal = await get_balance_safe(ctx, ctx.author.id)
        if bal < item_data["price"] and not is_nightly(ctx.bot):
            await ctx.reply(f"you need {item_data['price']} {coin_emoji} for that. you have {bal} {coin_emoji}")
            return

        await asyncio.to_thread(db.update_balance, ctx.author.id, -item_data["price"])
        await asyncio.to_thread(db.add_item, ctx.author.id, item_key)

        await ctx.reply(f"you bought **{item_data['emoji']} {item_key.title()}** for {item_data['price']} {coin_emoji}. use `%use {item_key}` to activate it!")

    @buy.error
    async def buy_error(ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply("what item? `%buy <item>`")
        else:
            await ctx.reply(f"error: {error}")

    @client.hybrid_command(name="inv", aliases=["inventory"], description="check your items")
    async def inv(ctx: commands.Context):
        items = await asyncio.to_thread(db.get_items, ctx.author.id)
        if not items:
            await ctx.reply("your inventory is empty. check `%shop` to buy stuff")
            return

        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'s Inventory",
            color=0x2f3136,
        )
        lines = []
        for item_name, qty in sorted(items.items()):
            data = ALL_ITEMS.get(item_name)
            emoji = data["emoji"] if data else "❓"
            lines.append(f"{emoji} **{item_name.title()}** x{qty}")
        embed.description = "\n".join(lines)
        embed.set_footer(text="use %use <item> to activate")
        await ctx.reply(embed=embed)

    @client.hybrid_command(name="use", description="use an item from your inventory")
    @app_commands.describe(item="the item to use")
    async def use(ctx: commands.Context, item: str):
        item_key = item.strip().lower()

        effect = ITEM_EFFECTS.get(item_key)
        if not effect:
            await ctx.reply(f"can't use {item_key} here")
            return

        has = await asyncio.to_thread(db.has_item, ctx.author.id, item_key)
        if not has:
            await ctx.reply(f"you don't have {item_key}. check `%inv`")
            return

        user_id = ctx.author.id
        cheat, response = effect
        active = ACTIVE_CHEATS.get(user_id)
        if active and active["type"] != cheat["type"]:
            await ctx.reply(f"you already have a {ACTIVE_CHEAT_NAMES[active['type']]} active. use it first")
            return

        # only burn the item once we know it will actually do something
        await asyncio.to_thread(db.remove_item, ctx.author.id, item_key)
        ACTIVE_CHEATS[user_id] = dict(cheat)
        await ctx.reply(response)

    @use.error
    async def use_error(ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply("what item? `%use <item>`")
        else:
            await ctx.reply(f"error: {error}")

    # admin command to manually give/remove items
    @client.hybrid_command(name="giveitem", description="give an item to a user (admin only)")
    @is_admin()
    @app_commands.describe(user="the user", item="item name", quantity="how many")
    async def giveitem(ctx: commands.Context, user: discord.Member, item: str, quantity: int = 1):
        await asyncio.to_thread(db.add_item, user.id, item.strip().lower(), quantity)
        await ctx.reply(f"gave {user.mention} x{quantity} {item}")

    @client.hybrid_command(name="setillegal", description="set the illegal guy's hours (admin only, utc)")
    @is_admin()
    @app_commands.describe(start_hour="start hour (0-23 utc)", end_hour="end hour (0-23 utc)")
    async def setillegal(ctx: commands.Context, start_hour: int, end_hour: int):
        if not (0 <= start_hour <= 23) or not (0 <= end_hour <= 23):
            await ctx.reply("hours must be between 0 and 23")
            return
        await asyncio.to_thread(db.set_config, "illegal_start", str(start_hour))
        await asyncio.to_thread(db.set_config, "illegal_end", str(end_hour))
        await ctx.reply(f"illegal guy hours set to {start_hour}:00–{end_hour}:00 utc")

    @client.hybrid_command(name="setshop", description="force open/close the shop or revert to time-based (admin only)")
    @is_admin()
    @app_commands.describe(state="open, close, or auto")
    async def setshop(ctx: commands.Context, state: str):
        global SHOP_OVERRIDE
        s = state.strip().lower()
        if s not in ("open", "close", "auto", "closed"):
            await ctx.reply("use `%setshop open`, `%setshop close`, or `%setshop auto`")
            return
        if s == "auto":
            SHOP_OVERRIDE = None
            await ctx.reply("shop hours reverted to time-based schedule (06:00–00:00 utc)")
        elif s == "close":
            SHOP_OVERRIDE = "closed"
            await ctx.reply("shop forcibly closed")
        else:
            SHOP_OVERRIDE = "open"
            await ctx.reply("shop forcibly opened")

    @client.hybrid_command(name="removeitem", description="remove items from a user (admin only)")
    @is_admin()
    @app_commands.describe(user="the user", item="item name", quantity="how many to remove")
    async def removeitem(ctx: commands.Context, user: discord.Member, item: str, quantity: int = 1):
        for _ in range(quantity):
            await asyncio.to_thread(db.remove_item, user.id, item.strip().lower())
        await ctx.reply(f"removed x{quantity} {item} from {user.mention}")
