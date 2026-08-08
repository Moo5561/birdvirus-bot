# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

This file covers how the bot is wired together and the places where it bites. Read `AGENTS.md` first — it has the non-negotiable rules and the tone this repo is written in. `DEVELOPMENT.md` has per-subsystem detail (jobs, economy, stocks, properties, audio, bans).

## commands

```bash
./setup.sh                      # venv + pip install -r requirements.txt + playwright install chromium
python main.py --host "name"    # run the bot; --host is required, it only sets the discord activity text
python -m py_compile main.py bot/*.py bot/commands/*.py   # the only "test" this repo has
```

There is no test suite, linter, or formatter. `bot/commands/update.py:syntax_check()` runs that same `py_compile` sweep over `bot/**/*.py` before the bot restarts itself, so it is also the gate on self-updates.

External requirements: `ffmpeg` on PATH (voice), `.env` with `KEY` (discord token) and `API_KEY` (gemini), optional `cookies.txt` for yt-dlp.

The static site (`birdvirus-cloud/`) is a separate Node/Express service: `npm start` in that directory, needs `OPENAI_API_KEY`. It is not imported by the bot and does not share its database.

## architecture

`main.py` builds a `BirdBot(AutoShardedBot)`, then calls `bot.events.setup(client)` followed by `bot.commands.setup(client)`. There are no discord.py Cogs — every module exports a `setup_<name>(client)` function that registers hybrid commands via closures, and `bot/commands/__init__.py:setup()` calls them in a fixed order.

Everything is `@client.hybrid_command` / `@client.hybrid_group`, so slash and prefix both work from one definition.

### shared state

Mutable state lives in `bot/commands/__init__.py`, not in the modules that use it:

- `audio_queues` — guild id → pending audio
- `voice_joiners` — guild id → the user who summoned the bot
- `in_game` — user ids with an active game, guarded by `game_lock(ctx)` / `game_unlock(ctx)` so one user can't run two interactive games at once

`bot/events.py` imports `audio_queues` lazily *inside* the handler to avoid a circular import. Keep that pattern — the View classes in `blackjack.py`, `horserace.py`, and `catrace.py` import helpers from `__init__.py` while `__init__.py` imports them back, so the import graph is already load-order sensitive.

### bot-to-bot invocation

`main.py` overrides `get_context` and `process_commands` so allowlisted bot IDs (`ALLOWED_BOT_IDS`) can invoke commands, which stock discord.py refuses outright. That override is a near-copy of upstream `get_context` — if you touch prefix parsing, it has to stay in sync with the installed discord.py version.

### identity switching

The bot decodes its own ID from the token in `main.py` before anything else runs. `bot/config.py:NIGHTLY_BOT_ID` is the nightly/dev bot: prefix `ht!` instead of `%`, `BOT_DB_PATH=birdvirus_nightly.db`, and it bypasses economy balance checks.

Test for it with `is_nightly(ctx.bot)` from `bot/commands/__init__.py`. Anything keyed to environment should hang off this ID check rather than a new flag.

### database

`bot/db.py` is plain synchronous `sqlite3`, opening a connection per call, path from `BOT_DB_PATH` (default `birdvirus.db`). Every call from command code must be wrapped in `await asyncio.to_thread(...)` or it blocks the event loop.

New tables go in `init_db()` as `CREATE TABLE IF NOT EXISTS`. **There are no migrations**, so a new column on an existing table needs defensive `ALTER TABLE` / default handling — production databases already exist and will not be recreated.

`birdvirus.db` is committed to the repo, which is why `/update` runs `git rm --cached birdvirus.db` before pulling.

### permissions

Both checks live in `bot/commands/__init__.py` and share `_is_configured_admin()`, which is the owner list in `bot/config.py:OWNER_IDS` plus the `admin_ids` config row. `@is_admin()` additionally accepts a guild administrator; `@is_bot_dev()` does not, so host-level commands like `/update` stay owners-only.

### messaging

`commands.Context.send` and `.reply` are monkeypatched at import time in `bot/commands/__init__.py` to fall back to a DM on `discord.Forbidden`. Two consequences that break code written against stock discord.py:

- they can return `None` — a fallback that also fails returns nothing
- the fallback path drops `reference` and `mention_author`, so a "reply" can silently become a plain DM

Bans are checked in three separate places (`@client.check`, `tree.interaction_check`, and `on_message`) against a file list (`bot/banned_users.txt`, via `bot/bans.py`), with the `banned_users` table as fallback. A new entry point needs its own check.

### self-updating

`/update` (bot devs only) writes `update_snapshot.txt` with the current HEAD, runs `git pull --autostash`, runs the syntax check, then `os.execv`s itself. On failure it `git reset --hard`s back to the snapshot.

`on_ready` in `bot/events.py` looks for a leftover `update_snapshot.txt` and treats it as a crash mid-update, reverting and restarting. Anything you change in startup behaviour has to survive being re-exec'd with the same argv.

### ai

`/chat`, `/internet search`, and `/tts` in `bot/commands/utility.py` talk to Gemini through its **OpenAI-compatible endpoint** (`generativelanguage.googleapis.com/v1beta/openai/chat/completions`) with `API_KEY` as a bearer token, model `gemini-3.1-flash-lite`.

`/chat` gives the model exactly one tool, `ignore`. It used to have an `execute` tool that ran allowlisted binaries; that was removed because the allowlist only checked the first token while the command went to a shell, so `ffmpeg -h && <anything>` was arbitrary code execution on the host. **Don't add a subprocess path back into `/chat`.**

TTS goes through `g4f` with an ordered provider fallback (OpenAIFM → Gemini) because OpenAIFM gets rate-limited. Keep the list-of-providers loop shape when adding one.

## conventions

- format coin amounts with `_s()` from `bot/commands/__init__.py` — `k`/`m`/`b` are rounded to one decimal, `t`/`q` are integer-truncated, and anything ≥ 1e18 switches to scientific (`1.234e+19`).
- consume shop items with `take_cheat(user_id, type)` from `bot/commands/shop.py`, not `ACTIVE_CHEATS.pop()` — a bare pop burns whatever unrelated item the user had active.
- economy games settle in ~20 distinct places across `economy.py` and the View classes. A new game means a new settle site, and the house/rake/tax hooks have to be added by hand.
