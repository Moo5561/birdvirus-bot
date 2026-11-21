![birdvirus bot](docs/images/birdvirusbot.png)

# birdvirus-bot

the official discord bot for the birdvirus community. multipurpose economy, audio, and ai chat bot built with discord.py.

## features

- **economy** — blackjack, roulette, slots, plinko, insaneroll, horse and cat racing, birdvirus guess game, fishing, begging. full banking with deposits, withdrawals, loans, debt, and a house wallet that takes a rake.
- **stock market** — ten tradeable tickers with live price drift and a matplotlib chart. one of them tracks the real roblox share price.
- **shop** — buy items and consumables from a time-gated storefront, plus an illegal vendor that only shows up in a two-hour window.
- **jobs** — 6 jobs (janitor, chef, developer, hacker, miner, thief), each with its own minigame, levels, xp, promotions, and random events.
- **voice & audio** — queue system for local files and youtube (via yt-dlp). random fart sounds play on their own in vc. text-to-speech support.
- **properties** — buy private threads or voice channels with custom roles, with an invite/kick system.
- **ai chat** — `/chat` talks to you with per-channel context memory, plus `/internet search`.
- **admin** — ban/unban, log viewing, economy and tax management, configurable coin emoji.

## setup

1. install dependencies:
   ```bash
   ./setup.sh
   ```
   or manually: `pip install -r requirements.txt`
2. install ffmpeg and add it to your system path.
3. copy `.env.example` to `.env` and add your keys:
   - `KEY` — discord bot token
   - `API_KEY` — gemini api key (for `/chat`, `/internet search`, `/tts`)
4. (optional) place a `cookies.txt` in netscape format for yt-dlp youtube access.

## running

```bash
python main.py --host "your_name"
```

`--host` is required. it only sets the activity status shown on discord.

## self-hosting notes

- the sqlite database is auto-created on first run. its path comes from `BOT_DB_PATH` and defaults to `birdvirus.db`. it is not tracked in git — a fresh clone starts with an empty economy.
- audio files go in the `mp3/` directory.
- the bot works out which identity it is from the token. the nightly/dev bot (id in `bot/config.py`) uses the `ht!` prefix, writes to a separate database, and bypasses economy checks.
- bot owners are listed in `bot/config.py:OWNER_IDS`. additional admins can be added at runtime through the `admin_ids` config row.

## commands

slash commands work in servers, dms, and group dms unless they require a server, like voice, property, and leaderboard commands. for group dms or dms with other users, add the app to your discord account. self-hosts need both server install and user install enabled in the discord developer portal and must restart the bot to sync the commands.

prefix commands use `%` for the main bot and `ht!` for nightly wherever the bot can receive messages.

| category | commands |
|----------|----------|
| gambling | `/pure chance`, `/pure blackjack`, `/pure slots`, `/pure roulette`, `/pure insaneroll`, `/pure birdvirus`, `/pure plinko`, `/pure plinkohard`, `/pure horse`, `/pure catrace` |
| economy | `/balance`, `/deposit`, `/withdraw`, `/beg`, `/fish`, `/leaderboard`, `/loan`, `/repay`, `/debt` |
| house | `/pure house`, `/pure houseclaim`, `/pure insurance`, `/pure bailout` |
| stocks | `/stock market`, `/stock buy`, `/stock sell`, `/stock portfolio` |
| shop | `/shop`, `/buy`, `/inv`, `/use` |
| jobs | `/job list`, `/job info`, `/job apply`, `/job work`, `/job quit`, `/job beg` |
| voice | `/vc join`, `/vc leave`, `/vc stop`, `/vc bird`, `/vc fart`, `/vc droid`, `/play`, `/stop`, `/bad apple` |
| properties | `/property register`, `/property buy`, `/property remove`, `/property invite`, `/property kick` |
| utility | `/ping`, `/gif`, `/httpbird`, `/version`, `/vote`, `/chat`, `/chat_reset`, `/say`, `/eatbomb`, `/tts`, `/numbairy`, `/internet search` |
| admin | `/ban`, `/unban`, `/view say`, `/view logs`, `/clear saylist`, `/giveitem`, `/removeitem`, `/setshop`, `/setillegal` |
| economy admin | `/ec emoji`, `/ec reset`, `/ec set`, `/ec setbank`, `/ec add`, `/ec taxrate`, `/ec taxinfo`, `/ec debtforgive`, `/ec debtlist` |
| bot devs | `/update` |

open `/httpbird` and pick a status from the `code` suggestions, or search by number or name. `%httpbird 404` still works. 22 codes have their own photo; other recognized codes use the birdvirus crow.
the photos were reframed and resized. their [credits and licenses](bot/assets/httpbird/credits.json) also appear under each card; share-alike cards retain the indicated license.

## contributing

`AGENTS.md` has the rules, `CLAUDE.md` has the architecture, and `DEVELOPMENT.md` has per-subsystem detail. verify syntax and run the regression tests with:

```bash
python -m py_compile main.py bot/*.py bot/commands/*.py
python -m unittest discover -s tests -p "*_test.py"
```

github actions runs both checks on every push and pull request.

after installing the bot dependencies, verify the discord sync payload without logging in:

```bash
python -m unittest discover -s tests -p "discord_registration_smoke.py"
```
