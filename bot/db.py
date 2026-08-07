import sqlite3
import os
import threading
from datetime import datetime, timedelta

DB_PATH = os.environ.get("BOT_DB_PATH", "birdvirus.db")

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
        balance, bank = int(row[0]), int(row[1])
        debt = int(row[2] or 0)
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
        balance = int(row[0])
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
    cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        new_balance = 100 + change
        cursor.execute(
            "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, ?, '0', '0')",
            (user_id, str(new_balance)),
        )
    else:
        new_balance = int(row[0]) + change
        cursor.execute(
            "UPDATE economy SET balance = ? WHERE user_id = ?", (str(new_balance), user_id)
        )
    conn.commit()
    cursor.close()
    return new_balance


def update_bank(user_id: int, change: int) -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT bank FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        new_bank = change
        cursor.execute(
            "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', ?, '0')",
            (user_id, str(new_bank)),
        )
    else:
        new_bank = int(row[0] or 0) + change
        cursor.execute(
            "UPDATE economy SET bank = ? WHERE user_id = ?", (str(new_bank), user_id)
        )
    conn.commit()
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
    debt = int(row[0] or 0)
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
    cursor.execute("SELECT debt FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        new_debt = max(0, change)
        cursor.execute("INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', '0', ?)", (user_id, str(new_debt)))
    else:
        new_debt = int(row[0] or 0) + change
        if new_debt < 0:
            new_debt = 0
        cursor.execute("UPDATE economy SET debt = ? WHERE user_id = ?", (str(new_debt), user_id))
    conn.commit()
    cursor.close()
    return new_debt

def get_all_balances() -> list[dict]:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance, bank, debt FROM economy ORDER BY (CAST(balance AS INTEGER) + CAST(bank AS INTEGER) - CAST(debt AS INTEGER)) DESC")
    rows = cursor.fetchall()
    cursor.close()
    return [{"user_id": row[0], "balance": int(row[1]), "bank": int(row[2]), "debt": int(row[3] or 0)} for row in rows]

def get_all_debts() -> list[dict]:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, debt, balance, bank FROM economy WHERE CAST(debt AS INTEGER) > 0 ORDER BY CAST(debt AS INTEGER) DESC")
    rows = cursor.fetchall()
    cursor.close()
    return [{"user_id": row[0], "debt": int(row[1]), "balance": int(row[2]), "bank": int(row[3])} for row in rows]


# Config Functions (Emoji, Properties channel, etc)
def get_config(key: str, default: str = None) -> str:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    cursor.close()
    return row[0] if row else default


def set_config(key: str, value: str):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, value, value),
    )
    conn.commit()
    cursor.close()


# House Wallet
def get_house() -> int:
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute("SELECT CAST(value AS INTEGER) FROM config WHERE key = 'house_wallet'")
    row = cursor.fetchone()
    cursor.close()
    return int(row[0]) if row and row[0] else 0


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
    cursor.execute("SELECT CAST(value AS INTEGER) FROM config WHERE key = 'house_wallet'")
    row = cursor.fetchone()
    new_val = int(row[0]) if row and row[0] else 0
    cursor.close()
    return new_val


# Balance Locks
def is_balance_locked(user_id: int) -> bool:
    csv = get_config("locked_balances", "")
    if not csv or not csv.strip():
        return False
    return str(user_id) in [x.strip() for x in csv.split(",") if x.strip()]


def lock_balance(user_id: int):
    csv = get_config("locked_balances", "")
    ids = [x.strip() for x in csv.split(",") if x.strip()]
    uid = str(user_id)
    if uid not in ids:
        ids.append(uid)
    set_config("locked_balances", ",".join(ids))


def unlock_balance(user_id: int):
    csv = get_config("locked_balances", "")
    ids = [x.strip() for x in csv.split(",") if x.strip()]
    uid = str(user_id)
    if uid in ids:
        ids.remove(uid)
    set_config("locked_balances", ",".join(ids))


def get_locked_balances() -> list[int]:
    csv = get_config("locked_balances", "")
    if not csv or not csv.strip():
        return []
    return [int(x.strip()) for x in csv.split(",") if x.strip()]
    """atomically adjust the house wallet balance. returns new balance."""
    conn = _conn()
    cursor = conn.cursor()
    val = str(change)
    cursor.execute(
        "INSERT INTO config (key, value) VALUES ('house_wallet', ?) ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + CAST(? AS INTEGER)",
        (val, val),
    )
    conn.commit()
    cursor.execute("SELECT CAST(value AS INTEGER) FROM config WHERE key = 'house_wallet'")
    row = cursor.fetchone()
    new_val = int(row[0]) if row and row[0] else 0
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
        "SELECT net FROM gamble_daily WHERE user_id = ? AND day = ?",
        (user_id, today),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            "INSERT INTO gamble_daily (user_id, day, net, insurance_claimed) VALUES (?, ?, ?, 0)",
            (user_id, today, int(net_gain)),
        )
    else:
        cursor.execute(
            "UPDATE gamble_daily SET net = ? WHERE user_id = ? AND day = ?",
            (row[0] + int(net_gain), user_id, today),
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


init_db()
