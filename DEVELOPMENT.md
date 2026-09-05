# development

Per-subsystem detail. `AGENTS.md` has the rules, `CLAUDE.md` has the architecture and the traps — this file is what each subsystem actually does.

## layout

```
birdvirus-bot/
├── main.py                     # entry point, prefix logic, bot-to-bot invocation override
├── setup.sh                    # venv + deps + playwright chromium
├── requirements.txt
├── version.txt                 # written by CI, don't hand-edit
├── bot/
│   ├── config.py               # .env loading, OWNER_IDS, NIGHTLY_BOT_ID
│   ├── db.py                   # synchronous sqlite3 — every table below
│   ├── bans.py                 # file-based ban list (banned_users.txt)
│   ├── events.py               # on_ready, ban checks, "67" trigger, error handler
│   └── commands/
│       ├── __init__.py         # shared state, send/reply monkeypatch, permission checks, _s(), setup()
│       ├── economy.py          # pure group, banking, loans/debt, house, leaderboard
│       ├── utility.py          # ping, gif, version, vote, chat, tts, say, eatbomb, numbairy, internet
│       ├── voice.py            # vc group, play/stop, bad apple, queue_audio(), voice_announcer task
│       ├── admin.py            # ban/unban, view, clear, property, ec groups
│       ├── job.py              # job group + 6 minigame views
│       ├── shop.py             # shop/buy/inv/use + item effects, ACTIVE_CHEATS
│       ├── stocks.py           # stock group, market loop, matplotlib chart
│       ├── update.py           # /update, syntax_check()
│       ├── blackjack.py        # BlackjackView, draw_card, calculate_hand
│       ├── horserace.py        # HorseRaceView
│       ├── catrace.py          # CatRaceView
│       ├── cars.py, crash.py, crypto.py, pet.py
├── mp3/                        # audio assets, and the scratch dir for tts//play downloads
├── site/                       # public github pages site: landing redirect, privacy, terms
├── birdvirus-cloud/            # separate node/express service, not imported by the bot
├── docs/images/                # readme screenshots and artwork
├── extras/                     # standalone odds and ends, not part of the bot
└── .github/workflows/          # pages deploy + version.txt bump
```

`birdvirus.db` is not in this tree on purpose: it is runtime state, gitignored, and
created by `init_db()` on first boot.

Everything under `mp3/` that matches `temp_*` or `tts_*` is scratch written at
runtime and ignored by git — only the committed `.mp3` assets are real files.

## database tables

`init_db()` creates twelve: `economy`, `config`, `properties`, `say_logs`, `chat_resets`, `user_jobs`, `user_items`, `banned_users`, `gamble_streaks`, `gamble_daily`, `stock_state`, `stock_holdings`.

## economy

- users start with 100 coins holding, 0 bank. `/deposit` and `/withdraw` move between the two.
- the house wallet is a single running integer in `config`, adjusted by `update_house()`. There is no history table, so there is no way to reconstruct what it was at a given time.
- a house rake is taken from winning bets; tax and streak bonuses adjust it further. Every game settles in its own place — see the note in `CLAUDE.md:conventions`.
- `/loan` takes debt at 10% interest, `/repay` pays it down, `/debt` reports it. Admins have `/ec debtforgive` and `/ec debtlist`.
- `/ec taxrate` and `/ec taxinfo` control the tax; `/pure insurance`, `/pure house`, `/pure houseclaim`, and `/pure bailout` are the house-side commands.
- the nightly bot bypasses balance checks entirely and has effectively infinite coins.

## jobs

Defined in the `JOBS` dict in `bot/commands/job.py`:

| job | minigame |
|-----|----------|
| janitor | click the poop button (9 tiles) |
| chef | select ingredients in recipe order |
| developer | pick the syntactically correct snippet |
| hacker | crack a 3-digit pin, mastermind-style |
| miner | 5×5 grid, find diamond, avoid lava |
| thief | push your luck through 4 escalating stages |

Each job has base pay scaling with level, a cooldown in minutes, a required overall level to apply, random events at 15% per shift, and a speed bonus measured against a par time. XP per level is `level * 100`.

## shop

Time-gated on UTC. Normal stock is available `06:00`–`00:00` (`SHOP_OPEN`/`SHOP_CLOSE`); the illegal vendor only appears `18:00`–`20:00` (`ILLEGAL_START`/`ILLEGAL_END`). `/setshop` forces open/closed or reverts to time-based, `/setillegal` moves the illegal window.

Items come from `NORMAL_ITEMS` and `ILLEGAL_ITEMS`, merged into `ALL_ITEMS` by name. `ITEM_EFFECTS` maps an item to the cheat it activates. Active cheats live in the in-memory `ACTIVE_CHEATS` dict — **consume them with `take_cheat(user_id, type)`**, since a bare `ACTIVE_CHEATS.pop()` discards whatever unrelated item the user had running. Because the dict is in memory, active cheats do not survive a restart.

## stocks

Ten tickers in the `STOCKS` list, each with a base price and a volatility factor. `market_loop` is a `tasks.loop(seconds=12.0)` started from an `on_ready` listener, which seeds any missing ticker via `ensure_stock()` first.

Most tickers drift synthetically through `drift_ticker()`. `RBLX` is flagged `"real": True` and instead pulls the live Roblox price from the Yahoo Finance chart API over `aiohttp`, throttled to one fetch per `REAL_FETCH_COOLDOWN` (45s) regardless of the 12s loop.

`HIST_LEN` (12) points of history are kept per ticker, which is what `/stock market` renders as a matplotlib per-ticker subplot chart and as inline sparklines.

## audio

- `queue_audio()` in `bot/commands/voice.py` accepts both local `mp3/` paths and remote URLs via yt-dlp.
- volume is `PCMVolumeTransformer` at 0.60, except files named `badapple_max` at 1.0.
- `voice_announcer` is a background task that plays a random bird sound in every connected vc every 15 seconds, at 80% chance.
- on-demand sounds are `/vc bird`, `/vc fart`, and `/vc droid`.
- `/vc join`/`/vc leave` also exist as bare prefix-only `join`/`leave` commands.

## properties

- `/property register <channel>` sets where property threads get created.
- `/property buy` creates either a private thread (50 coins) or a private vc with a custom role (100 coins).
- `/property invite` and `/property kick` manage vc property access; `/property remove` is admin-only.
- tracked in the `properties` table.

## bans

Two layers, both checked: `bot/banned_users.txt` (read through `bans.py`) and the `banned_users` table as fallback. Enforced in three places — see `CLAUDE.md:messaging`.

## error handling

- `UserBanned` (`bot/events.py`) is silently swallowed.
- `CheckFailure` / `MissingPermissions` → "you don't have permission to do that".
- `CommandOnCooldown` → the remaining cooldown.
- everything else is printed to console and not surfaced to users, except API errors in `/chat`.
