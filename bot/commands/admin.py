import asyncio
import datetime
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
import os
from bot.commands import is_admin, is_bot_dev

async def check_if_dev(user_id):
    AUTHORIZED_USERS = [
        1048423590623727686, 1278489064210956378, 1421940246492352612, 
        1246945967102623755, 1488967988207157308, 274556515061465088, 
        983544114635235430, 1100425178359533691
    ]
    if user_id in AUTHORIZED_USERS:
        return True
        
    admin_ids_str = await asyncio.to_thread(db.get_config, "admin_ids")
    if admin_ids_str:
        try:
            admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
            if user_id in admin_ids:
                return True
        except Exception:
            pass
            
    return False

def setup_admin(client: commands.Bot):
    # Ban Commands
    @client.hybrid_command(name="ban", description="ban a user from using the bot (bot devs only)")
    @is_bot_dev()
    @app_commands.describe(user="the user to ban")
    async def ban_cmd(ctx: commands.Context, user: discord.Member):
        if await check_if_dev(user.id):
            await ctx.reply("you cannot ban another bot developer.", ephemeral=True)
            return
            
        import bot.events
        await asyncio.to_thread(db.ban_user, user.id)
        bot.events.BANNED_USERS.add(user.id)
        await ctx.reply(f"{user.mention} has been banned from using the bot.")

    @client.hybrid_command(name="unban", description="unban a user from using the bot (bot devs only)")
    @is_bot_dev()
    @app_commands.describe(user="the user to unban")
    async def unban_cmd(ctx: commands.Context, user: discord.Member):
        import bot.events
        await asyncio.to_thread(db.unban_user, user.id)
        bot.events.BANNED_USERS.discard(user.id)
        await ctx.reply(f"{user.mention} has been unbanned from using the bot.")

    # View Group
    @client.hybrid_group(name="view", description="view logs and other data")
    @is_admin()
    async def view_group(ctx: commands.Context):
        pass

    @view_say_command := view_group.command(name="say", description="see who said what with say")
    @is_admin()
    async def view_say(ctx: commands.Context):
        logs = await asyncio.to_thread(db.get_say_logs, 20)
        if not logs:
            await ctx.reply("no logs found", ephemeral=True)
            return
        
        lines = []
        for user_name, user_id, content, ts in logs:
            try:
                dt = datetime.datetime.fromisoformat(ts)
                formatted_ts = dt.strftime("%Y-%m-%d %H:%M")
            except:
                formatted_ts = ts
            lines.append(f"{user_name} ({user_id}) at {formatted_ts}: {content}")
        
        response_text = "\n".join(lines)
        if len(response_text) > 1900:
            response_text = response_text[:1900] + "\n..."
        
        await ctx.reply(f"### say logs\n{response_text}", ephemeral=True)

    @view_logs_command := view_group.command(name="logs", description="view the bot logs")
    @is_admin()
    async def view_logs(ctx: commands.Context):
        log_path = "bot.log"
        if not os.path.exists(log_path):
            await ctx.reply("no bot.log file found.", ephemeral=True)
            return

        with open(log_path, "r") as f:
            lines = f.readlines()
            
        last_lines = lines[-15:]
        response_text = "".join(last_lines)
        
        if not response_text.strip():
            await ctx.reply("log file is empty.", ephemeral=True)
            return
            
        if len(response_text) > 1900:
            response_text = response_text[-1900:]
            
        await ctx.reply(f"### last 15 lines of bot.log\n```{response_text}```", ephemeral=True)

    # Clear Group
    @client.hybrid_group(name="clear", description="clear logs and other data")
    @is_admin()
    async def clear_group(ctx: commands.Context):
        pass

    @clear_saylist_command := clear_group.command(name="saylist", description="clear the say logs")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    async def clear_saylist(ctx: commands.Context):
        await asyncio.to_thread(db.clear_say_logs)
        await ctx.reply("say logs cleared", ephemeral=True)

    # Property Group
    @client.hybrid_group(name="property", description="property commands")
    async def property_group(ctx: commands.Context):
        pass

    @property_register_command := property_group.command(name="register", description="register properties thread channel (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="the channel where private property threads will be created")
    async def property_register(ctx: commands.Context, channel: discord.TextChannel = None):
        target_channel = channel or ctx.channel
        await asyncio.to_thread(db.set_config, "property_channel_id", str(target_channel.id))
        await ctx.reply(f"registered {target_channel.mention} for properties")

    @property_buy_command := property_group.command(name="buy", description="buy a private property (costs 50 coins)")
    async def property_buy(ctx: commands.Context, name: str = None, type: str = "thread"):
        # this is just a quick fix since hybrid commands are tricky with custom arguments
        # especially with spaces in names.
        
        args = ctx.message.content.split()
        # manual parsing if prefix command
        if not ctx.interaction:
            # simple parser for --name "..." --type ...
            # this is hacky but we are in a hurry
            import argparse
            class ArgumentParser(argparse.ArgumentParser):
                def error(self, message): pass
            
            parser = ArgumentParser()
            parser.add_argument("--name")
            parser.add_argument("--type")
            
            # split by -- to separate
            parts = ctx.message.content.split("--")
            parsed_args, _ = parser.parse_known_args(parts)
            
            name = parsed_args.name if parsed_args.name else name
            type = parsed_args.type if parsed_args.type else type

        if type == "vc":
            # vc logic
            cost = 100 # lets set a price
            balance = await asyncio.to_thread(db.get_balance, ctx.author.id)
            if balance < cost:
                await ctx.reply(f"you don't have enough coins. a vc property costs {cost} coins (your balance: {balance})")
                return

            new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, -cost)
            
            # create role
            role_name = f"{ctx.author.display_name}'s property"
            role = await ctx.guild.create_role(name=role_name, reason="property purchase")
            await ctx.author.add_roles(role)
            
            # create category
            category = discord.utils.get(ctx.guild.categories, name="vc-properties")
            if not category:
                category = await ctx.guild.create_category("vc-properties")
            
            # create vc
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(connect=False),
                role: discord.PermissionOverwrite(connect=True, view_channel=True),
                ctx.guild.me: discord.PermissionOverwrite(connect=True, view_channel=True)
            }
            vc = await ctx.guild.create_voice_channel(name=name or f"{ctx.author.display_name}'s-vc", category=category, overwrites=overwrites)
            
            await asyncio.to_thread(db.add_property, vc.id, ctx.author.id, "vc")
            await ctx.reply(f"you bought a VC property {vc.mention}! role {role.mention} added. balance: {new_balance}")
            return

        # thread logic (the old way)
        channel_id_str = await asyncio.to_thread(db.get_config, "property_channel_id")
        if not channel_id_str:
            await ctx.reply("properties channel has not been registered yet. an admin needs to run `/property register` first")
            return
            
        channel_id = int(channel_id_str)
        property_channel = ctx.guild.get_channel(channel_id)
        if not property_channel:
            await ctx.reply("registered properties channel not found. please re-register")
            return
            
        cost = 50
        balance = await asyncio.to_thread(db.get_balance, ctx.author.id)
        if balance < cost:
            await ctx.reply(f"you don't have enough coins. a property costs {cost} coins (your balance: {balance})")
            return
            
        new_balance = await asyncio.to_thread(db.update_balance, ctx.author.id, -cost)
        
        thread_name = name or f"{ctx.author.display_name}s property"
        thread_name = thread_name.lower().replace(" ", "-")
        
        try:
            thread = await property_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread
            )
            
            await thread.add_user(ctx.author)
            await asyncio.to_thread(db.add_property, thread.id, ctx.author.id, thread_name)
            
            coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
            await ctx.reply(f"you bought property {thread.mention}! deducted {cost} {coin_emoji} (remaining: {new_balance} {coin_emoji})")
            await thread.send(f"welcome to your private property {ctx.author.mention}! this thread is yours. enjoy")
            
        except Exception as e:
            await asyncio.to_thread(db.update_balance, ctx.author.id, cost)
            await ctx.reply(f"failed to create thread: {e}")

    @property_group.command(name="remove", description="remove a property (admin only)")
    @is_admin()
    async def property_remove(ctx: commands.Context, channel: discord.VoiceChannel = None):
        if not channel:
            await ctx.reply("please mention the voice channel to remove")
            return
            
        await channel.delete()
        await ctx.reply(f"removed property {channel.name}")

    @property_group.command(name="invite", description="invite someone to your vc property")
    async def property_invite(ctx: commands.Context, member: discord.Member, channel: discord.VoiceChannel = None):
        channel = channel or (ctx.author.voice.channel if ctx.author.voice else None)
        if not channel:
            await ctx.reply("please mention a voice channel or join one")
            return
        
        role_name = f"{ctx.author.display_name}'s property"
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        
        if not role or role not in ctx.author.roles:
             await ctx.reply("you don't own this property")
             return
             
        await member.add_roles(role)
        await ctx.reply(f"invited {member.mention} to {channel.name}")

    @property_group.command(name="kick", description="kick someone from your vc property")
    async def property_kick(ctx: commands.Context, member: discord.Member, channel: discord.VoiceChannel = None):
        channel = channel or (ctx.author.voice.channel if ctx.author.voice else None)
        if not channel:
            await ctx.reply("please mention a voice channel or join one")
            return
        
        role_name = f"{ctx.author.display_name}'s property"
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        
        if not role or role not in ctx.author.roles:
             await ctx.reply("you don't own this property")
             return
             
        if role in member.roles:
            await member.remove_roles(role)
            if member.voice and member.voice.channel == channel:
                await member.move_to(None)
            await ctx.reply(f"kicked {member.mention} from {channel.name}")
        else:
            await ctx.reply(f"{member.display_name} is not in this property")

    # EC Group
    @client.hybrid_group(name="ec", description="economy administration commands")
    @is_admin()
    async def ec_group(ctx: commands.Context):
        pass

    @ec_emoji_command := ec_group.command(name="emoji", description="set the economy coin emoji (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(emoji="the emoji representing birdvirus coin")
    async def ec_emoji(ctx: commands.Context, emoji: str):
        await asyncio.to_thread(db.set_config, "coin_emoji", emoji)
        await ctx.reply(f"set economy emoji to {emoji}")

    @ec_reset_command := ec_group.command(name="reset", description="reset a user's balance to 100 (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="the user whose balance to reset")
    async def ec_reset(ctx: commands.Context, user: discord.Member):
        await asyncio.to_thread(db.set_balance, user.id, 100)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"reset {user.display_name}s balance to 100 {coin_emoji}")

    @ec_set_command := ec_group.command(name="set", description="set a user's holding balance (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="the user whose balance to set", amount="the new balance amount")
    async def ec_set(ctx: commands.Context, user: discord.Member, amount: int):
        if amount < 0:
            await ctx.reply("amount cannot be negative")
            return
        await asyncio.to_thread(db.set_balance, user.id, amount)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"set {user.display_name}s holding balance to {amount} {coin_emoji}")

    @ec_setbank_command := ec_group.command(name="setbank", description="set a user's bank balance (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="the user whose bank balance to set", amount="the new bank balance amount")
    async def ec_setbank(ctx: commands.Context, user: discord.Member, amount: int):
        if amount < 0:
            await ctx.reply("amount cannot be negative")
            return
        await asyncio.to_thread(db.set_bank, user.id, amount)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"set {user.display_name}s bank balance to {amount} {coin_emoji}")
