import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("BOT_DB_PATH", "birdvirus.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
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

    # add bank column to existing dbs
    try:
        cursor.execute("ALTER TABLE economy ADD COLUMN bank INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # add debt column to existing dbs
    for attempt in range(3):
        try:
            cursor.execute("ALTER TABLE economy ADD COLUMN debt INTEGER DEFAULT 0")
            break
        except sqlite3.OperationalError:
            pass

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

    conn.commit()
    conn.close()


# Ban Functions
def ban_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO banned_users (user_id) VALUES (?)", (user_id,)
    )
    conn.commit()
    conn.close()


def unban_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_banned_users() -> set:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM banned_users")
    rows = cursor.fetchall()
    conn.close()
    return {row[0] for row in rows}


# Chat Reset Functions
def set_chat_reset(channel_id: int, reset_at: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_resets (channel_id, reset_at) VALUES (?, ?) ON CONFLICT(channel_id) DO UPDATE SET reset_at = ?",
        (channel_id, reset_at, reset_at),
    )
    conn.commit()
    conn.close()


def get_chat_reset(channel_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reset_at FROM chat_resets WHERE channel_id = ?", (channel_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# Say Logs Functions
def log_say(user_id: int, user_name: str, message: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO say_logs (user_id, user_name, message_content, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, user_name, message, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_say_logs(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_name, user_id, message_content, timestamp FROM say_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def clear_say_logs():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM say_logs")
    conn.commit()
    conn.close()


# Economy Functions
def get_balances(user_id: int) -> tuple[int, int, int]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance, bank, debt FROM economy WHERE user_id = ?", (user_id,))
    except sqlite3.OperationalError:
        conn.close()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE economy ADD COLUMN debt TEXT DEFAULT '0'")
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
    conn.close()
    return balance, bank, debt


def get_balance(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()
    return balance


def set_balance(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, ?, '0', '0') ON CONFLICT(user_id) DO UPDATE SET balance = ?",
        (user_id, str(amount), str(amount)),
    )
    conn.commit()
    conn.close()


def set_bank(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', ?, '0') ON CONFLICT(user_id) DO UPDATE SET bank = ?",
        (user_id, str(amount), str(amount)),
    )
    conn.commit()
    conn.close()


def update_balance(user_id: int, change: int) -> int:
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()
    return new_balance


def update_bank(user_id: int, change: int) -> int:
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()
    return new_bank

def get_debt(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT debt FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', '0', '0')", (user_id,))
        conn.commit()
        conn.close()
        return 0
    debt = int(row[0] or 0)
    conn.close()
    return debt

def set_debt(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO economy (user_id, balance, bank, debt) VALUES (?, '100', '0', ?) ON CONFLICT(user_id) DO UPDATE SET debt = ?",
        (user_id, str(amount), str(amount)),
    )
    conn.commit()
    conn.close()

def update_debt(user_id: int, change: int) -> int:
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()
    return new_debt

def get_all_balances() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance, bank, debt FROM economy ORDER BY (CAST(balance AS INTEGER) + CAST(bank AS INTEGER) - CAST(debt AS INTEGER)) DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": row[0], "balance": int(row[1]), "bank": int(row[2]), "debt": int(row[3] or 0)} for row in rows]

def get_all_debts() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, debt, balance, bank FROM economy WHERE CAST(debt AS INTEGER) > 0 ORDER BY CAST(debt AS INTEGER) DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": row[0], "debt": int(row[1]), "balance": int(row[2]), "bank": int(row[3])} for row in rows]


# Config Functions (Emoji, Properties channel, etc)
def get_config(key: str, default: str = None) -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default


def set_config(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, value, value),
    )
    conn.commit()
    conn.close()


# Properties Functions
def add_property(thread_id: int, owner_id: int, name: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO properties (thread_id, owner_id, name) VALUES (?, ?, ?)",
        (thread_id, owner_id, name),
    )
    conn.commit()
    conn.close()


def get_property(thread_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT owner_id, name FROM properties WHERE thread_id = ?", (thread_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row


def update_property_owner(thread_id: int, new_owner_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE properties SET owner_id = ? WHERE thread_id = ?",
        (new_owner_id, thread_id),
    )
    conn.commit()
    conn.close()


def update_property_name(thread_id: int, new_name: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE properties SET name = ? WHERE thread_id = ?", (new_name, thread_id)
    )
    conn.commit()
    conn.close()


# Job Functions
def get_user_job(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT job_name, job_xp, job_level, shifts_completed, last_work_time FROM user_jobs WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
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
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()


def remove_user_job(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_jobs WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def update_job_progress(user_id: int, xp_gain: int, time_str: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT job_xp, job_level, shifts_completed FROM user_jobs WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
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
    conn.close()
    return level_up, level


def update_job_time(user_id: int, time_str: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE user_jobs SET last_work_time = ? WHERE user_id = ?", (time_str, user_id)
    )
    conn.commit()
    conn.close()


# User Items Functions
def add_item(user_id: int, item: str, quantity: int = 1):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_items (user_id, item, quantity) VALUES (?, ?, ?) ON CONFLICT(user_id, item) DO UPDATE SET quantity = quantity + ?",
        (user_id, item, quantity, quantity),
    )
    conn.commit()
    conn.close()


def remove_item(user_id: int, item: str, quantity: int = 1):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT quantity FROM user_items WHERE user_id = ? AND item = ?",
        (user_id, item),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
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
    conn.close()


def get_items(user_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT item, quantity FROM user_items WHERE user_id = ?", (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def has_item(user_id: int, item: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM user_items WHERE user_id = ? AND item = ? AND quantity > 0",
        (user_id, item),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


init_db()
