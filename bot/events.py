import discord
import random
import asyncio
import os
import sys
import subprocess
import discord.ext.commands as commands
import bot.db as db
import bot.bans as bans
from bot.config import NIGHTLY_BOT_ID

SNAPSHOT_FILE = "update_snapshot.txt"


def _audit_droid(client):
    """make sure /vc droid is alive in all the places it can get deleted from.
    1) the audio file on disk
    2) the command registrations (hybrid + prefix)
    3) the stocks ticker (droid shares the sound)
    if anything is missing, say so loudly."""
    import bot.commands.stocks as stocks_mod
    import bot.commands.voice as voice_mod

    ok = True

    audio_sources = ["mp3/droid_sound.mp3", "mp3/droid.mp3", "mp3/bird.mp3"]
    src = next((s for s in audio_sources if os.path.exists(s)), None)
    if src is None:
        print("!!! /vc droid: no droid audio file found on disk", flush=True)
        ok = False
    else:
        print(f"/vc droid: audio source -> {src}", flush=True)

    command_names = {c.name for c in client.commands}
    if "droid" not in command_names:
        print("!!! /vc droid: droid command is not registered", flush=True)
        ok = False

    stock_tickers = [s["ticker"] for s in stocks_mod.STOCKS]
    if "DROID" not in stock_tickers:
        print("!!! droid: DROID ticker missing from stocks", flush=True)
        ok = False

    if not ok:
        print(
            "!!! AUDIT: /vc droid is broken somewhere. re-add the file, the command, and the ticker.",
            flush=True,
        )


class UserBanned(commands.CheckFailure):
    pass


def setup(client: commands.Bot):
    @client.event
    async def on_ready():
        if client.shard_id is not None and client.shard_id != 0:
            return

        if not hasattr(client, "start_time"):
            client.start_time = discord.utils.utcnow()

        if os.path.exists(SNAPSHOT_FILE):
            with open(SNAPSHOT_FILE) as f:
                snapshot_head = f.read().strip()
            print(
                f"update snapshot found ({snapshot_head[:8]}), bot may have crashed during update. reverting..."
            )
            subprocess.run(
                ["git", "reset", "--hard", snapshot_head],
                capture_output=True,
                timeout=30,
            )
            os.remove(SNAPSHOT_FILE)
            print("reverted. restarting with original args...")
            os.execv(sys.executable, [sys.executable] + sys.argv)

        prefix = "ht!" if client.user and client.user.id == NIGHTLY_BOT_ID else "%"
        await client.change_presence(
            activity=discord.CustomActivity(name=f"{prefix} • hosted by {client._host}")
        )

        print(f"the bird has awoken as {client.user}")
        try:
            synced = await client.tree.sync()
            print(f"synced {len(synced)} command(s) with discord")
        except Exception as e:
            print(f"error syncing command tree: {e}")

        _audit_droid(client)

    @client.check
    async def globally_block_banned(ctx):
        try:
            banned = await bans.read_banned_users()
        except Exception:
            banned = set()
        if ctx.author.id in banned:
            raise UserBanned()
        return True

    @client.tree.interaction_check
    async def globally_block_banned_interactions(interaction: discord.Interaction):
        try:
            banned = await bans.read_banned_users()
        except Exception:
            banned = set()
        if interaction.user.id in banned:
            return False
        return True

    @client.listen("on_message")
    async def on_message(message: discord.Message):
        if message.author == client.user:
            return
        try:
            if message.author.id in await bans.read_banned_users():
                return
        except Exception:
            # if ban read fails, fall back to DB check
            try:
                db_banned = await asyncio.to_thread(db.get_banned_users)
                if message.author.id in db_banned:
                    return
            except Exception:
                pass

        if "67" in message.content:
            if message.guild and message.guild.voice_client:
                vc = message.guild.voice_client
                if vc.is_connected():
                    try:
                        from bot.commands import audio_queues

                        guild_id = vc.guild.id
                        source = (
                            "mp3/birdvirus.mp3"
                            if random.random() < 0.50
                            else "mp3/bird.mp3"
                        )

                        if not vc.is_playing():

                            def play_next(error, vc_ref, g_id):
                                if error:
                                    print(f"player error: {error}")
                                if g_id in audio_queues and len(audio_queues[g_id]) > 0:
                                    src = audio_queues[g_id].pop(0)
                                    vc_ref.play(
                                        discord.FFmpegPCMAudio(src),
                                        after=lambda e: play_next(e, vc_ref, g_id),
                                    )

                            vc.play(
                                discord.FFmpegPCMAudio(source),
                                after=lambda e: play_next(e, vc, guild_id),
                            )
                        else:
                            if guild_id not in audio_queues:
                                audio_queues[guild_id] = []
                            audio_queues[guild_id].append(source)
                    except Exception as e:
                        print(f"error queueing bird on 67: {e}")

    @client.event
    async def on_command_error(ctx: commands.Context, error):
        if isinstance(error, UserBanned):
            return
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            await ctx.reply("you don't have permission to do that", ephemeral=True)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(
                f"slow down dude wait {error.retry_after:.1f} seconds", ephemeral=True
            )
        elif isinstance(error, commands.CommandError):
            await ctx.reply(str(error), ephemeral=True)
        else:
            print(f"command error: {error}")
            try:
                await ctx.reply(f"something broke: {error}")
            except:
                pass
