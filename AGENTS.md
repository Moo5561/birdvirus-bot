# Agent Instructions

the rules that aren't negotiable. `CLAUDE.md` is how the bot is built and where it bites; `DEVELOPMENT.md` is per-subsystem detail. don't restate things from those files here — this one stays short enough that people actually read it.

## personality

be yourself, but be direct. no padding, no "great question", no summarizing back what was just asked. say the thing.

- **don't perform enthusiasm you don't have.** if a request is a bad idea, say so in a sentence and then do it anyway if it's still what was asked.
- **report what actually happened.** if the syntax check failed, paste it. if you skipped part of the task, say which part. "done" means done and verified, not "probably fine".
- **user-facing bot text is a separate voice from yours.** everything the bot says in discord is lowercase and casual, punctuation only where it changes meaning. your messages to the developer are normal prose.

## hard rules

- **db calls block.** `bot/db.py` is synchronous `sqlite3`. every call from command code goes through `await asyncio.to_thread(...)`. no exceptions.
- **register your module.** there are no cogs. a new file in `bot/commands/` must export `setup_<name>(client)` and be imported + called in `bot/commands/__init__.py:setup()`, or it silently does nothing.
- **guard for dms.** `default_allowed_contexts` in `main.py` enables dms, group dms, and user installs globally, so every new command lands there whether you meant it to or not. anything touching `ctx.guild` or `ctx.author.guild_permissions` needs an explicit `ctx.guild is None` check first.
- **don't hand-edit `version.txt`.** a github action rewrites it on every push to `main`.
- **don't commit** `.env`, `cookies.txt`, or `bot.log`. `birdvirus.db` is (unfortunately) tracked already — don't add churn to it on purpose.
- **verify before you claim done:** `python -m py_compile main.py bot/*.py bot/commands/*.py`. there is no test suite; that check plus reading the diff is all you get.
- **keep the diff scoped.** this codebase has a lot of near-duplicate game logic. don't opportunistically refactor unrelated files.

## the traps that actually cost time

each of these has burned someone. details in `CLAUDE.md`.

- `ctx.send` / `ctx.reply` are monkeypatched and **can return `None`** — don't assume you got a `Message` back.
- format coin amounts with `_s()`, never raw. format shop-item consumption with `take_cheat()`, never `ACTIVE_CHEATS.pop()`.
- test for the nightly bot with `is_nightly(ctx.bot)`, never a fresh id literal.
- never add a subprocess path back into `/chat`. it was arbitrary code execution the first time.
