import asyncio
import discord
import discord.ext.commands as commands
import bot.db as db

audio_queues = {}
voice_joiners = {}

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
            print(f"failed to send DM fallback: {e}")

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
            print(f"failed to send DM fallback: {e}")

commands.Context.send = safe_send
commands.Context.reply = safe_reply

def is_admin():
    async def predicate(ctx: commands.Context):
        AUTHORIZED_USERS = [
            1048423590623727686, 1278489064210956378, 1421940246492352612, 
            1246945967102623755, 1488967988207157308, 274556515061465088, 
            983544114635235430, 1100425178359533691
        ]
        if ctx.author.id in AUTHORIZED_USERS:
            return True;

        admin_ids_str = await asyncio.to_thread(db.get_config, "admin_ids");
        if admin_ids_str:
            try:
                admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()];
                if ctx.author.id in admin_ids:
                    return True;
            except Exception as e:
                print(f"error parsing admin_ids config: {e}");
                
        if ctx.author.guild_permissions.administrator:
            return True;
            
        return False;
    return commands.check(predicate);

from .blackjack import setup_blackjack
from .voice import setup_voice
from .economy import setup_economy
from .admin import setup_admin
from .utility import setup_utility

def setup(client: commands.Bot):
    setup_blackjack(client)
    setup_voice(client)
    setup_economy(client)
    setup_admin(client)
    setup_utility(client)
