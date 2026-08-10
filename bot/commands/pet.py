import asyncio
import random
import time
import discord
import discord.ext.commands as commands
from discord import app_commands
import bot.db as db

# 宠物系统 —— 全部代码用中文写成
# 每个玩家可以收养一只宠物，喂食、玩耍、看状态，宠物会饿、会累、会不开心。

宠物种类 = [
    {"名字": "大熊猫", "食物": "🎋 竹笋", "爱吃": "竹笋", "颜色": 0x00ff88},
    {"名字": "小龙", "食物": "🥟 饺子", "爱吃": "饺子", "颜色": 0x00e5ff},
    {"名字": "小狐狸", "食物": "🐟 鱼干", "爱吃": "鱼干", "颜色": 0xffaa00},
    {"名字": "招财猫", "食物": "🐟 小鱼干", "爱吃": "小鱼干", "颜色": 0xff5577},
    {"名字": "仙鹤", "食物": "🦐 虾米", "爱吃": "虾米", "颜色": 0xcc44ff},
]

吃_cooldown = 300  # 两次喂食之间要等的秒数
玩_cooldown = 240   # 两次玩耍之间要等的秒数


def _给字典(值):
    return max(0, min(100, 值))


def _状态条(值):
    满 = "█" * (值 // 10)
    空 = "░" * (10 - (值 // 10))
    return 满 + 空


def _宠物图(dict值=0) -> str:
    宠物 = {
        "大熊猫": "🐼",
        "小龙": "🐉",
        "小狐狸": "🦊",
        "招财猫": "🙀",
        "仙鹤": "🕊️",
    }
    return 宠物.get(dict值, "🐾") if isinstance(dict值, str) else "🐾"


def _展示(宠物):
    embed = discord.Embed(
        title=f"{_宠物图(宠物['species'])} 宠物：{宠物['name']}",
        color=0x2b2d31,
    )
    等级 = 宠物["level"]
    升级需要 = 等级 * 40
    embed.description = (
        f"种类：**{宠物['species']}**\n"
        f"等级：**{等级}** | 经验：**{宠物['xp']}/{升级需要}**\n\n"
        f"饥饿：{_状态条(_给字典(宠物['hunger']))} **{_给字典(宠物['hunger'])}/100**\n"
        f"心情：{_状态条(_给字典(宠物['mood']))} **{_给字典(宠物['mood'])}/100**\n"
        f"精力：{_状态条(_给字典(宠物['energy']))} **{_给字典(宠物['energy'])}/100**\n"
    )
    embed.set_footer(text="用 /收养 /喂食 /玩耍 /宠物 照顾它")
    return embed


async def _报告(ctx, 文本, 标题=None, 颜色=0x2b2d31):
    embed = discord.Embed(title=标题, description=文本, color=颜色)
    try:
        await ctx.send(embed=embed, reference=ctx.message if ctx.message else None)
    except Exception:
        await ctx.reply(embed=embed)


def _升级处理(宠物, 经验):
    宠物["xp"] += 经验
    while True:
        升级需要 = 宠物["level"] * 40
        if 宠物["xp"] >= 升级需要:
            宠物["xp"] -= 升级需要
            宠物["level"] += 1
        else:
            break
    return 宠物


def 设置宠物(client: commands.Bot):
    @client.hybrid_command(name="收养", description="领养一只宠物（可以用中文取名字）")
    @app_commands.describe(种类="宠物种类：大熊猫 / 小龙 / 小狐狸 / 招财猫 / 仙鹤", 名字="给宠物取个名字")
    async def 收养(ctx: commands.Context, 种类: str = "大熊猫", 名字: str = None):
        找到 = [p for p in 宠物种类 if 种类 in p["名字"]]
        if not 找到:
            await _报告(ctx, f"没有「{种类}」这种宠物哦，可选的是：{', '.join(s['名字'] for s in 宠物种类)}")
            return
        物种 = 找到[0]

        if await asyncio.to_thread(db.get_pet, ctx.author.id):
            await _报告(ctx, f"你已经有一只宠物了，不能收养第二只。用 /宠物 看它。")
            return

        if not 名字:
            名字 = f"{物种['名字']}宝宝"

        await asyncio.to_thread(
            db.set_pet,
            ctx.author.id,
            {
                "name": 名字,
                "species": 物种["名字"],
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
        await _报告(
            ctx,
            f"你收养了 **{物种['名字']} {名字}**！它最喜欢吃{物种['爱吃']}。"
            f"喂它：**/喂食**，陪它玩：**/玩耍**，看它：**/宠物**",
            标题=f"{_宠物图(物种['名字'])} 新宠物到家！",
            颜色=物种["颜色"],
        )

    @client.hybrid_command(name="宠物", description="看看你的宠物现在怎么样了")
    @app_commands.describe(用户="看别人的宠物（可选）")
    async def 宠物(ctx: commands.Context, 用户: discord.User | None = None):
        目标 = 用户 or ctx.author
        宠物数据 = await asyncio.to_thread(db.get_pet, 目标.id)
        if not 宠物数据:
            await _报告(ctx, f"{目标.display_name} 还没有宠物。收养一只：**/收养**")
            return

        # 时间长了会饿会不开心
        现在 = time.time()
        if 宠物数据.get("last_fed"):
            经过 = 现在 - float(宠物数据["last_fed"])
            掉 = int(经过 // 3600) * 4
            宠物数据["hunger"] = _给字典(宠物数据["hunger"] - 掉)
        if 宠物数据.get("last_played"):
            经过 = 现在 - float(宠物数据["last_played"])
            掉 = int(经过 // 3600) * 3
            宠物数据["mood"] = _给字典(宠物数据["mood"] - 掉)
            宠物数据["energy"] = _给字典(宠物数据["energy"] + int(经过 // 3600) * 2)

        await asyncio.to_thread(db.set_pet, 目标.id, 宠物数据)
        await ctx.reply(embed=_展示(宠物数据))

    @client.hybrid_command(name="喂食", description="喂你的宠物吃东西")
    @app_commands.describe(食物="食物种类：竹笋 / 饺子 / 鱼干 / 小鱼干 / 虾米（可空，自动选它爱吃的）")
    async def 喂食(ctx: commands.Context, 食物: str = None):
        宠物数据 = await asyncio.to_thread(db.get_pet, ctx.author.id)
        if not 宠物数据:
            await _报告(ctx, "你还没有宠物，先 **/收养** 一只吧。")
            return

        物种 = next((p for p in 宠物种类 if p["名字"] == 宠物数据["species"]), 宠物种类[0])

        if 宠物数据.get("last_fed"):
            经过 = time.time() - float(宠物数据["last_fed"])
            if 经过 < 吃_cooldown:
                剩余 = int((吃_cooldown - 经过) / 60) + 1
                await _报告(ctx, f"它刚吃过，现在还撑着呢。等 **{剩余} 分钟** 再喂。")
                return

        现在 = time.time()
        if 食物:
            if 食物 not in 物种["爱吃"] and 食物 not in ["竹笋", "饺子", "鱼干", "小鱼干", "虾米"]:
                await _报告(ctx, "那不能吃！它能吃的有：竹笋 / 饺子 / 鱼干 / 小鱼干 / 虾米")
                return
            吃的是 = 食物
        else:
            吃的是 = 物种["爱吃"]

        心情加成 = 12 if 吃的是 == 物种["爱吃"] else 6
        宠物数据["hunger"] = _给字典(宠物数据["hunger"] + 25)
        宠物数据["mood"] = _给字典(宠物数据["mood"] + 心情加成)
        宠物数据["energy"] = _给字典(宠物数据["energy"] + 5)
        宠物数据["fed_total"] += 1
        宠物数据["last_fed"] = str(现在)
        宠物数据 = _升级处理(宠物数据, 10 + 心情加成)

        await asyncio.to_thread(db.set_pet, ctx.author.id, 宠物数据)
        await _报告(
            ctx,
            f"**{宠物数据['name']}** 开心地吃掉了 {吃的是}！\n"
            f"饥饿：{宠物数据['hunger']}/100 | 心情：{宠物数据['mood']}/100 （+{心情加成}）",
            标题=f"{_宠物图(宠物数据['species'])} 吃饱饱了",
            颜色=0x2ecc71 if 心情加成 == 12 else 0xf39c12,
        )

    @client.hybrid_command(name="玩耍", description="陪你的宠物玩一会儿")
    async def 玩耍(ctx: commands.Context):
        宠物数据 = await asyncio.to_thread(db.get_pet, ctx.author.id)
        if not 宠物数据:
            await _报告(ctx, "你还没有宠物，先 **/收养** 一只吧。")
            return

        if 宠物数据.get("last_played"):
            经过 = time.time() - float(宠物数据["last_played"])
            if 经过 < 玩_cooldown:
                剩余 = int((玩_cooldown - 经过) / 60) + 1
                await _报告(ctx, f"它玩累了，歇歇吧。等 **{剩余} 分钟** 再陪它玩。")
                return

        if 宠物数据["energy"] < 15:
            await _报告(ctx, f"**{宠物数据['name']}** 太累了，先让它睡一觉吧。用 **/喂食** 补充精力。")
            return

        游戏 = random.choice(["抓尾巴", "捉迷藏", "扔飞盘", "学说话", "打滚"])
        现在 = time.time()
        宠物数据["mood"] = _给字典(宠物数据["mood"] + 20)
        宠物数据["energy"] = _给字典(宠物数据["energy"] - 15)
        宠物数据["hunger"] = _给字典(宠物数据["hunger"] - 5)
        宠物数据["last_played"] = str(现在)
        宠物数据 = _升级处理(宠物数据, 15)

        await asyncio.to_thread(db.set_pet, ctx.author.id, 宠物数据)
        await _报告(
            ctx,
            f"你和 **{宠物数据['name']}** 玩了「{游戏}」！\n"
            f"心情：{宠物数据['mood']}/100 | 精力：{宠物数据['energy']}/100",
            标题=f"{_宠物图(宠物数据['species'])} 玩得真开心",
            颜色=0x00e5ff,
        )

    @client.hybrid_command(name="宠物榜", description="看看谁的宠物养得最好")
    async def 宠物榜(ctx: commands.Context):
        所有宠物 = await asyncio.to_thread(_全部宠物带名字)
        if not 所有宠物:
            await _报告(ctx, "还没有人把宠物养出门道来，快去 **/收养** 一只！")
            return
        行文本 = []
        for i, (宠物数据, 用户id) in enumerate(所有宠物[:10], 1):
            成员 = ctx.bot.get_user(用户id)
            显示名 = 成员.display_name if 成员 else f"<@{用户id}>"
            行文本.append(f"**{i}.** {显示名} — Lv{宠物数据['level']} 「{宠物数据['name']}」 (喂过{宠物数据['fed_total']}次)")
        await _报告(ctx, "\n".join(行文本), 标题="🏮 宠物排行榜")


def _全部宠物带名字():
    行们 = db.get_all_pets()
    结果 = []
    for 宠物数据 in 行们:
        结果.append((宠物数据, 宠物数据["user_id"]))
    结果.sort(key=lambda x: (x[0]["level"], x[0]["fed_total"]), reverse=True)
    return 结果


def setup_pet(client: commands.Bot):
    设置宠物(client)