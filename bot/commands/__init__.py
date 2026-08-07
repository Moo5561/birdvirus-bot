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
    """abbreviate a number: 1234 -> 1.2k, 5678900 -> 5.7m, huge -> 3.9e+81"""
    if num >= 1_000_000_000_000_000:
        return f"{num:.15e}"
    if num >= 1_000_000_000:
        s = f"{num / 1_000_000_000:.1f}b"
    elif num >= 1_000_000:
        s = f"{num / 1_000_000:.1f}m"
    elif num >= 1_000:
        s = f"{num / 1_000:.1f}k"
    else:
        s = str(num)
    if s.endswith(".0") and s[-3].isdigit():
        s = s[:-2]
    return s


async def claim_streak_bonus(ctx):
    """grant the once-daily gambling streak bonus. returns bonus amount."""
    if is_nightly(ctx.bot):
        return 0
    streak, bonus = await asyncio.to_thread(db.claim_daily_streak, ctx.author.id)
    if bonus > 0:
        await asyncio.to_thread(db.update_balance, ctx.author.id, bonus)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"🔥 daily gambling streak — day {streak}! +{bonus} {coin_emoji} streak bonus")
    return bonus


async def track_gamble(ctx, net_gain):
    """record a settled gamble's net result for daily loss insurance."""
    if is_nightly(ctx.bot):
        return
    await asyncio.to_thread(db.track_gamble_result, ctx.author.id, net_gain)


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
