import asyncio
import datetime
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db
from bot.commands import is_admin

def setup_admin(client: commands.Bot):
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
    @app_commands.describe(
        name="desired name for your property",
        type="type of property: thread (old) or vc (new private vc + role)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="thread", value="thread"),
        app_commands.Choice(name="vc", value="vc")
    ])
    async def property_buy(ctx: commands.Context, name: str = None, type: str = "thread"):
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
            
            # create vc
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(connect=False),
                role: discord.PermissionOverwrite(connect=True, view_channel=True),
                ctx.guild.me: discord.PermissionOverwrite(connect=True, view_channel=True)
            }
            vc = await ctx.guild.create_voice_channel(name=name or f"{ctx.author.display_name}'s-vc", overwrites=overwrites)
            
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

    @ec_set_command := ec_group.command(name="set", description="set a user's balance (admin only)")
    @is_admin()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(user="the user whose balance to set", amount="the new balance amount")
    async def ec_set(ctx: commands.Context, user: discord.Member, amount: int):
        if amount < 0:
            await ctx.reply("amount cannot be negative")
            return
        await asyncio.to_thread(db.set_balance, user.id, amount)
        coin_emoji = await asyncio.to_thread(db.get_config, "coin_emoji", "🪙")
        await ctx.reply(f"set {user.display_name}s balance to {amount} {coin_emoji}")
