# Migrate hardbans into the runtime ban file

import asyncio
import bot.bans as bans

async def migrate():
    try:
        # read hardbans file
        with open('bot/hardbans.txt', 'r', encoding='utf-8') as f:
            ids = [int(line.strip()) for line in f if line.strip()]
    except Exception:
        ids = []

    # add each to the main ban file
    for uid in ids:
        try:
            await bans.add_ban(uid)
        except Exception:
            pass

if __name__ == '__main__':
    asyncio.run(migrate())
