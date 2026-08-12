import asyncio
import discord
import discord.ext.commands as commands
import bot.db as db
from bot.config import NIGHTLY_BOT_ID, OWNER_IDS


def is_nightly(bot) -> bool:
    """the nightly/dev bot bypasses economy balance checks."""
    return bool(bot.user and bot.user.id == NIGHTLY_BOT_ID)


audio_queues = {}
voice_joiners = {}
in_game = set()

def game_lock(ctx):
    if ctx.author.id in in_game:
        raise commands.CommandError("you already have a game running")
    in_game.add(ctx.author.id)

def game_unlock(ctx):
    in_game.discard(ctx.author.id)

# Global DM fallback monkeypatch
_original_send = commands.Context.send
_original_reply = commands.Context.reply


async def safe_send(self, *args, **kwargs):
    try:
        return await _original_send(self, *args, **kwargs)
    except discord.Forbidden:
        try:
            dm_channel = self.author.dm_channel or await self.author.create_dm()
            kwargs.pop("reference", None)
            kwargs.pop("mention_author", None)
            return await dm_channel.send(*args, **kwargs)
        except Exception as e:
            print(f"failed to send DM fallback for {self.author.id}: {e}")
            return None


async def safe_reply(self, *args, **kwargs):
    try:
        return await _original_reply(self, *args, **kwargs)
    except discord.Forbidden:
        try:
            dm_channel = self.author.dm_channel or await self.author.create_dm()
            kwargs.pop("reference", None)
            kwargs.pop("mention_author", None)
            return await dm_channel.send(*args, **kwargs)
        except Exception as e:
            print(f"failed to send DM fallback for {self.author.id}: {e}")
            return None


commands.Context.send = safe_send
commands.Context.reply = safe_reply


async def _is_configured_admin(user_id: int) -> bool:
    """owner list + the admin_ids config row. no guild perms involved."""
    if user_id in OWNER_IDS:
        return True

    admin_ids_str = await asyncio.to_thread(db.get_config, "admin_ids")
    if admin_ids_str:
        try:
            admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
            if user_id in admin_ids:
                return True
        except Exception as e:
            print(f"error parsing admin_ids config: {e}")

    return False


def is_dev():
    async def predicate(ctx: commands.Context):
        AUTHORIZED_USERS = [
            1048423590623727686,
            1278489064210956378,
            1421940246492352612,
            1246945967102623755,
            1488967988207157308,
            274556515061465088,
            983544114635235430,
        ]
        return ctx.author.id in AUTHORIZED_USERS

    return commands.check(predicate)


def is_admin():
    async def predicate(ctx: commands.Context):
        if await _is_configured_admin(ctx.author.id):
            return True

        # guild_permissions only exists on Member — commands work in dms too
        if ctx.guild is not None and ctx.author.guild_permissions.administrator:
            return True

        return False

    return commands.check(predicate)


def is_bot_dev():
    async def predicate(ctx: commands.Context):
        return await _is_configured_admin(ctx.author.id)

    return commands.check(predicate)


def _s(num):
    """abbreviate a number: 1234 -> 1.2k, 5678900 -> 5.7m"""
    sign = "-" if num < 0 else ""
    n = abs(num)
    if n >= 1_000_000_000_000_000_000:
        digits = str(n)
        s = f"{digits[0]}.{digits[1:4]}e+{len(digits)-1}"
    elif n >= 1_000_000_000_000_000:
        s = f"{n // 1_000_000_000_000_000}q"
    elif n >= 1_000_000_000_000:
        s = f"{n // 1_000_000_000_000}t"
    elif n >= 1_000_000_000:
        s = f"{n / 1_000_000_000:.1f}b"
    elif n >= 1_000_000:
        s = f"{n / 1_000_000:.1f}m"
    elif n >= 1_000:
        s = f"{n / 1_000:.1f}k"
    else:
        s = str(n)
    if s.endswith(".0") and len(s) > 2 and s[-3].isdigit():
        s = s[:-2]
    return sign + s

async def claim_streak_bonus(ctx):
    """grant the once-daily gambling streak bonus. returns bonus amount."""
    if is_nightly(ctx.bot):
        return 0
    streak, bonus = await asyncio.to_thread(db.claim_daily_streak, ctx.author.id)
    if bonus > 0:
        await asyncio.to_thread(db.update_balance, ctx.author.id, bonus)
        await asyncio.to_thread(db.update_house, -bonus)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"🔥 daily gambling streak — day {streak}! +{bonus} {coin_emoji} streak bonus")
    return bonus


async def track_gamble(ctx, net_gain):
    """record a settled gamble's net result for daily loss insurance, and route money through the house wallet."""
    if is_nightly(ctx.bot):
        return
    if net_gain > 0:
        rake_pct = int(await asyncio.to_thread(db.get_config, "house_rake", "25") or "25")
        if rake_pct > 0:
            rake = max(1, int(net_gain * rake_pct / 100))
            await asyncio.to_thread(db.update_balance, ctx.author.id, -rake)
            net_gain -= rake
    await asyncio.to_thread(db.track_gamble_result, ctx.author.id, net_gain)
    await asyncio.to_thread(db.update_house, -net_gain)


async def apply_income_tax(ctx, user_id, amount):
    """income tax on non-gambling earnings (jobs, fish, beg, crypto cashouts).

    rate lives in config `income_tax_rate` (percent, 0 disables, default 15).
    returns the tax amount taken (0 if disabled). identical money flow to
    the gambling tax: player pays, house collects, lifetime total tracked.
    """
    if amount <= 0:
        return 0
    rate_str = await asyncio.to_thread(db.get_config, "income_tax_rate", "15")
    try:
        rate = int(rate_str)
    except (TypeError, ValueError):
        rate = 15
    if rate <= 0 or is_nightly(ctx.bot):
        return 0
    tax = max(1, int(amount * rate / 100))
    await asyncio.to_thread(db.update_balance, user_id, -tax)
    await asyncio.to_thread(db.update_house, tax)
    collected = await asyncio.to_thread(db.get_config, "income_tax_collected", "0")
    try:
        total = int(collected)
    except (TypeError, ValueError):
        total = 0
    await asyncio.to_thread(db.set_config, "income_tax_collected", str(total + tax))
    return tax


from .blackjack import setup_blackjack
from .voice import setup_voice
from .economy import setup_economy
from .admin import setup_admin
from .utility import setup_utility
from .horserace import setup_horserace
from .catrace import setup_catrace
from .job import setup_job
from .update import setup_update
from .shop import setup_shop
from .stocks import setup_stocks
from .crash import setup_crash
from .crypto import setup_crypto
from .pet import setup_pet
from .cars import setup_car


def setup(client: commands.Bot):
    setup_blackjack(client)
    setup_voice(client)
    setup_economy(client)
    setup_horserace(client)
    setup_catrace(client)
    setup_admin(client)
    setup_utility(client)
    setup_job(client)
    setup_update(client)
    setup_shop(client)
    setup_stocks(client)
    setup_crash(client)
    setup_crypto(client)
    setup_pet(client)
    setup_car(client)
