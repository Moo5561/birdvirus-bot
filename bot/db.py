import json
import sqlite3
import os
import threading
from datetime import datetime, timedelta

DB_PATH = os.environ.get("BOT_DB_PATH", "birdvirus.db")


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, OverflowError):
        return default


def _is_corrupt(val):
    """true if a balance/bank/debt value is mangled beyond parsing."""
    if val is None:
        return False
    try:
        int(val)
        return False
    except (ValueError, OverflowError):
        return True

# thread-local persistent connections. each executor thread reuses one
# connection instead of opening/closing per call — huge win under load.
# WAL lets readers run concurrently with the single writer.
_local = threading.local()


def _conn():
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=30000")
        _local.conn = c
    return c


def _apply_migrations(cursor):
    # add bank column to existing dbs
    try:
        cursor.execute("ALTER TABLE economy ADD COLUMN bank INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # add debt column to existing dbs
    for _attempt in range(3):
        try:
            cursor.execute("ALTER TABLE economy ADD COLUMN debt TEXT DEFAULT '0'")
            break
        except sqlite3.OperationalError:
            pass


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    cursor = conn.cursor()

    # say logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS say_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            message_content TEXT,
            timestamp TEXT
        )
    """)

    # economy table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS economy (
            user_id INTEGER PRIMARY KEY,
            balance TEXT DEFAULT '100',
            bank TEXT DEFAULT '0',
            debt TEXT DEFAULT '0'
        )
    """)

    _apply_migrations(cursor)

    # config table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # properties table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            thread_id INTEGER PRIMARY KEY,
            owner_id INTEGER,
            name TEXT
        )
    """)

    # chat resets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_resets (
            channel_id INTEGER PRIMARY KEY,
            reset_at TEXT
        )
    """)

    # user jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_jobs (
            user_id INTEGER PRIMARY KEY,
            job_name TEXT,
            job_xp INTEGER DEFAULT 0,
            job_level INTEGER DEFAULT 1,
            shifts_completed INTEGER DEFAULT 0,
            last_work_time TEXT
        )
    """)

    # banned users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY
        )
    """)

    # user items table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_items (
            user_id INTEGER,
            item TEXT,
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, item)
        )
    """)

    # daily gambling streak table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gamble_streaks (
            user_id INTEGER PRIMARY KEY,
            last_day TEXT,
            streak INTEGER DEFAULT 0
        )
    """)

    # daily gambling net result (for loss insurance)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gamble_daily (
            user_id INTEGER,
            day TEXT,
            net INTEGER DEFAULT 0,
            insurance_claimed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, day)
        )
    """)

    # stock market state (one row per ticker)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_state (
            ticker TEXT PRIMARY KEY,
            price INTEGER DEFAULT 10000,
            hist TEXT DEFAULT '[]',
            updated_at TEXT
        )
    """)

    # user stock holdings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_holdings (
            user_id INTEGER,
            ticker TEXT,
            shares INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, ticker)
        )
    """)

    # crypto miner wallets
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crypto_wallets (
            user_id INTEGER PRIMARY KEY,
            balance TEXT DEFAULT '0',
            rig_level INTEGER DEFAULT 1,
            mined_total TEXT DEFAULT '0',
            last_mine TEXT
        )
    """)

    # 宠物表 — 每个玩家的宠物 (pet system, one pet per player)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pets (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            species TEXT,
            hunger INTEGER DEFAULT 50,
            mood INTEGER DEFAULT 50,
            energy INTEGER DEFAULT 50,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            fed_total INTEGER DEFAULT 0,
            last_fed TEXT,
            last_played TEXT
        )
    """)

    # user cars garage
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_cars (
            user_id INTEGER,
            car_key TEXT,
            name TEXT,
            tier INTEGER DEFAULT 1,
            mileage INTEGER DEFAULT 0,
            wear INTEGER DEFAULT 0,
            earned_total TEXT DEFAULT '0',
            last_drive TEXT,
            PRIMARY KEY (user_id, car_key)
        )
    """)

    conn.commit()
    conn.close()


# Ban Functions
def ban_user(user_id: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (user_id,)
    )
    conn.commit()
    cursor.close()


def unban_user(user_id: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
    conn.commit()
    cursor.close()


def get_banned_users() -> set:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM banned_users")
    rows = cursor.fetchall()
    cursor.close()
    return {row[0] for row in rows}


# Chat Reset Functions
def set_chat_reset(channel_id: int, reset_at: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_resets (channel_id, reset_at) VALUES (?, ?) ON CONFLICT(channel_id) DO UPDATE SET reset_at = ?",
        (channel_id, reset_at, reset_at),
    )
    conn.commit()
    cursor.close()


def get_chat_reset(channel_id: int) -> str:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reset_at FROM chat_resets WHERE channel_id = ?", (channel_id,)
    )
    row = cursor.fetchone()
    cursor.close()
    return row[0] if row else None


# Say Logs Functions
def log_say(user_id: int, user_name: str, message: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO say_logs (user_id, user_name, message_content, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, user_name, message, datetime.utcnow().isoformat()),
    )
    conn.commit()
    cursor.close()


def get_say_logs(limit: int = 20):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_name, user_id, message_content, timestamp FROM say_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows


def clear_say_logs():
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM say_logs")
    conn.commit()
    cursor.close()


# Economy Functions
def get_balances(user_id: int) -> tuple[int, int, int]:
    conn = _conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance, bank, debt FROM economy WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    except sqlite3.OperationalError:
        _apply_migrations(cursor)
        conn.commit()
        cursor.execute("SELECT balance, bank, debt FROM economy WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', '0', '0')",
            (user_id,),
        )
        conn.commit()
        balance, bank, debt = 100, 0, 0
    else:
        balance, bank = _safe_int(row[0]), _safe_int(row[1])
        debt = _safe_int(row[2])
        if _is_corrupt(row[0]) or _is_corrupt(row[1]) or _is_corrupt(row[2]):
            cursor.execute(
                "UPDATE economy SET balance = '0', bank = '0', debt = '0' WHERE user_id = ?",
                (user_id,),
            )
            conn.commit()
            balance, bank, debt = 0, 0, 0
    cursor.close()
    return balance, bank, debt


def get_balance(user_id: int) -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "INSERT INTO economy (user_id, balance) VALUES (?, '100')", (user_id,)
        )
        conn.commit()
        balance = 100
    else:
        if _is_corrupt(row[0]):
            cursor.execute("UPDATE economy SET balance = '0' WHERE user_id = ?", (user_id,))
            conn.commit()
            balance = 0
        else:
            balance = _safe_int(row[0])
    cursor.close()
    return balance


def set_balance(user_id: int, amount: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, ?, '0', '0') ON CONFLICT(user_id) DO UPDATE SET balance = ?",
        (user_id, str(amount), str(amount)),
    )
    conn.commit()
    cursor.close()


def set_bank(user_id: int, amount: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', ?, '0') ON CONFLICT(user_id) DO UPDATE SET bank = ?",
        (user_id, str(amount), str(amount)),
    )
    conn.commit()
    cursor.close()


def update_balance(user_id: int, change: int) -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO economy (user_id, balance, bank, debt)
        VALUES (?, ?, '0', '0')
        ON CONFLICT(user_id) DO UPDATE SET balance = CAST(CAST(balance AS INTEGER) + ? AS TEXT)
        """,
        (user_id, str(100 + change), change),
    )
    conn.commit()
    cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    new_balance = _safe_int(row[0]) if row else 0
    cursor.close()
    return new_balance


def update_bank(user_id: int, change: int) -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO economy (user_id, balance, bank, debt)
        VALUES (?, '100', ?, '0')
        ON CONFLICT(user_id) DO UPDATE SET bank = CAST(CAST(bank AS INTEGER) + ? AS TEXT)
        """,
        (user_id, str(change), change),
    )
    conn.commit()
    cursor.execute("SELECT bank FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    new_bank = _safe_int(row[0]) if row else 0
    cursor.close()
    return new_bank

def get_debt(user_id: int) -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT debt FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', '0', '0')", (user_id,))
        conn.commit()
        cursor.close()
        return 0
    debt = _safe_int(row[0])
    cursor.close()
    return debt

def set_debt(user_id: int, amount: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', '0', ?) ON CONFLICT(user_id) DO UPDATE SET debt = ?",
        (user_id, str(amount), str(amount)),
    )
    conn.commit()
    cursor.close()

def update_debt(user_id: int, change: int) -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO economy (user_id, balance, bank, debt)
        VALUES (?, '100', '0', ?)
        ON CONFLICT(user_id) DO UPDATE SET debt = CAST(max(CAST(debt AS INTEGER) + ?, 0) AS TEXT)
        """,
        (user_id, str(max(0, change)), change),
    )
    conn.commit()
    cursor.execute("SELECT debt FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    new_debt = _safe_int(row[0]) if row else 0
    cursor.close()
    return new_debt

def get_all_balances() -> list[dict]:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance, bank, debt FROM economy ORDER BY (CAST(balance AS INTEGER) + CAST(bank AS INTEGER) - CAST(debt AS INTEGER)) DESC")
    rows = cursor.fetchall()
    cursor.close()
    return [{"user_id": row[0], "balance": _safe_int(row[1]), "bank": _safe_int(row[2]), "debt": _safe_int(row[3])} for row in rows]

def get_all_debts() -> list[dict]:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, debt, balance, bank FROM economy WHERE CAST(debt AS INTEGER) > 0 ORDER BY CAST(debt AS INTEGER) DESC")
    rows = cursor.fetchall()
    cursor.close()
    return [{"user_id": row[0], "debt": _safe_int(row[1]), "balance": _safe_int(row[2]), "bank": _safe_int(row[3])} for row in rows]


# Config Functions (Emoji, Properties channel, etc)
#
# config rows are read constantly (coin_emoji alone is read on nearly every
# command) and written almost never, so reads are cached process-wide. dict
# get/set are atomic under the GIL, so no lock is needed across executor
# threads. every writer must invalidate — see _invalidate_config.
_config_cache = {}
_MISSING = object()  # distinguishes "not cached" from "cached as absent"


def _invalidate_config(key: str):
    _config_cache.pop(key, None)


def get_config(key: str, default: str = None) -> str:
    cached = _config_cache.get(key, _MISSING)
    if cached is not _MISSING:
        return cached if cached is not None else default

    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    cursor.close()
    value = row[0] if row else None
    _config_cache[key] = value
    return value if value is not None else default


def set_config(key: str, value: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, value, value),
    )
    conn.commit()
    cursor.close()
    _config_cache[key] = value


# House Wallet
def get_house() -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT CAST(value AS INTEGER) FROM config WHERE key = 'house_wallet'")
    row = cursor.fetchone()
    cursor.close()
    return _safe_int(row[0]) if row and row[0] else 0


def execute(query: str, params: tuple = ()):
    """run a raw query on the db. used for pings/health checks."""
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def update_house(change: int) -> int:
    """atomically adjust the house wallet balance. returns new balance."""
    conn = _conn()
    cursor = conn.cursor()
    val = str(change)
    cursor.execute(
        "INSERT INTO config (key, value) VALUES ('house_wallet', ?) ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + CAST(? AS INTEGER)",
        (val, val),
    )
    conn.commit()
    # written by raw sql, not set_config — keep the cache honest in case
    # anything ever reads house_wallet through get_config()
    _invalidate_config("house_wallet")
    cursor.execute("SELECT CAST(value AS INTEGER) FROM config WHERE key = 'house_wallet'")
    row = cursor.fetchone()
    new_val = _safe_int(row[0]) if row and row[0] else 0
    cursor.close()
    return new_val


# Properties Functions
def add_property(thread_id: int, owner_id: int, name: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO properties (thread_id, owner_id, name) VALUES (?, ?, ?)",
        (thread_id, owner_id, name),
    )
    conn.commit()
    cursor.close()


def get_property(thread_id: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT owner_id, name FROM properties WHERE thread_id = ?", (thread_id,)
    )
    row = cursor.fetchone()
    cursor.close()
    return row


def update_property_owner(thread_id: int, new_owner_id: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE properties SET owner_id = ? WHERE thread_id = ?",
        (new_owner_id, thread_id),
    )
    conn.commit()
    cursor.close()


def update_property_name(thread_id: int, new_name: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE properties SET name = ? WHERE thread_id = ?", (new_name, thread_id)
    )
    conn.commit()
    cursor.close()


# Job Functions
def get_user_job(user_id: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT job_name, job_xp, job_level, shifts_completed, last_work_time FROM user_jobs WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    if row:
        return {
            "job_name": row[0],
            "job_xp": row[1],
            "job_level": row[2],
            "shifts_completed": row[3],
            "last_work_time": row[4],
        }
    return None


def set_user_job(user_id: int, job_name: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO user_jobs (user_id, job_name, job_xp, job_level, shifts_completed, last_work_time) 
        VALUES (?, ?, 0, 1, 0, NULL) 
        ON CONFLICT(user_id) DO UPDATE SET job_name = ?, job_xp = 0, job_level = 1, shifts_completed = 0, last_work_time = NULL
    """,
        (user_id, job_name, job_name),
    )
    conn.commit()
    cursor.close()


def remove_user_job(user_id: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_jobs WHERE user_id = ?", (user_id,))
    conn.commit()
    cursor.close()


def update_job_progress(user_id: int, xp_gain: int, time_str: str):
    conn = _conn()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT job_xp, job_level, shifts_completed FROM user_jobs WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        return False, 0

    current_xp, level, shifts = row
    new_xp = current_xp + xp_gain
    shifts += 1

    level_up = False
    xp_needed = level * 100
    if new_xp >= xp_needed:
        new_xp -= xp_needed
        level += 1
        level_up = True

    cursor.execute(
        """
        UPDATE user_jobs 
        SET job_xp = ?, job_level = ?, shifts_completed = ?, last_work_time = ? 
        WHERE user_id = ?
    """,
        (new_xp, level, shifts, time_str, user_id),
    )

    conn.commit()
    cursor.close()
    return level_up, level


def update_job_time(user_id: int, time_str: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_jobs SET last_work_time = ? WHERE user_id = ?", (time_str, user_id)
    )
    conn.commit()
    cursor.close()


# User Items Functions
def add_item(user_id: int, item: str, quantity: int = 1):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_items (user_id, item, quantity) VALUES (?, ?, ?) ON CONFLICT(user_id, item) DO UPDATE SET quantity = quantity + ?",
        (user_id, item, quantity, quantity),
    )
    conn.commit()
    cursor.close()


def remove_item(user_id: int, item: str, quantity: int = 1):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT quantity FROM user_items WHERE user_id = ? AND item = ?",
        (user_id, item),
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        return
    new_qty = row[0] - quantity
    if new_qty <= 0:
        cursor.execute(
            "DELETE FROM user_items WHERE user_id = ? AND item = ?", (user_id, item)
        )
    else:
        cursor.execute(
            "UPDATE user_items SET quantity = ? WHERE user_id = ? AND item = ?",
            (new_qty, user_id, item),
        )
    conn.commit()
    cursor.close()


def get_items(user_id: int) -> dict:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT item, quantity FROM user_items WHERE user_id = ?", (user_id,)
    )
    rows = cursor.fetchall()
    cursor.close()
    return {row[0]: row[1] for row in rows}


def has_item(user_id: int, item: str) -> bool:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM user_items WHERE user_id = ? AND item = ? AND quantity > 0",
        (user_id, item),
    )
    row = cursor.fetchone()
    cursor.close()
    return row is not None


# Gambling streak + loss insurance
def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def claim_daily_streak(user_id: int) -> tuple[int, int]:
    """returns (streak, bonus). bonus is 0 if already claimed today.
    streak grows by 1 each consecutive day you gamble, resets on a missed day."""
    today = _today()
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT last_day, streak FROM gamble_streaks WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "INSERT INTO gamble_streaks (user_id, last_day, streak) VALUES (?, ?, 1)",
            (user_id, today),
        )
        conn.commit()
        cursor.close()
        return 1, min(1 * 25, 500)
    last_day, streak = row
    if last_day == today:
        cursor.close()
        return streak, 0
    if last_day is not None:
        try:
            last = datetime.strptime(last_day, "%Y-%m-%d").date()
            cur = datetime.strptime(today, "%Y-%m-%d").date()
            streak = streak + 1 if (cur - last).days == 1 else 1
        except ValueError:
            streak = 1
    else:
        streak = 1
    bonus = min(streak * 25, 500)
    cursor.execute(
        "UPDATE gamble_streaks SET last_day = ?, streak = ? WHERE user_id = ?",
        (today, streak, user_id),
    )
    conn.commit()
    cursor.close()
    return streak, bonus


def track_gamble_result(user_id: int, net_gain: int):
    """accumulate today's net gambling result (for loss insurance)."""
    today = _today()
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO gamble_daily (user_id, day, net, insurance_claimed)
        VALUES (?, ?, ?, 0)
        ON CONFLICT(user_id, day) DO UPDATE SET net = net + excluded.net
        """,
        (user_id, today, int(net_gain)),
    )
    conn.commit()
    cursor.close()


def claim_insurance(user_id: int) -> tuple[int, int, bool]:
    """returns (refund, eligible_losses, already_claimed). refund 10% of today's
    net losses, capped. marks the day as claimed only when a refund is paid."""
    today = _today()
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT net, insurance_claimed FROM gamble_daily WHERE user_id = ? AND day = ?",
        (user_id, today),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.close()
        return 0, 0, False
    net, claimed = row
    if claimed:
        cursor.close()
        return 0, max(0, -net), True
    eligible = max(0, -net)
    refund = min(int(eligible * 0.10), 500)
    if refund > 0:
        cursor.execute(
            "UPDATE gamble_daily SET insurance_claimed = 1 WHERE user_id = ? AND day = ?",
            (user_id, today),
        )
        conn.commit()
    cursor.close()
    return refund, eligible, False


# Stock Market
def get_stock_price(ticker: str) -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT price FROM stock_state WHERE ticker = ?", (ticker,))
    row = cursor.fetchone()
    cursor.close()
    return int(row[0]) if row else None


def get_stock_history(ticker: str) -> list:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT hist FROM stock_state WHERE ticker = ?", (ticker,))
    row = cursor.fetchone()
    cursor.close()
    if not row or not row[0]:
        return []
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return []


def get_all_stock_state() -> dict:
    """price + history for every ticker in one query.

    /stock market used to call get_stock_price and get_stock_history per
    ticker, which is 2 round-trips through the executor per stock. this is
    one.
    """
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, price, hist FROM stock_state")
    rows = cursor.fetchall()
    cursor.close()

    state = {}
    for ticker, price, hist in rows:
        try:
            parsed = json.loads(hist) if hist else []
        except (ValueError, TypeError):
            parsed = []
        state[ticker] = {"price": int(price) if price is not None else None, "hist": parsed}
    return state


def apply_stock_trade(user_id: int, ticker: str, share_delta: int, coin_delta: int) -> tuple[int, int]:
    """settle a stock trade in one transaction. returns (new_balance, new_shares).

    the user's coin change and the house's are always equal and opposite:
    coins leaving the player go to the house and vice versa. previously the
    caller made these as separate committed writes, so a crash in between
    left the house books disagreeing with the player's balance.

    mirrors update_balance()'s behaviour for a user with no economy row yet
    (they start at 100 coins).
    """
    conn = _conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            new_balance = 100 + coin_delta
            cursor.execute(
                "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, ?, '0', '0')",
                (user_id, str(new_balance)),
            )
        else:
            new_balance = _safe_int(row[0]) + coin_delta
            cursor.execute(
                "UPDATE economy SET balance = ? WHERE user_id = ?", (str(new_balance), user_id)
            )

        house_delta = str(-coin_delta)
        cursor.execute(
            "INSERT INTO config (key, value) VALUES ('house_wallet', ?) ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + CAST(? AS INTEGER)",
            (house_delta, house_delta),
        )

        cursor.execute(
            "SELECT shares FROM stock_holdings WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        )
        held_row = cursor.fetchone()
        new_shares = (int(held_row[0]) if held_row else 0) + share_delta
        if new_shares <= 0:
            new_shares = 0
            cursor.execute(
                "DELETE FROM stock_holdings WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            )
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO stock_holdings (user_id, ticker, shares) VALUES (?, ?, ?)",
                (user_id, ticker, new_shares),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

    _invalidate_config("house_wallet")
    return new_balance, new_shares


def set_stock_price(ticker: str, price: int, hist: list, updated_at: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO stock_state (ticker, price, hist, updated_at) VALUES (?, ?, ?, ?)",
        (ticker, int(price), json.dumps(hist), updated_at),
    )
    conn.commit()
    cursor.close()


def get_all_stock_prices() -> dict:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, price FROM stock_state")
    rows = cursor.fetchall()
    cursor.close()
    return {ticker: int(price) for ticker, price in rows}


def get_stock_holdings(user_id: int) -> dict:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ticker, shares FROM stock_holdings WHERE user_id = ?", (user_id,)
    )
    rows = cursor.fetchall()
    cursor.close()
    return {ticker: int(shares) for ticker, shares in rows}


def set_stock_shares(user_id: int, ticker: str, shares: int):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO stock_holdings (user_id, ticker, shares) VALUES (?, ?, ?)",
        (user_id, ticker, int(shares)),
    )
    conn.commit()
    cursor.close()


# Crypto Miner Wallet
def get_crypto_wallet(user_id: int) -> dict:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT balance, rig_level, mined_total, last_mine FROM crypto_wallets WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return {"balance": 0, "rig_level": 1, "mined_total": 0, "last_mine": None}
    return {
        "balance": int(row[0]),
        "rig_level": int(row[1]),
        "mined_total": int(row[2]),
        "last_mine": row[3],
    }


def set_crypto_wallet(user_id: int, balance: int, rig_level: int, mined_total: int, last_mine: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO crypto_wallets (user_id, balance, rig_level, mined_total, last_mine) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET balance = ?, rig_level = ?, mined_total = ?, last_mine = ?",
        (user_id, balance, rig_level, mined_total, last_mine, balance, rig_level, mined_total, last_mine),
    )
    conn.commit()
    cursor.close()


def get_crypto_leaderboard(limit: int = 10) -> list:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, balance, mined_total FROM crypto_wallets ORDER BY mined_total DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    cursor.close()
    return rows


def cashout_crypto(user_id: int, take: int, payout: int, income_tax: int = 0) -> tuple[int, int]:
    """move mined crypto into the main economy in one transaction.

    wallet deduction and economy credit used to be separate commits, so a
    crash between them either paid out without deducting or deducted without
    paying. validates the wallet balance inside the same transaction.

    income tax (if any) is deducted in the same transaction: payout is the
    gross credit, income_tax the cut for the state. returns (new_balance, tax).
    """
    conn = _conn()
    cursor = conn.cursor()
    wallet = get_crypto_wallet(user_id)
    if wallet["balance"] < take:
        cursor.close()
        raise ValueError("wallet balance too low")
    remain = wallet["balance"] - take
    cursor.execute(
        "INSERT INTO crypto_wallets (user_id, balance, rig_level, mined_total, last_mine) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET balance = ?",
        (user_id, remain, wallet["rig_level"], wallet["mined_total"], wallet["last_mine"], remain),
    )
    net = payout - income_tax
    row = cursor.execute(
        "SELECT balance FROM economy WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        new_balance = 100 + net
        cursor.execute(
            "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, ?, '0', '0')",
            (user_id, str(new_balance)),
        )
    else:
        new_balance = _safe_int(row[0]) + net
        cursor.execute(
            "UPDATE economy SET balance = ? WHERE user_id = ?", (str(new_balance), user_id)
        )
    if income_tax:
        cursor.execute(
            "INSERT INTO config (key, value) VALUES ('house_wallet', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + CAST(? AS INTEGER)",
            (str(income_tax), str(income_tax)),
        )
        collected = get_config("income_tax_collected", "0")
        cursor.execute(
            "INSERT INTO config (key, value) VALUES ('income_tax_collected', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + CAST(? AS INTEGER)",
            (str(int(collected) + income_tax), str(income_tax)),
        )
    conn.commit()
    cursor.close()
    _invalidate_config("house_wallet")
    _invalidate_config("income_tax_collected")
    return new_balance, income_tax


# 宠物系统 (Pet System)
def get_pet(user_id: int) -> dict:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, species, hunger, mood, energy, level, xp, fed_total, last_fed, last_played "
        "FROM pets WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return None
    return {
        "name": row[0],
        "species": row[1],
        "hunger": int(row[2]),
        "mood": int(row[3]),
        "energy": int(row[4]),
        "level": int(row[5]),
        "xp": int(row[6]),
        "fed_total": int(row[7]),
        "last_fed": row[8],
        "last_played": row[9],
    }


def set_pet(user_id: int, params: dict):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pets (user_id, name, species, hunger, mood, energy, level, xp, fed_total, last_fed, last_played) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "name = excluded.name, species = excluded.species, "
        "hunger = excluded.hunger, mood = excluded.mood, energy = excluded.energy, "
        "level = excluded.level, xp = excluded.xp, fed_total = excluded.fed_total, "
        "last_fed = excluded.last_fed, last_played = excluded.last_played",
        (
            user_id,
            params["name"],
            params["species"],
            params["hunger"],
            params["mood"],
            params["energy"],
            params["level"],
            params["xp"],
            params["fed_total"],
            params.get("last_fed"),
            params.get("last_played"),
        ),
    )
    conn.commit()
    cursor.close()


def get_all_pets() -> list:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, name, species, hunger, mood, energy, level, xp, fed_total, last_fed, last_played "
        "FROM pets"
    )
    rows = cursor.fetchall()
    cursor.close()
    return [
        {
            "user_id": r[0],
            "name": r[1],
            "species": r[2],
            "hunger": int(r[3]),
            "mood": int(r[4]),
            "energy": int(r[5]),
            "level": int(r[6]),
            "xp": int(r[7]),
            "fed_total": int(r[8]),
            "last_fed": r[9],
            "last_played": r[10],
        }
        for r in rows
    ]


# Cars
def get_user_cars(user_id: int) -> list[dict]:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT car_key, name, tier, mileage, wear, earned_total, last_drive FROM user_cars WHERE user_id = ? ORDER BY tier DESC, mileage DESC",
        (user_id,),
    )
    rows = cursor.fetchall()
    cursor.close()
    return [
        {
            "car_key": row[0],
            "name": row[1],
            "tier": int(row[2]),
            "mileage": int(row[3]),
            "wear": int(row[4]),
            "earned_total": _safe_int(row[5]),
            "last_drive": row[6],
        }
        for row in rows
    ]


def get_car(user_id: int, car_key: str) -> dict:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT car_key, name, tier, mileage, wear, earned_total, last_drive FROM user_cars WHERE user_id = ? AND car_key = ?",
        (user_id, car_key),
    )
    row = cursor.fetchone()
    cursor.close()
    if not row:
        return None
    return {
        "car_key": row[0],
        "name": row[1],
        "tier": int(row[2]),
        "mileage": int(row[3]),
        "wear": int(row[4]),
        "earned_total": _safe_int(row[5]),
        "last_drive": row[6],
    }


def add_car(user_id: int, car_key: str, name: str, tier: int) -> bool:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO user_cars (user_id, car_key, name, tier) VALUES (?, ?, ?, ?)",
        (user_id, car_key, name, tier),
    )
    inserted = cursor.rowcount > 0
    conn.commit()
    cursor.close()
    return inserted


def record_car_drive(user_id: int, car_key: str, miles: int, wear: int, earned: int, last_drive: str) -> dict:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE user_cars
        SET mileage = mileage + ?,
            wear = min(wear + ?, 100),
            earned_total = CAST(CAST(earned_total AS INTEGER) + ? AS TEXT),
            last_drive = ?
        WHERE user_id = ? AND car_key = ?
        """,
        (miles, wear, earned, last_drive, user_id, car_key),
    )
    conn.commit()
    cursor.close()
    return get_car(user_id, car_key)


def repair_car(user_id: int, car_key: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_cars SET wear = 0 WHERE user_id = ? AND car_key = ?",
        (user_id, car_key),
    )
    conn.commit()
    cursor.close()


def get_all_car_earnings(limit: int = 10) -> list[dict]:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT user_id, SUM(CAST(earned_total AS INTEGER)) AS earned, SUM(mileage) AS miles
        FROM user_cars
        GROUP BY user_id
        HAVING earned > 0
        ORDER BY earned DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    cursor.close()
    return [
        {"user_id": row[0], "earned_total": _safe_int(row[1]), "mileage": int(row[2] or 0)}
        for row in rows
    ]


init_db()
