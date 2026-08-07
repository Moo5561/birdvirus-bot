import random
import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from bot.commands import is_nightly
from bot.commands.job_rewards import JOBS, get_job_title
from bot.commands.job_games import (
    JanitorGameView,
    ChefGameView,
    DeveloperGameView,
    HackerGameView,
    MinerGameView,
    ThiefGameView,
)
from datetime import datetime, timedelta
from typing import Literal


def setup_job(client: commands.Bot):
    @client.hybrid_group(name="job", description="job system commands")
    async def job_group(ctx: commands.Context):
        pass

    @job_group.command(name="list", description="list all available jobs")
    async def job_list(ctx: commands.Context):
        embed = discord.Embed(title="Available Jobs", color=0x3498db)
        for job_id, info in JOBS.items():
            embed.add_field(
                name=f"{info['emoji']} {job_id.title()}",
                value=f"**Pay:** {info['base_pay']} / shift\n**Req Level:** {info['req_level']}\n**Cooldown:** {info['cooldown_minutes']}m\n_{info['description']}_",
                inline=False
            )
        await ctx.reply(embed=embed)

    @job_group.command(name="info", description="check your current job status")
    async def job_info(ctx: commands.Context):
        job_data = await asyncio.to_thread(db.get_user_job, ctx.author.id)
        if not job_data:
            await ctx.reply("you are currently unemployed. use `/job apply <job_name>` to get a job.")
            return
            
        job_name = job_data["job_name"]
        if job_name not in JOBS:
            await asyncio.to_thread(db.remove_user_job, ctx.author.id)
            await ctx.reply("your job no longer exists. you have been fired.")
            return
            
        info = JOBS[job_name]
        level = job_data["job_level"]
        xp = job_data["job_xp"]
        shifts = job_data["shifts_completed"]
        
        title = get_job_title(job_name, level)
        
        xp_needed = level * 100
        progress_bar_length = 10
        filled = int((xp / xp_needed) * progress_bar_length)
        bar = "█" * filled + "░" * (progress_bar_length - filled)
        
        embed = discord.Embed(title=f"Employment Info - {ctx.author.display_name}", color=0x2ecc71)
        embed.add_field(name="Job", value=f"{info['emoji']} {job_name.title()} ({title})", inline=True)
        embed.add_field(name="Level", value=f"{level} / {info['max_level']}", inline=True)
        embed.add_field(name="Shifts Completed", value=str(shifts), inline=True)
        embed.add_field(name="Experience", value=f"`{bar}` ({xp}/{xp_needed} XP)", inline=False)
        embed.add_field(name="Base Pay", value=f"{int(info['base_pay'] * (1 + (level * 0.1)))} coins / shift", inline=False)
        
        await ctx.reply(embed=embed)

    @job_group.command(name="apply", description="apply for a job")
    @app_commands.describe(job_name="the name of the job you want")
    async def job_apply(ctx: commands.Context, job_name: Literal["janitor", "chef", "developer", "hacker", "miner", "thief"]):
        job_name = job_name.lower()
        if job_name not in JOBS:
            await ctx.reply(f"invalid job. use `/job list` to see available jobs.")
            return
            
        req_level = JOBS[job_name]["req_level"]
        fee = req_level * 500
        
        if fee > 0:
            bal = await asyncio.to_thread(db.get_balance, ctx.author.id)
            if bal < fee and not is_nightly(ctx.bot):
                await ctx.reply(f"you need {fee} coins to get the license for this job. you only have {bal}.")
                return
            await asyncio.to_thread(db.update_balance, ctx.author.id, -fee)
            await ctx.reply(f"you paid {fee} coins for the {job_name} license.")
            
        await asyncio.to_thread(db.set_user_job, ctx.author.id, job_name)
        await ctx.reply(f"congratulations! you are now a {JOBS[job_name]['emoji']} {job_name.title()}. use `/job work` to start your shift.")

    @job_group.command(name="quit", description="quit your current job")
    async def job_quit(ctx: commands.Context):
        job_data = await asyncio.to_thread(db.get_user_job, ctx.author.id)
        if not job_data:
            await ctx.reply("you don't even have a job to quit.")
            return
            
        await asyncio.to_thread(db.remove_user_job, ctx.author.id)
        await ctx.reply("you slammed your badge on the desk and walked out. you are now unemployed.")

    @job_group.command(name="work", description="work your shift to earn money")
    async def job_work(ctx: commands.Context):
        job_data = await asyncio.to_thread(db.get_user_job, ctx.author.id)
        if not job_data:
            await ctx.reply("you don't have a job! use `/job apply` first.")
            return
            
        job_name = job_data["job_name"]
        if job_name not in JOBS:
            await ctx.reply("your job is invalid. please apply for a new one.")
            return
            
        info = JOBS[job_name]
        
        # Check cooldown
        if job_data["last_work_time"]:
            last_work = datetime.fromisoformat(job_data["last_work_time"])
            now = datetime.utcnow()
            diff = now - last_work
            cooldown_dt = timedelta(minutes=info["cooldown_minutes"])
            
            if diff < cooldown_dt:
                remaining = cooldown_dt - diff
                mins, secs = divmod(remaining.total_seconds(), 60)
                await ctx.reply(f"you are on break! your next shift starts in {int(mins)}m {int(secs)}s. (try `/job beg` if you're desperate)", ephemeral=True)
                return
                
        title = get_job_title(job_name, job_data["job_level"])
        embed = discord.Embed(title=f"{info['emoji']} {job_name.title()} Shift Started ({title})", color=0x3498db)
        
        if job_name == "janitor":
            embed.description = "oh no! someone made a mess. click the poop emoji to clean it up!"
            view = JanitorGameView(ctx, job_data)
        elif job_name == "chef":
            view = ChefGameView(ctx, job_data)
            embed.description = f"**Recipe:** {' -> '.join(view.target_recipe)}\n\n**Progress:** "
        elif job_name == "developer":
            view = DeveloperGameView(ctx, job_data)
            embed.description = "find the snippet of code that actually compiles without errors:\n\n" + view.snippet_display
        elif job_name == "hacker":
            embed.description = "**TARGET MAINFRAME ENCRYPTED**\nCrack the 3-digit PIN.\n\n**Attempts left:** 3"
            view = HackerGameView(ctx, job_data)
        elif job_name == "miner":
            embed.description = "**Welcome to the mines!**\nFind the diamond 💎, avoid the lava 🔥.\n\n**Picks left:** 3"
            view = MinerGameView(ctx, job_data)
        elif job_name == "thief":
            stage = view.stages[0] if (view := ThiefGameView(ctx, job_data)) else None
            embed.description = f"**Current Stash:** 0 coins\n\nNext target: **{stage['name']}**\nRisk of getting caught: {int((1-stage['chance'])*100)}%\nPotential gain: {stage['reward']} coins\n\ndo you push your luck?"
        else:
            await ctx.reply("job minigame not implemented yet.")
            return

        # stamp the cooldown now, not when the shift resolves — otherwise you can
        # open as many shifts at once as you can click and get paid for all of them
        await asyncio.to_thread(db.update_job_time, ctx.author.id, datetime.utcnow().isoformat())

        view.message = await ctx.reply(embed=embed, view=view)

    @job_group.command(name="beg", description="beg your boss to let you off break early")
    @commands.cooldown(1, 120, commands.BucketType.user)
    async def job_beg(ctx: commands.Context):
        job_data = await asyncio.to_thread(db.get_user_job, ctx.author.id)
        if not job_data:
            await ctx.reply("you don't even have a job to beg for. go apply first.")
            return
            
        job_name = job_data["job_name"]
        if job_name not in JOBS:
            await ctx.reply("your job is invalid. please apply for a new one.")
            return

        info = JOBS[job_name]

        if not job_data["last_work_time"]:
            await ctx.reply("you aren't even on break... get back to work! `/job work`")
            return
            
        last_work = datetime.fromisoformat(job_data["last_work_time"])
        now = datetime.utcnow()
        diff = now - last_work
        cooldown_dt = timedelta(minutes=info["cooldown_minutes"])
        
        if diff >= cooldown_dt:
            await ctx.reply("you are already off break! run `/job work` to start your shift.")
            return
            
        success = random.random() < 0.35  # 35% chance to get off break
        
        if success:
            await asyncio.to_thread(db.update_job_time, ctx.author.id, None)
            await ctx.reply("your boss sighed and told you to get back to work. you are off break! run `/job work`.")
        else:
            penalty = timedelta(minutes=random.randint(1, 3))
            new_last_work = last_work + penalty
            await asyncio.to_thread(db.update_job_time, ctx.author.id, new_last_work.isoformat())
            await ctx.reply(f"your boss got mad and told you to get out of his office. your break was extended by {penalty.total_seconds() // 60:.0f} minutes!")

    @job_beg.error
    async def job_beg_error(ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"your boss is ignoring you right now. try again in {error.retry_after:.1f}s", ephemeral=True)
        else:
            await ctx.reply(f"error: {error}")