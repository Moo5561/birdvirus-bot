# development

## architecture

```
birdvirus-bot/
├── main.py                  # entry point, bot setup, prefix logic
├── bot/
│   ├── config.py            # loads KEY and API_KEY from .env
│   ├── db.py                # sqlite3 — economy, jobs, properties, config, bans, chat resets
│   ├── bans.py              # async file-based ban list (banned_users.txt)
│   ├── events.py            # on_ready, global ban check, "67" trigger, error handler
│   └── commands/
│       ├── __init__.py      # monkeypatches send/reply for dm fallback, is_admin/is_bot_dev checks, setup()
│       ├── utility.py       # ping, gif, version, chat (ai), chat_reset, say, eatbomb, tts, internet search
│       ├── economy.py       # pure group (chance, blackjack, slots, roulette, insaneroll, birdvirus, plinko, horse), beg, fish, deposit, withdraw, balance
│       ├── voice.py         # vc group (join, leave, stop, bird, droid), bad apple, play, voice announcer task
│       ├── admin.py         # ban, unban, view group (say, logs), clear group, property group, ec group
│       ├── blackjack.py     # BlackjackView, draw_card, calculate_hand
│       ├── horserace.py     # HorseRaceView with select horse and animated race
│       └── job.py           # job group (list, info, apply, work, quit, beg) + 6 minigame views
├── mp3/                     # audio files (birdvirus.mp3, bird.mp3, badapple.mp3, droid.mp3, etc.)
├── templates/               # html templates (notable: birdvirus-cloud/)
├── index.html               # redirects to birdvirus-cloud/
├── version.txt              # current branch and commit
├── .env.example             # key template
├── requirements.txt         # dependencies
└── setup.sh                 # venv + dependency installer
```

## conventions

- all database calls from commands must be wrapped in `await asyncio.to_thread(...)` — `db.py` is synchronous sqlite3.
- `ctx.send` and `ctx.reply` are monkeypatched in `bot/commands/__init__.py` to fallback to dms on `discord.Forbidden`.
- admin commands use `@is_admin()` (checks a hardcoded list + db config + guild admin perms).
- dev-only commands use `@is_bot_dev()` (same hardcoded list + db config, no guild perm fallback).
- messaging is casual, all lowercase, no punctuation unless it's code.

## adding a new command

1. add the function in the appropriate file under `bot/commands/`.
2. call the setup function from `bot/commands/__init__.py`.
3. if it reads/writes to the db, wrap the call in `await asyncio.to_thread(...)`.
4. since `default_allowed_contexts` is set globally in `main.py`, new commands automatically work in dms and group chats.

## economy system

- users start with 100 coins in their holding balance and 0 in bank.
- the bank earns interest (configured via db, not yet exposed as a command).
- coin emoji is configurable via `/ec emoji` (stored in config table as `coin_emoji`).
- nightly dev bot (id `1522117141090799697`) bypasses all balance checks and has infinite coins.

## audio system

- `bot/commands/voice.py` manages a per-guild queue (`audio_queues` dict) and tracks who joined (`voice_joiners` dict).
- `queue_audio()` handles both local mp3 paths and remote urls/yt-dlp streams.
- two volume tiers: 0.60 for normal, 1.0 for files named "badapple_max".
- a background task `voice_announcer` randomly plays bird sounds in all connected vcs every 15 seconds (80% chance).

## job system

jobs are defined in `JOBS` dict in `bot/commands/job.py`:
- `janitor` — click the poop button (9 tiles)
- `chef` — select ingredients in order (recipe memory minigame)
- `developer` — pick the syntactically correct code snippet
- `hacker` — crack a 3-digit pin with feedback (mastermind-style)
- `miner` — 5x5 grid, find diamond, avoid lava
- `thief` — push your luck stealing through 4 stages with escalating risk/reward

each job has:
- base pay (scales with level)
- cooldown (minutes)
- requirement level (must be level N overall to apply)
- random events (15% chance per shift)
- speed bonuses (completion time multiplied against par time, penalizes slow completions)

xp needed per level = `level * 100`

## property system

- `/property register <channel>` — sets the channel where property threads are created.
- `/property buy` — creates a private thread (50 coins) or a private vc with custom role (100 coins).
- properties are tracked in the `properties` table in birdvirus.db.

## bot ids

defined in `AGENTS.md`:
- main bot: `1518310857598308433`
- nightly/dev: `1522117141090799697` — uses `ht!` prefix, bypasses economy checks

## ban system

two ban layers:
1. file-based: `bot/banned_users.txt` (read async via `bans.py`)
2. db-based: `banned_users` table in birdvirus.db

both are checked in `events.py` — global check for prefix commands, tree check for slash commands, and on_message listener.

## error handling

- `UserBanned` exception (`bot/events.py`) is silently ignored.
- `CheckFailure` / `MissingPermissions` responds with "you don't have permission to do that".
- `CommandOnCooldown` responds with the remaining cooldown time.
- all other errors are printed to console, not exposed to users (except api errors in chat).
- the monkeypatched `send`/`reply` in `__init__.py` silently catches `discord.Forbidden` and falls back to dms.
