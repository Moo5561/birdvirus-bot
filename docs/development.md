# development guide

## architecture
the bot was recently refactored from a massive monolith into a clean, modular package structure:
- `main.py`: orchestration, dynamic prefix checking, and client initialization.
- `bot/config.py`: loads environment variables.
- `bot/db.py`: sqlite3 database interactions (economy, properties, logs).
- `bot/events.py`: global event listeners (`on_ready`, `on_message`, `on_command_error`).
- `bot/commands/`: the core command modules.
  - `__init__.py`: global monkeypatches (dm fallback), `is_admin` decorator, and module registry.
  - `admin.py`: moderation and property management.
  - `blackjack.py`: blackjack logic and UI views.
  - `economy.py`: gambling, banking, and fishing.
  - `utility.py`: ping, version, ai chat, tts, and web search.
  - `voice.py`: audio queueing, streaming, and vc controls.

## adding commands
all commands use `@client.hybrid_command` or `@client.hybrid_group` so they work as both slash commands and prefix commands.

if you add a new file to `bot/commands/`, make sure to import it and register its setup function inside `bot/commands/__init__.py`.

## database
we use a local `birdvirus.db` sqlite3 database. if you need to add tables, update the `init_db()` function inside `bot/db.py`. all db calls must be wrapped in `asyncio.to_thread` from the commands.

## contributing
- test your code locally before pushing.
- run `python -m py_compile main.py bot/*.py bot/commands/*.py` to check for syntax errors.
- don't commit your `.env` or `cookies.txt` files.