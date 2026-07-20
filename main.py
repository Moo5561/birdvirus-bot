import discord
import argparse
import logging
import base64
import os
import discord.ext.commands as commands
from discord.ext.commands.view import StringView
from discord.ext.commands.context import Context
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


# bots are ignored by default; allow these user ids to invoke commands
# (must also bypass get_context's self-message early return)
ALLOWED_BOT_IDS = {1518310857598308433}


class BirdBot(commands.AutoShardedBot):
    async def get_context(self, origin, /, *, cls=discord.utils.MISSING):
        if cls is discord.utils.MISSING:
            cls = Context

        if isinstance(origin, discord.Interaction):
            return await cls.from_interaction(origin)

        view = StringView(origin.content)
        ctx = cls(prefix=None, view=view, bot=self, message=origin)

        # stock discord.py returns here for self messages — skip that for allowlisted bots
        if self.user and origin.author.id == self.user.id:
            if origin.author.id not in ALLOWED_BOT_IDS:
                return ctx

        prefix = await self.get_prefix(origin)
        invoked_prefix = prefix

        if isinstance(prefix, str):
            if not view.skip_string(prefix):
                return ctx
        else:
            try:
                if origin.content.startswith(tuple(prefix)):
                    invoked_prefix = discord.utils.find(view.skip_string, prefix)
                else:
                    return ctx
            except TypeError:
                if not isinstance(prefix, list):
                    raise TypeError(
                        f"get_prefix must return either a string or a list of string, not {prefix.__class__.__name__}"
                    )
                for value in prefix:
                    if not isinstance(value, str):
                        raise TypeError(
                            "Iterable command_prefix or list returned from get_prefix must "
                            f"contain only strings, not {value.__class__.__name__}"
                        )
                raise

        if self.strip_after_prefix:
            view.skip_ws()

        invoker = view.get_word()
        ctx.invoked_with = invoker
        ctx.prefix = invoked_prefix
        ctx.command = self.all_commands.get(invoker)
        return ctx

    async def process_commands(self, message):
        if message.author.bot and message.author.id not in ALLOWED_BOT_IDS:
            return
        ctx = await self.get_context(message)
        await self.invoke(ctx)


intents = discord.Intents.default()
intents.message_content = True
client = BirdBot(
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
