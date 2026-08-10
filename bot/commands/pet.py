import asyncio
import random
import time
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db

# pet system — adopt one pet, feed it, play with it, watch it level up.
# pets get hungry, bored, and tired over time.

PETS = [
    {"name": "Giant Panda", "food": "🎋 Bamboo", "favorite": "Bamboo", "color": 0x00ff88},
    {"name": "Dragon", "food": "🥟 Dumpling", "favorite": "Dumpling", "color": 0x00e5ff},
    {"name": "Fox", "food": "🐟 Dried Fish", "favorite": "Dried Fish", "color": 0xffaa00},
    {"name": "Lucky Cat", "food": "🐟 Small Fish", "favorite": "Small Fish", "color": 0xff5577},
    {"name": "Crane", "food": "🦐 Shrimp", "favorite": "Shrimp", "color": 0xcc44ff},
]

FEED_COOLDOWN = 300  # seconds between feedings
PLAY_COOLDOWN = 240  # seconds between play sessions


def _clamp(value):
    return max(0, min(100, value))


def _bar(value):
    filled = "█" * (value // 10)
    empty = "░" * (10 - (value // 10))
    return filled + empty


def _emoji(name: str = "") -> str:
    emojis = {
        "Giant Panda": "🐼",
        "Dragon": "🐉",
        "Fox": "🦊",
        "Lucky Cat": "🙀",
        "Crane": "🕊️",
    }
    return emojis.get(name, "🐾")


def _display(pet):
    level = pet["level"]
    xp_needed = level * 40
    embed = discord.Embed(
        title=f"{_emoji(pet['species'])} Pet: {pet['name']}",
        color=0x2b2d31,
    )
    embed.description = (
        f"Species: **{pet['species']}**\n"
        f"Level: **{level}** | XP: **{pet['xp']}/{xp_needed}**\n\n"
        f"Hunger: {_bar(_clamp(pet['hunger']))} **{_clamp(pet['hunger'])}/100**\n"
        f"Mood: {_bar(_clamp(pet['mood']))} **{_clamp(pet['mood'])}/100**\n"
        f"Energy: {_bar(_clamp(pet['energy']))} **{_clamp(pet['energy'])}/100**\n"
    )
    embed.set_footer(text="use /adopt /feed /playwith /pet to take care of it")
    return embed


async def _report(ctx, text: str, title=None, color=0x2b2d31):
    embed = discord.Embed(title=title, description=text, color=color)
    try:
        await ctx.send(embed=embed, reference=ctx.message if ctx.message else None)
    except Exception:
        await ctx.reply(embed=embed)


def _gain_xp(pet, xp):
    pet["xp"] += xp
    while True:
        xp_needed = pet["level"] * 40
        if pet["xp"] >= xp_needed:
            pet["xp"] -= xp_needed
            pet["level"] += 1
        else:
            break
    return pet


def _all_pets_ranked():
    rows = db.get_all_pets()
    result = [(p, p["user_id"]) for p in rows]
    result.sort(key=lambda x: (x[0]["level"], x[0]["fed_total"]), reverse=True)
    return result


def setup_pets(client: commands.Bot):
    @client.hybrid_command(name="adopt", description="adopt a pet")
    @app_commands.describe(species="Giant Panda / Dragon / Fox / Lucky Cat / Crane", name="name your pet")
    async def adopt(ctx: commands.Context, species: str = "Giant Panda", name: str = None):
        match = [p for p in PETS if species in p["name"]]
        if not match:
            await _report(ctx, f"no pet called {species} — pick one of: {', '.join(p['name'] for p in PETS)}")
            return
        pet_type = match[0]

        if await asyncio.to_thread(db.get_pet, ctx.author.id):
            await _report(ctx, "you already have a pet, you can't adopt a second one. use /pet to check on it.")
            return

        if not name:
            name = f"{pet_type['name']} Baby"

        await asyncio.to_thread(
            db.set_pet,
            ctx.author.id,
            {
                "name": name,
                "species": pet_type["name"],
                "hunger": 80,
                "mood": 60,
                "energy": 70,
                "level": 1,
                "xp": 0,
                "fed_total": 0,
                "last_fed": None,
                "last_played": None,
            },
        )
        await _report(
            ctx,
            f"you adopted a **{pet_type['name']}** named **{name}**! it loves {pet_type['favorite']}.\n"
            f"feed it: **/feed**, play with it: **/play**, check on it: **/pet**",
            title=f"{_emoji(pet_type['name'])} new pet!",
            color=pet_type["color"],
        )

    @client.hybrid_command(name="pet", description="check on your pet")
    @app_commands.describe(user="check someone else's pet (optional)")
    async def pet(ctx: commands.Context, user: discord.User | None = None):
        target = user or ctx.author
        pet_data = await asyncio.to_thread(db.get_pet, target.id)
        if not pet_data:
            await _report(ctx, f"{target.display_name} doesn't have a pet yet. adopt one: **/adopt**")
            return

        now = time.time()
        if pet_data.get("last_fed"):
            elapsed = now - float(pet_data["last_fed"])
            drop = int(elapsed // 3600) * 4
            pet_data["hunger"] = _clamp(pet_data["hunger"] - drop)
        if pet_data.get("last_played"):
            elapsed = now - float(pet_data["last_played"])
            drop = int(elapsed // 3600) * 3
            pet_data["mood"] = _clamp(pet_data["mood"] - drop)
            pet_data["energy"] = _clamp(pet_data["energy"] + int(elapsed // 3600) * 2)

        await asyncio.to_thread(db.set_pet, target.id, pet_data)
        await ctx.reply(embed=_display(pet_data))

    @client.hybrid_command(name="feed", description="feed your pet")
    @app_commands.describe(food="Bamboo / Dumpling / Dried Fish / Small Fish / Shrimp (defaults to its favorite)")
    async def feed(ctx: commands.Context, food: str = None):
        pet_data = await asyncio.to_thread(db.get_pet, ctx.author.id)
        if not pet_data:
            await _report(ctx, "you don't have a pet yet — **/adopt** one first.")
            return

        pet_type = next((p for p in PETS if p["name"] == pet_data["species"]), PETS[0])

        if pet_data.get("last_fed"):
            elapsed = time.time() - float(pet_data["last_fed"])
            if elapsed < FEED_COOLDOWN:
                remaining = int((FEED_COOLDOWN - elapsed) / 60) + 1
                await _report(ctx, f"it already ate recently. try again in **{remaining} min**.")
                return

        now = time.time()
        foods = ["Bamboo", "Dumpling", "Dried Fish", "Small Fish", "Shrimp"]
        if food:
            if food not in pet_type["favorite"] and food not in foods:
                await _report(ctx, "that's not food! it can eat: Bamboo / Dumpling / Dried Fish / Small Fish / Shrimp")
                return
            eaten = food
        else:
            eaten = pet_type["favorite"]

        mood_gain = 12 if eaten == pet_type["favorite"] else 6
        pet_data["hunger"] = _clamp(pet_data["hunger"] + 25)
        pet_data["mood"] = _clamp(pet_data["mood"] + mood_gain)
        pet_data["energy"] = _clamp(pet_data["energy"] + 5)
        pet_data["fed_total"] += 1
        pet_data["last_fed"] = str(now)
        pet_data = _gain_xp(pet_data, 10 + mood_gain)

        await asyncio.to_thread(db.set_pet, ctx.author.id, pet_data)
        await _report(
            ctx,
            f"**{pet_data['name']}** happily ate the {eaten}!\n"
            f"hunger: {pet_data['hunger']}/100 | mood: {pet_data['mood']}/100 (+{mood_gain})",
            title=f"{_emoji(pet_data['species'])} all fed up",
            color=0x2ecc71 if mood_gain == 12 else 0xf39c12,
        )

    @client.hybrid_command(name="playwith", description="play with your pet")
    async def play(ctx: commands.Context):
        pet_data = await asyncio.to_thread(db.get_pet, ctx.author.id)
        if not pet_data:
            await _report(ctx, "you don't have a pet yet — **/adopt** one first.")
            return

        if pet_data.get("last_played"):
            elapsed = time.time() - float(pet_data["last_played"])
            if elapsed < PLAY_COOLDOWN:
                remaining = int((PLAY_COOLDOWN - elapsed) / 60) + 1
                await _report(ctx, f"it's tired from playing. try again in **{remaining} min**.")
                return

        if pet_data["energy"] < 15:
            await _report(ctx, f"**{pet_data['name']}** is too tired, let it rest. use **/feed** for energy.")
            return

        game = random.choice(["chase the tail", "hide and seek", "fetch", "learn to talk", "roll over"])
        now = time.time()
        pet_data["mood"] = _clamp(pet_data["mood"] + 20)
        pet_data["energy"] = _clamp(pet_data["energy"] - 15)
        pet_data["hunger"] = _clamp(pet_data["hunger"] - 5)
        pet_data["last_played"] = str(now)
        pet_data = _gain_xp(pet_data, 15)

        await asyncio.to_thread(db.set_pet, ctx.author.id, pet_data)
        await _report(
            ctx,
            f"you played **{game}** with **{pet_data['name']}**!\n"
            f"mood: {pet_data['mood']}/100 | energy: {pet_data['energy']}/100",
            title=f"{_emoji(pet_data['species'])} had a great time",
            color=0x00e5ff,
        )

    @client.hybrid_command(name="petpool", description="best-kept pets leaderboard")
    async def petpool(ctx: commands.Context):
        all_pets = await asyncio.to_thread(_all_pets_ranked)
        if not all_pets:
            await _report(ctx, "nobody has a pet worth showing off yet — go **/adopt** one!")
            return
        lines = []
        for i, (pet_data, uid) in enumerate(all_pets[:10], 1):
            member = ctx.bot.get_user(uid)
            display = member.display_name if member else f"<@{uid}>"
            lines.append(f"**{i}.** {display} — Lv{pet_data['level']} [{pet_data['name']}] ({pet_data['fed_total']} feedings)")
        await _report(ctx, "\n".join(lines), title="🏆 pet leaderboard")


def setup_pet(client: commands.Bot):
    setup_pets(client)