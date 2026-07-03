# birdvirus-bot

the official, highly modular, and extremely tuff discord bot for the birdvirus community.

## overview
this repo contains the source code for birdvirus bot. it's a multipurpose bot built with `discord.py` that handles a full custom economy, advanced voice channel audio queueing (with yt-dlp integration), private vc properties, and an ai chatbot.

## features
- **economy**: gamble your life savings away with blackjack, roulette, slots, plinko, or just go fishing. complete with a full banking system.
- **voice & audio**: a robust audio queueing system. play local files, stream directly from youtube via `yt-dlp`, or convert text to speech using `g4f`. 
- **properties**: buy your own private voice channels, complete with custom roles and kicking/inviting powers.
- **ai chat**: talk to the bot using `/chat`. it has context memory and can even browse the web to describe search results.

## setup
1. clone the repo.
2. install dependencies: `pip install -r requirements.txt`
3. install ffmpeg and add it to your system PATH.
4. copy `.env.example` to `.env` and add your discord token and gemini api key.
5. (optional) add a `cookies.txt` file in netscape format to the root folder to allow youtube playback without getting blocked.

## running the bot
you must specify the host when running the bot so everyone knows who spun it up:
```bash
python main.py --host "your_name"
```
