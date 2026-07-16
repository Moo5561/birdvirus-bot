# birdvirus-bot

the official discord bot for the birdvirus community. multipurpose economy, audio, and ai chat bot built with discord.py.

## features

- **economy** — blackjack, roulette, slots, plinko, horse racing, birdvirus guess game, fishing, begging. full bank system with deposits/withdrawals.
- **voice & audio** — queue system for local files and youtube (via yt-dlp). random birdvirus/bird sounds play automatically in vc. g4f text-to-speech support.
- **job system** — 6 jobs (janitor, chef, developer, hacker, miner, thief) each with a unique minigame, levels, xp, promotions, and random events.
- **properties** — buy private threads or voice channels with custom roles, invite/kick system.
- **ai chat** — `/chat` talks to you with context memory, optional web search via playwright screenshots.
- **admin** — ban/unban users, view logs, manage economy, configure coin emoji.

## setup

1. install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. install ffmpeg and add it to your system path.
3. copy `.env.example` to `.env` and add your keys:
   - `KEY` — discord bot token
   - `API_KEY` — gemini api key (for `/chat` and `/internet search`)
4. (optional) place a `cookies.txt` in netscape format for yt-dlp youtube access.

## running

```bash
python main.py --host "your_name"
```

## self-hosting notes

- the bot expects a sqlite3 database at `birdvirus.db` (auto-created on first run).
- audio files go in the `mp3/` directory.
- the nightly/dev bot (id `1522117141090799697`) uses `ht!` prefix and bypasses economy checks automatically.
- the `--host` flag sets the activity status shown on discord.

## commands

all commands are hybrid (slash + prefix). prefix is `%` for the main bot, `ht!` for nightly.

| category | commands |
|----------|----------|
| economy | `/pure chance`, `/pure blackjack`, `/pure slots`, `/pure roulette`, `/pure insaneroll`, `/pure birdvirus`, `/pure plinko`, `/pure horse`, `/beg`, `/fish`, `/deposit`, `/withdraw`, `/balance` |
| voice | `/vc join`, `/vc leave`, `/vc stop`, `/vc bird`, `/vc droid`, `/stop`, `/play`, `/bad apple` |
| jobs | `/job list`, `/job info`, `/job apply`, `/job work`, `/job quit`, `/job beg` |
| properties | `/property register`, `/property buy`, `/property remove`, `/property invite`, `/property kick` |
| admin | `/ban`, `/unban`, `/view say`, `/view logs`, `/clear saylist`, `/ec emoji`, `/ec reset`, `/ec set`, `/ec setbank` |
| utility | `/ping`, `/gif`, `/version`, `/chat`, `/chat_reset`, `/say`, `/eatbomb`, `/tts`, `/internet search` |
