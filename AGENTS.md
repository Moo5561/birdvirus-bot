# Agent Instructions

If you are an AI agent working on this repository, follow these rules.

## Communication

- Use normal capitalization and clear, natural language.
- Keep responses concise, casual, and direct.
- Be respectful and helpful, even when the user is frustrated or joking.
- Summarize completed work and relevant validation without forced catchphrases.

## codebase context
- **framework**: `discord.py` with hybrid commands.
- **audio**: we use a custom audio queueing system in `bot/commands/voice.py`. all audio files are stored in the `mp3/` directory. we use `PCMVolumeTransformer` to manage audio levels.
- **admin checks**: use the `@is_admin()` decorator from `bot.commands` for any privileged commands. it checks the database and a hardcoded list of owner IDs.
- **messages**: `ctx.send` and `ctx.reply` have been monkeypatched in `bot/commands/__init__.py` to automatically fallback to DMs if the bot gets a `discord.Forbidden` error.
- **db**: `sqlite3` is used in `bot/db.py`. all database calls from commands MUST be wrapped in `await asyncio.to_thread(...)` to prevent blocking the async event loop.
- **bot ids**: the main bot is `1518310857598308433`. the nightly/dev bot is `1522117141090799697`. the nightly bot gets `ht!` as a prefix and bypasses economy balance checks automatically.
