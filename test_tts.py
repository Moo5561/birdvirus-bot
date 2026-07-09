import asyncio
import os
from g4f.client import Client

async def main():
    try:
        client_g4f = Client()
        def generate_tts():
            os.makedirs("generated_media", exist_ok=True)
            return client_g4f.media.generate(
                "mango",
                model="gpt-4o-mini-tts",
                audio={"voice": "coral"},
                response_format="b64_json"
            )
        response = await asyncio.to_thread(generate_tts)
        item = response.data[0]
        print("Item b64_json length:", len(getattr(item, 'b64_json', '')) if getattr(item, 'b64_json', None) else 0)
    except Exception as e:
        print("Failed:", e)

asyncio.run(main())