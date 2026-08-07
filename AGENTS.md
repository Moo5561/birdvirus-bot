# Agent Instructions


`CLAUDE.md` has the full architecture rundown, `DEVELOPMENT.md` has per-subsystem detail. this file is the short version plus the rules that aren't negotiable.

## personality

- Whatever you are like lmao

## hard rules

- **db calls block.** `bot/db.py` is synchronous `sqlite3`. every call from command code goes through `await asyncio.to_thread(...)`. no exceptions.
- **register your module.** there are no cogs. a new file in `bot/commands/` must export `setup_<name>(client)` and be imported + called in `bot/commands/__init__.py:setup()`, or it silently does nothing.
- **don't hand-edit `version.txt`.** a github action rewrites it on every push to `main`.
- **don't commit** `.env`, `cookies.txt`, or `bot.log`. `birdvirus.db` is (unfortunately) tracked already — don't add churn to it on purpose.
- **verify before you claim done:** `python -m py_compile main.py bot/*.py bot/commands/*.py`. there is no test suite; that check plus reading the diff is all you get.
- **keep the diff scoped.** this codebase has a lot of near-duplicate game logic. don't opportunistically refactor unrelated files.

## codebase context

- **framework**: `discord.py`, hybrid commands only (`@client.hybrid_command` / `@client.hybrid_group`) so slash and prefix both work.
- **contexts**: `default_allowed_contexts` in `main.py` enables dms, group dms, and user installs globally. new commands land there automatically, so guard anything guild-dependent with an explicit `ctx.guild is None` check.
- **shared state**: `audio_queues`, `voice_joiners`, and `in_game` live in `bot/commands/__init__.py`, not in the modules that mutate them. use `game_lock(ctx)` / `game_unlock(ctx)` around anything interactive so one user can't run two games at once.
- **messages**: `ctx.send` and `ctx.reply` are monkeypatched in `bot/commands/__init__.py` to fall back to dms on `discord.Forbidden`. they can return `None`, and the fallback drops `reference`/`mention_author` — don't assume you got a `Message` back.
- **admin checks**: `@is_admin()` for privileged commands, `@is_bot_dev()` for anything that touches the host machine (restart, update, shell-adjacent). both check `OWNER_IDS` from `bot/config.py` and the `admin_ids` config row; only `is_admin` also accepts a guild administrator. guard `ctx.author.guild_permissions` with `ctx.guild is not None` — it doesn't exist in dms.
- **numbers**: format coin amounts with `_s()` from `bot/commands/__init__.py` (`1.2k`, `5.7m`, scientific past a quadrillion).
- **audio**: custom queue in `bot/commands/voice.py`, files in `mp3/`, `PCMVolumeTransformer` at 0.60 (1.0 for `badapple_max`). `queue_audio()` takes both local paths and yt-dlp urls.
- **ai**: `/chat`, `/internet search`, and `/tts` in `bot/commands/utility.py` hit gemini through its openai-compatible endpoint with `API_KEY` as a bearer token. tts uses `g4f` with an ordered provider fallback (OpenAIFM → Gemini) because OpenAIFM gets rate-limited — keep that loop shape if you add a provider.
- **bot ids**: main bot is `1518310857598308433`. the nightly/dev bot is `bot/config.py:NIGHTLY_BOT_ID` — `ht!` prefix, writes to `birdvirus_nightly.db`, and bypasses economy balance checks. test it with `is_nightly(ctx.bot)`, don't paste the literal again.
- **shop items**: consume an active cheat with `take_cheat(user_id, type)` from `bot/commands/shop.py`. `ACTIVE_CHEATS.pop()` throws away whatever unrelated item the user had active.
- **self-update**: `/update` snapshots HEAD to `update_snapshot.txt`, pulls, syntax-checks, then `os.execv`s the process. `on_ready` reverts if it finds a stale snapshot. anything you change in startup has to survive being re-exec'd with the same argv.
