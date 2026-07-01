# Refactor Map for bot/commands.py

## Summary
- Total lines: 1111
- Total functions: ~35
- Total exported symbols: `setup(client)`
- Top-level variables:
  - `audio_queues`: Map of guild ID to list of pending audio files (reads and writes in `setup`, `vc_leave`, `on_message`).
  - `voice_joiners`: Map of guild ID to user ID of the joiner (reads and writes in `setup`, `vc_join`, `vc_leave`).

## Function Registry
| Name | Line Range | Responsibility | Target Module | Shared State Dependencies |
|---|---|---|---|---|
| `draw_card` | 13-16 | Draws a random card | `bot/commands/blackjack.py` | None |
| `calculate_hand` | 18-34 | Calculates card hand value | `bot/commands/blackjack.py` | None |
| `is_admin` | 36-57 | Checks if user is bot admin | `bot/commands/admin.py` | None |
| `BlackjackView` | 59-162 | UI view for playing blackjack | `bot/commands/blackjack.py` | `audio_queues` |
| `voice_announcer` | 184-193 | Plays random bird sounds in voice channels | `bot/commands/voice.py` | `audio_queues` |
| `vc_group` | 370-373 | Group decorator for voice channel commands | `bot/commands/voice.py` | None |
| `vc_join` | 375-390 | Joins bot to user's voice channel | `bot/commands/voice.py` | `voice_joiners` |
| `vc_leave` | 392-427 | Disconnects bot from voice channel | `bot/commands/voice.py` | `voice_joiners`, `audio_queues` |
| `vc_stop` | 429-441 | Stops current audio playback and clears queue | `bot/commands/voice.py` | `audio_queues` |
| `vc_bird` | 443-458 | Plays bird sound in voice channel on-demand | `bot/commands/voice.py` | None |
| `ping_cmd` | 212-215 | Basic ping response command | `bot/commands/utility.py` | None |
| `gif_cmd` | 217-241 | Sends a random tuff gif | `bot/commands/utility.py` | None |
| `bad_apple` | 243-255 | Queues bad apple audio in voice channel | `bot/commands/voice.py` | `audio_queues` |
| `chat_reset` | 364-369 | Wipes AI chat context for channel | `bot/commands/utility.py` | None |
| `chat` | 244-362 | AI chatbot query utilizing Gemini | `bot/commands/utility.py` | None |
| `pure_group` | 448-450 | Group decorator for gambling/economy commands | `bot/commands/economy.py` | None |
| `pure_chance` | 452-472 | Double-or-nothing coin flip | `bot/commands/economy.py` | None |
| `pure_blackjack` | 474-504 | Plays interactive blackjack game | `bot/commands/economy.py` | None |
| `pure_slots` | 506-586 | Spin the slot machine | `bot/commands/economy.py` | None |
| `pure_roulette` | 588-692 | Spin the roulette wheel | `bot/commands/economy.py` | None |
| `pure_plinko` | 694-770 | Play plinko | `bot/commands/economy.py` | None |
| `beg` | 785-810 | Beg for free coins | `bot/commands/economy.py` | None |
| `fish` | 811-840 | Go fishing for coins | `bot/commands/economy.py` | None |
| `balance` | 889-920 | View cash and bank balance | `bot/commands/economy.py` | None |
| `ec_group` | 921-925 | Group decorator for economy admin commands | `bot/commands/admin.py` | None |
| `ec_emoji` | 927-933 | Sets custom economy emoji | `bot/commands/admin.py` | None |
| `ec_reset` | 935-943 | Resets user balance | `bot/commands/admin.py` | None |
| `ec_set` | 945-957 | Sets user balance | `bot/commands/admin.py` | None |
| `internet_group` | 958-961 | Group decorator for internet utilities | `bot/commands/utility.py` | None |
| `internet_get` | 963-965 | Fun dummy internet command | `bot/commands/utility.py` | None |
| `internet_search` | 967-1015 | Searches DuckDuckGo via Playwright | `bot/commands/utility.py` | None |
| `eat_bomb` | 1016-1034 | Eat a consumable bomb | `bot/commands/utility.py` | None |

## Module Assignment Plan
We will surgically split `bot/commands.py` into smaller files under a package `bot/commands/`:
- `bot/commands/__init__.py`: Handlers orchestration and registers all command sub-modules.
- `bot/commands/blackjack.py`: Blackjack UI View and card mechanics.
- `bot/commands/voice.py`: Voice announcer loop, `/vc` group (join, leave, stop, bird, bad apple).
- `bot/commands/economy.py`: `/pure` group (chance, blackjack, slots, roulette, plinko), beg, fish, balance.
- `bot/commands/admin.py`: is_admin check, `/view` group, `/clear` group, `/property` group, `/ec` group.
- `bot/commands/utility.py`: ping, version, gif, chat, chat_reset, internet_group, eatbomb.

## Risk Flags
- `is_admin` is required across both `economy.py` and `admin.py`. We will export it from a shared utility module or define it in `bot/commands/__init__.py`.
- `audio_queues` and `voice_joiners` must be accessible globally so both the event listeners (`bot/events.py`) and command handlers can read/write them.
