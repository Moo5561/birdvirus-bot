import asyncio
from g4f.client import AsyncClient

async def main():
    try:
        client_g4f = AsyncClient()
        response = await client_g4f.media.generate(
            "mango",
            model="gpt-4o-mini-tts",
            audio={"voice": "coral"}
        )
        print("Response data:", response.data)
        item = response.data[0]
        print("Item URL:", getattr(item, 'url', None))
    except Exception as e:
        print("Failed:", e)

asyncio.run(main())