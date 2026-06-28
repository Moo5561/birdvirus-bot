## Summary
- Total lines: 116
- Total functions: 5
- Total exported symbols: 3 (`token`, `apikey`, `client`)
- Top-level variables:
  - `token`: Read by global script.
  - `apikey`: Read by `chat`.
  - `client`: Read/mutated by `on_ready`, `ping_cmd`, `chat`, `join`, `leave` (as decorators), and read by `on_ready` and `chat` (as `client.user`).
  - `intents`: Read by global script.

## Function Registry
| Name | Line Range | Responsibility | Target Module | Shared State Dependencies |
|---|---|---|---|---|
| `on_ready` | 17-19 | Ready event handler | `bot/events.py` | `client` |
| `ping_cmd` | 21-23 | Ping command | `bot/commands.py` | `client` |
| `chat` | 25-92 | AI chat command | `bot/commands.py` | `client`, `apikey` |
| `join` | 93-108 | Join voice command | `bot/commands.py` | `client` |
| `leave` | 109-115 | Leave voice command | `bot/commands.py` | `client` |

## Module Assignment Plan
- `bot/core.py`
  - Functions: None (Setup script/Client init)
  - Imports: `discord`, `os`, `dotenv`, `discord.ext.commands`, `bot.commands`, `bot.events`
  - Exports: `client`, `run_bot` function (which uses `token`)
- `bot/commands.py`
  - Functions: `ping_cmd`, `chat`, `join`, `leave`, `setup`
  - Imports: `discord.ext.commands`, `aiohttp`, `datetime`, `os`
  - Exports: `setup(client)` function to register commands
- `bot/events.py`
  - Functions: `on_ready`, `setup`
  - Imports: `discord.ext.commands`
  - Exports: `setup(client)` function to register events

## Risk Flags
- `chat` function touches multiple API-related variables and heavily relies on the client state.
- `client` is used globally for decorators (`@client.command`), which requires passing the `client` object to the modules or using Discord.py Cogs. Migrating to Cogs is recommended to avoid circular dependencies when splitting into modules.

## Smoke Test Results
- `python -m py_compile main.py` executed successfully without errors.
- `python -m py_compile bot/*.py` executed successfully without errors.
- Main logic is completely extracted into `bot/` modules, leaving `main.py` as pure orchestration (wiring up commands, events, config, and running the bot client).
- The monolithic structure has been fully dismantled into cohesive modules.
