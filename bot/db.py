import sqlite3
import os
from datetime import datetime

DB_PATH = "birdvirus.db"

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
            balance INTEGER DEFAULT 100
        )
    """)
    
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
    
    conn.commit()
    conn.close()

# Chat Reset Functions
def set_chat_reset(channel_id: int, reset_at: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_resets (channel_id, reset_at) VALUES (?, ?) ON CONFLICT(channel_id) DO UPDATE SET reset_at = ?",
        (channel_id, reset_at, reset_at)
    )
    conn.commit()
    conn.close()

def get_chat_reset(channel_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT reset_at FROM chat_resets WHERE channel_id = ?", (channel_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# Say Logs Functions
def log_say(user_id: int, user_name: str, message: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO say_logs (user_id, user_name, message_content, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, user_name, message, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_say_logs(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, user_id, message_content, timestamp FROM say_logs ORDER BY id DESC LIMIT ?", (limit,))
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
def get_balances(user_id: int) -> tuple[int, int]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, bank FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO economy (user_id, balance, bank) VALUES (?, 100, 0)", (user_id,))
        conn.commit()
        balance, bank = 100, 0
    else:
        balance, bank = row[0], row[1]
    conn.close()
    return balance, bank

def get_balance(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        # Default starting balance of 100 coins
        cursor.execute("INSERT INTO economy (user_id, balance) VALUES (?, 100)", (user_id,))
        conn.commit()
        balance = 100
    else:
        balance = row[0]
    conn.close()
    return balance

def set_balance(user_id: int, amount: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO economy (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = ?", (user_id, amount, amount))
    conn.commit()
    conn.close()

def update_balance(user_id: int, change: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        new_balance = 100 + change
        cursor.execute("INSERT INTO economy (user_id, balance, bank) VALUES (?, ?, 0)", (user_id, new_balance))
    else:
        new_balance = row[0] + change
        cursor.execute("UPDATE economy SET balance = ? WHERE user_id = ?", (new_balance, user_id))
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
        cursor.execute("INSERT INTO economy (user_id, balance, bank) VALUES (?, 100, ?)", (user_id, new_bank))
    else:
        new_bank = (row[0] or 0) + change
        cursor.execute("UPDATE economy SET bank = ? WHERE user_id = ?", (new_bank, user_id))
    conn.commit()
    conn.close()
    return new_bank

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
    cursor.execute("INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?", (key, value, value))
    conn.commit()
    conn.close()

# Properties Functions
def add_property(thread_id: int, owner_id: int, name: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO properties (thread_id, owner_id, name) VALUES (?, ?, ?)", (thread_id, owner_id, name))
    conn.commit()
    conn.close()

init_db()
