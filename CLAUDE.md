# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `AGENTS.md` too — it defines the tone/personality rules for this repo. `DEVELOPMENT.md` has per-subsystem detail (jobs, economy, properties, audio, bans).

## commands

```bash
./setup.sh                      # venv + pip install -r requirements.txt + playwright install chromium
python main.py --host "name"    # run the bot; --host is required, it only sets the discord activity text
python -m py_compile main.py bot/*.py bot/commands/*.py   # the only "test" this repo has
```

There is no test suite, linter, or formatter configured. The syntax check above is what CI-equivalent verification looks like here, and `bot/commands/update.py:syntax_check()` runs the same `py_compile` sweep over `bot/**/*.py` before the bot restarts itself.

External requirements: `ffmpeg` on PATH (voice), `.env` with `KEY` (discord token) and `API_KEY` (gemini), optional `cookies.txt` for yt-dlp.

The static site (`birdvirus-cloud/`) is a separate Node/Express service: `npm start` in that directory, needs `OPENAI_API_KEY`. It is not imported by the bot.

## architecture

`main.py` builds a `BirdBot(AutoShardedBot)` and calls `bot.events.setup(client)` then `bot.commands.setup(client)`. There are no discord.py Cogs — every module exports a `setup_<name>(client)` function that registers hybrid commands via closures, and `bot/commands/__init__.py` calls them all. **A new command file is dead code until it is imported and called in `bot/commands/__init__.py:setup()`.**

Shared mutable state lives in `bot/commands/__init__.py`, not in the modules that use it: `audio_queues` (guild id → pending audio), `voice_joiners` (guild id → user who summoned the bot), `in_game` (user ids with an active game, guarded by `game_lock`/`game_unlock`). `bot/events.py` imports `audio_queues` lazily inside the handler to avoid a circular import — keep that pattern.

`main.py` overrides `get_context`/`process_commands` to let allowlisted bot IDs (`ALLOWED_BOT_IDS`) invoke commands, which stock discord.py refuses. If you touch prefix parsing, that override is a near-copy of upstream `get_context` and has to stay in sync with the installed discord.py.

### identity switching

The bot decodes its own ID from the token in `main.py` before anything else. `bot/config.py:NIGHTLY_BOT_ID` is the nightly/dev bot: prefix `ht!` instead of `%`, `BOT_DB_PATH=birdvirus_nightly.db`, and it bypasses economy balance checks — test that with `is_nightly(ctx.bot)` from `bot/commands/__init__.py`, never a fresh ID literal. Main bot is `1518310857598308433`. Anything keyed to environment should follow this ID check rather than a new flag.

### database

`bot/db.py` is plain synchronous `sqlite3`, opening a connection per call, path from `BOT_DB_PATH` (default `birdvirus.db`). Every call from command code must be wrapped in `await asyncio.to_thread(...)` or it blocks the event loop. New tables go in `init_db()` as `CREATE TABLE IF NOT EXISTS` — there are no migrations, so new columns need defensive `ALTER TABLE`/default handling for existing databases.

`birdvirus.db` is committed to the repo, which is why `/update` runs `git rm --cached birdvirus.db` before pulling.

### self-updating

`/update` (bot devs only) writes `update_snapshot.txt` with the current HEAD, `git pull --autostash`, runs the syntax check, and `os.execv`s itself. On failure it `git reset --hard`s back. `on_ready` in `bot/events.py` looks for a leftover `update_snapshot.txt` and reverts+restarts, treating it as a crash mid-update. Anything that changes startup behaviour has to survive being re-exec'd with the same argv.

### permissions

Both checks live in `bot/commands/__init__.py` and share `_is_configured_admin()` (owner list in `bot/config.py:OWNER_IDS` → `admin_ids` config row). `@is_admin()` additionally accepts a guild administrator; `@is_bot_dev()` does not, so host-level commands like `/update` are owners-only. `ctx.author.guild_permissions` only exists on `Member`, so any new perm check needs a `ctx.guild is not None` guard — commands are DM-enabled globally.

### messaging

`commands.Context.send` and `.reply` are monkeypatched at import time in `bot/commands/__init__.py` to fall back to a DM on `discord.Forbidden`. Consequences: they can return `None`, and they drop `reference`/`mention_author` on the fallback path. Don't assume a Message came back.

Bans are checked in three places (`@client.check`, `tree.interaction_check`, `on_message`) against a file list (`bot/banned_users.txt`, via `bot/bans.py`) with the `banned_users` table as fallback.

### ai / audio

`/chat` exposes an `execute` tool to the model, restricted to `ffmpeg`/`ffprobe`/`yt-dlp`. It runs via `create_subprocess_exec` on a `shlex.split` argv — never reintroduce a shell there, or the allowlist becomes bypassable with `&&`.

`/chat`, `/internet search`, and `/tts` in `bot/commands/utility.py` talk to Gemini through its **OpenAI-compatible endpoint** (`generativelanguage.googleapis.com/v1beta/openai/chat/completions`) with `API_KEY` as a bearer token, model `gemini-3.1-flash-lite`. TTS goes through `g4f` with an ordered provider fallback (OpenAIFM → Gemini) because OpenAIFM gets rate-limited; keep the list-of-providers loop shape when adding one.

`bot/commands/voice.py` owns `queue_audio()`, which handles both local `mp3/` paths and yt-dlp URLs, and the `voice_announcer` background task. Volume is `PCMVolumeTransformer` at 0.60, except files named `badapple_max` at 1.0.

## conventions

- all user-facing bot text is lowercase and casual, punctuation only where it matters.
- commands are `@client.hybrid_command` / `@client.hybrid_group` so slash and prefix both work; `default_allowed_contexts` in `main.py` already enables DMs and user installs, so guard anything that needs a guild (`ctx.guild is None`) yourself.
- use `_s()` from `bot/commands/__init__.py` to format coin amounts (1.2k / 5.7m / scientific).
- consume shop items with `take_cheat(user_id, type)` from `bot/commands/shop.py`, not `ACTIVE_CHEATS.pop()` — a bare pop burns whatever unrelated item the user had active.
- `version.txt` is written by the `Update Version File` workflow on pushes to `main` — don't hand-edit it.
