"""shared money helpers.

these live here rather than in economy.py so that view modules and admin.py can
use them without importing economy.py, which imports the views back.
"""

import asyncio
import discord.ext.commands as commands
import bot.db as db
from bot.commands import is_nightly


def _payout(bet, mult):
    """exact integer multiplication, no float precision loss."""
    if type(mult) is int:
        return bet * mult
    n, d = mult.as_integer_ratio()
    return bet * n // d


def _to_bet(val):
    """convert string bet to int, supports arbitrarily large numbers."""
    try:
        v = int(val)
    except (ValueError, TypeError):
        raise commands.BadArgument("bet must be a valid integer")
    if v <= 0:
        raise commands.BadArgument("bet must be greater than zero")
    return v


async def get_balance_checked(ctx, user_id):
    if is_nightly(ctx.bot):
        return 999999999999999999999999999, 999999999999999999999999999, 0
    bal, bank, debt = await asyncio.to_thread(db.get_balances, user_id)
    return bal, bank, debt


async def apply_tax(ctx, user_id, net_gain):
    if net_gain <= 0:
        return 0
    tax_rate_str = await asyncio.to_thread(db.get_config, "tax_rate", "0")
    tax_rate = int(tax_rate_str)
    if tax_rate <= 0:
        return 0
    if is_nightly(ctx.bot):
        return 0
    tax_amount = max(1, int(net_gain * tax_rate / 100))
    await asyncio.to_thread(db.update_balance, user_id, -tax_amount)
    await asyncio.to_thread(db.update_house, tax_amount)
    collected = await asyncio.to_thread(db.get_config, "tax_collected", "0")
    await asyncio.to_thread(db.set_config, "tax_collected", str(int(collected) + tax_amount))
    return tax_amount


def update_with_tax(ctx, user_id, net_gain):
    async def wrapper():
        new_bal = await asyncio.to_thread(db.update_balance, user_id, net_gain)
        tax = 0
        if net_gain > 0:
            tax = await apply_tax(ctx, user_id, net_gain)
        return new_bal, tax
    return wrapper()
