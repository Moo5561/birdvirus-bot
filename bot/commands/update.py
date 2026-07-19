import asyncio
import discord
import discord.ext.commands as commands
from discord import app_commands
import os
import sys
import subprocess
import pathlib
from bot.commands import is_bot_dev

SNAPSHOT_FILE = "update_snapshot.txt"


def get_current_head():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip() if result.returncode == 0 else None


def syntax_check():
    import py_compile

    bot_dir = pathlib.Path("bot")
    for pyfile in bot_dir.rglob("*.py"):
        try:
            py_compile.compile(pyfile, doraise=True)
        except py_compile.PyCompileError as e:
            return False, str(e)
    return True, None


async def dm_user(user: discord.User, content: str):
    try:
        dm = user.dm_channel or await user.create_dm()
        await dm.send(content)
    except:
        pass


def setup_update(client: commands.Bot):
    @client.hybrid_command(
        name="update", description="git pull and restart the bot (bot devs only)"
    )
    @is_bot_dev()
    async def update_cmd(ctx: commands.Context):
        head_before = get_current_head()
        if not head_before:
            await ctx.reply("could not determine current HEAD")
            return

        with open(SNAPSHOT_FILE, "w") as f:
            f.write(head_before + "\n")

        await ctx.reply("pulling latest code...")

        try:
            result = subprocess.run(
                ["git", "pull"], capture_output=True, text=True, timeout=30
            )
            output = result.stdout + result.stderr
        except Exception as e:
            await ctx.reply(f"git pull failed: {e}")
            await dm_user(ctx.author, f"update failed: git pull error — {e}")
            os.remove(SNAPSHOT_FILE)
            return

        if result.returncode != 0:
            await ctx.reply(
                f"git pull returned non-zero exit:\n```\n{output[:1500]}```"
            )
            await dm_user(
                ctx.author,
                f"update failed: git pull returned non-zero exit:\n```\n{output[:1500]}```",
            )
            os.remove(SNAPSHOT_FILE)
            return

        await ctx.reply(f"git pull done:\n```\n{output[:1500]}```\nchecking syntax...")

        ok, err = await asyncio.to_thread(syntax_check)
        if not ok:
            await ctx.reply(
                f"syntax error in new code, reverting...\n```\n{err[:1500]}```"
            )
            await dm_user(
                ctx.author,
                f"update failed: syntax error in pulled code, reverting to {head_before[:8]}...\n```\n{err[:1500]}```",
            )
            subprocess.run(
                ["git", "reset", "--hard", head_before], capture_output=True, timeout=30
            )
            os.remove(SNAPSHOT_FILE)
            await ctx.reply("reverted. restarting with original args...")
            try:
                await client.close()
            except:
                pass
            os.execv(sys.executable, [sys.executable] + sys.argv)

        os.remove(SNAPSHOT_FILE)
        await ctx.reply("syntax ok. restarting...")

        try:
            await client.close()
        except:
            pass

        os.execv(sys.executable, [sys.executable] + sys.argv)
