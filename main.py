import discord
import aiohttp
import datetime
import argparse
import logging
import base64
import os
import discord.ext.commands as commands
import bot.events
import bot.commands
from bot.config import token

bot_id = int(base64.b64decode(token.split(".")[0] + "==").decode())
if bot_id == 1522117141090799697:
    os.environ["BOT_DB_PATH"] = "birdvirus_nightly.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log", mode="w"), logging.StreamHandler()],
)

parser = argparse.ArgumentParser(description="run the birdvirus bot")
parser.add_argument("--host", required=True, help="who is hosting the bot currently")
args = parser.parse_args()


def get_prefix(bot, message):
    if bot.user and bot.user.id == 1522117141090799697:
        return "ht!"
    return "%"


intents = discord.Intents.default()
intents.message_content = True
client = commands.AutoShardedBot(
    command_prefix=get_prefix,
    intents=intents,
    activity=discord.CustomActivity(name=f"loading..."),
)
client._host = args.host

client.tree.default_allowed_contexts = discord.app_commands.AppCommandContext(
    guild=True, dm_channel=True, private_channel=True
)
client.tree.default_allowed_installs = discord.app_commands.AppInstallationType(
    guild=True, user=True
)

bot.events.setup(client)
bot.commands.setup(client)

client.run(token)
