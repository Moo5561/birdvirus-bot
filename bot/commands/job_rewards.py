"""job definitions, titles, random events, and reward settlement."""

import random
import asyncio
import discord
import bot.db as db
from bot.commands import is_nightly
from bot.commands.shop import take_cheat
from datetime import datetime

JOBS = {
    "janitor": {
        "description": "clean up messes around the server. easy work, low pay.",
        "base_pay": 25,
        "max_level": 10,
        "emoji": "🧹",
        "cooldown_minutes": 5,
        "req_level": 0,
        "titles": ["Apprentice Sweeper", "Mop Wielder", "Stain Master", "Head Custodian", "Sanitation CEO"]
    },
    "chef": {
        "description": "cook meals for the server. requires good memory.",
        "base_pay": 60,
        "max_level": 15,
        "emoji": "🍳",
        "cooldown_minutes": 10,
        "req_level": 3,
        "titles": ["Dishwasher", "Line Cook", "Sous Chef", "Head Chef", "Culinary Master"]
    },
    "developer": {
        "description": "write code and fix bugs. requires brain power.",
        "base_pay": 120,
        "max_level": 20,
        "emoji": "💻",
        "cooldown_minutes": 15,
        "req_level": 5,
        "titles": ["Intern", "Junior Dev", "Mid-Level Dev", "Senior Dev", "Lead Architect"]
    },
    "hacker": {
        "description": "hack into mainframes. high risk, high reward.",
        "base_pay": 250,
        "max_level": 30,
        "emoji": "🕵️",
        "cooldown_minutes": 30,
        "req_level": 10,
        "titles": ["Script Kiddie", "Netrunner", "White Hat", "Black Hat", "Cyber Overlord"]
    },
    "miner": {
        "description": "delve deep into the mines. dodge lava, find diamonds.",
        "base_pay": 150,
        "max_level": 25,
        "emoji": "⛏️",
        "cooldown_minutes": 20,
        "req_level": 7,
        "titles": ["Pebble Kicker", "Dirt Digger", "Cave Explorer", "Ore Specialist", "Dwarf King"]
    },
    "thief": {
        "description": "steal from houses. push your luck, don't get caught.",
        "base_pay": 0,  # dynamic pay based on what they steal
        "max_level": 20,
        "emoji": "🥷",
        "cooldown_minutes": 20,
        "req_level": 8,
        "titles": ["Pickpocket", "Burglar", "Cat Burglar", "Master Thief", "Phantom"]
    }
}

def get_job_title(job_name, level):
    titles = JOBS[job_name]["titles"]
    idx = min(level // 5, len(titles) - 1)
    return titles[idx]

async def trigger_random_event(ctx, job_name, level):
    if random.random() > 0.15:  # 15% chance of random event
        return 0, ""
        
    events = []
    if job_name == "janitor":
        events = [("a pipe burst while you were sweeping! hospital bill:", -50), ("you found a lost wallet in the trash!", 100)]
    elif job_name == "chef":
        events = [("you burned the soup and got fined by the health inspector.", -100), ("a famous food critic loved your meal and tipped you heavily!", 200)]
    elif job_name == "developer":
        events = [("you dropped the production database. your pay was docked.", -150), ("you fixed a critical day-0 bug and got a fat bonus!", 300)]
    elif job_name == "hacker":
        events = [("the fbi tracked your ip. you had to bribe them.", -500), ("you found a crypto wallet with some leftovers.", 600)]
    elif job_name == "miner":
        events = [("a cave-in crushed your equipment. repair cost:", -200), ("you stumbled upon a hidden gold vein!", 400)]
    elif job_name == "thief":
        events = [("the cops spotted your getaway car. pay the impound fee.", -300), ("you fenced some extra jewelry you forgot you had.", 350)]
        
    if not events:
        return 0, ""
        
    event_desc, coin_change = random.choice(events)
    # scale the event impact by level
    coin_change = int(coin_change * (1 + (level * 0.05)))
    
    return coin_change, event_desc

async def handle_job_reward(ctx, job_name, job_data, success, game_message, custom_payout=None, time_taken=None):
    coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
    level = job_data["job_level"]
    
    if not success:
        embed = game_message.embeds[0]
        embed.color = 0xe74c3c
        embed.description += "\n\n**Result:** you failed the task. boss is mad. no pay for you."
        if custom_payout and custom_payout < 0:
            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, custom_payout)
            embed.description += f"\nactually, you got fined {abs(custom_payout)} {coin_emoji}. (balance: {new_balance})"
            
        await game_message.edit(embed=embed, view=None)
        time_str = datetime.utcnow().isoformat()
        await asyncio.to_thread(db.update_job_progress, ctx.author.id, 0, time_str)
        return

    job_info = JOBS[job_name]
    
    if custom_payout is not None:
        payout = custom_payout
    else:
        payout = int(job_info["base_pay"] * (1 + (level * 0.1)))
        
    time_bonus_text = ""
    if time_taken is not None:
        adjusted_time = max(0.1, time_taken - ctx.bot.latency)
        par_times = {
            "janitor": 3.0,
            "chef": 8.0,
            "developer": 15.0,
            "hacker": 12.0,
            "miner": 10.0,
            "thief": 10.0
        }
        par_time = par_times.get(job_name, 10.0)
        
        speed_ratio = par_time / adjusted_time
        multiplier = max(0.1, min(3.0, speed_ratio))
        
        payout = int(payout * multiplier)
        
        if multiplier > 1.2:
            time_bonus_text = f"\n⏱️ **speed bonus!** took {adjusted_time:.1f}s (ping adjusted). {multiplier:.2f}x multiplier applied!"
        elif multiplier < 0.8:
            time_bonus_text = f"\n⏱️ **too slow...** took {adjusted_time:.1f}s (ping adjusted). {multiplier:.2f}x penalty applied."
        else:
            time_bonus_text = f"\n⏱️ **average speed.** took {adjusted_time:.1f}s (ping adjusted)."

    xp_gain = random.randint(15, 30)

    cheat = take_cheat(ctx.author.id, "xp_boost")
    if cheat:
        xp_gain *= cheat["value"]
    
    # Handle random event
    event_payout, event_desc = await trigger_random_event(ctx, job_name, level)
    total_payout = payout + event_payout
    
    new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, total_payout)
    time_str = datetime.utcnow().isoformat()
    level_up, new_level = await asyncio.to_thread(db.update_job_progress, ctx.author.id, xp_gain, time_str)
    
    embed = game_message.embeds[0]
    embed.color = 0x2ecc71
    
    result_text = f"\n\n**Result:** you completed your shift successfully!"
    if time_bonus_text:
        result_text += time_bonus_text
        
    if event_desc:
        result_text += f"\n⚠️ **Random Event:** {event_desc} ({event_payout} {coin_emoji})\n"
        
    result_text += f"\n+ earned a total of {total_payout} {coin_emoji} (balance: {new_balance})\n+ gained {xp_gain} xp"
    
    if level_up:
        new_title = get_job_title(job_name, new_level)
        result_text += f"\n🎉 **promotion!** you are now level {new_level}! ({new_title})"
        
    embed.description += result_text
    await game_message.edit(embed=embed, view=None)
