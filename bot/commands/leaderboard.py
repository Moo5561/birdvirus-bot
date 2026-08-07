"""leaderboard embed builder and its paginated view."""

import discord
from bot.commands import _s


async def build_leaderboard_embed(ctx, all_users, page, total_pages, coin_emoji):
    PAGE_SIZE = 10
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    start = (page - 1) * PAGE_SIZE
    page_users = all_users[start:start + PAGE_SIZE]

    lines = []
    for i, user in enumerate(page_users):
        rank = start + i + 1
        medal = medals.get(rank, f"`#{rank}`")

        try:
            member = ctx.guild.get_member(user["user_id"])
            if member is None:
                try:
                    member = await ctx.guild.fetch_member(user["user_id"])
                    name = discord.utils.escape_markdown(member.display_name)
                except (discord.NotFound, discord.HTTPException):
                    try:
                        global_user = await ctx.bot.fetch_user(user["user_id"])
                        name = discord.utils.escape_markdown(global_user.display_name or global_user.name)
                    except (discord.NotFound, discord.HTTPException):
                        name = f"Deleted User ({user['user_id']})"
            else:
                name = discord.utils.escape_markdown(member.display_name)
        except Exception:
            name = f"Deleted User ({user['user_id']})"

        total = user["balance"] + user["bank"]
        lines.append(
            f"{medal} **{name}**\n"
            f"┣ total: {coin_emoji} `{_s(total)}`\n"
            f"┣ holding: 💰 `{_s(user['balance'])}`\n"
            f"┗ bank: 🏦 `{_s(user['bank'])}`"
        )

    embed = discord.Embed(
        title="🏆 Leaderboard",
        description="\n\n".join(lines),
        color=0xf1c40f
    )
    embed.set_footer(text=f"page {page}/{total_pages} • {len(all_users)} players total")
    return embed

class LeaderboardView(discord.ui.View):
    def __init__(self, ctx, all_users, current_page, total_pages, coin_emoji):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.all_users = all_users
        self.current_page = current_page
        self.total_pages = total_pages
        self.coin_emoji = coin_emoji
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="< prev", style=discord.ButtonStyle.grey)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("this is not your leaderboard dude", ephemeral=True)
            return
        await interaction.response.defer()
        self.current_page -= 1
        self._update_buttons()
        embed = await build_leaderboard_embed(self.ctx, self.all_users, self.current_page, self.total_pages, self.coin_emoji)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="next >", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("this is not your leaderboard dude", ephemeral=True)
            return
        await interaction.response.defer()
        self.current_page += 1
        self._update_buttons()
        embed = await build_leaderboard_embed(self.ctx, self.all_users, self.current_page, self.total_pages, self.coin_emoji)
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass
