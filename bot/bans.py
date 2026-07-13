import os
import asyncio
from typing import Set

BAN_FILE = "banned_users.txt"


def _ensure_file():
    # create the file if it doesn't exist
    d = os.path.dirname(BAN_FILE)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(BAN_FILE):
        open(BAN_FILE, "w", encoding="utf-8").close()


def _read_banned_users_sync() -> Set[int]:
    _ensure_file()
    ids = set()
    try:
        with open(BAN_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ids.add(int(line))
                except ValueError:
                    # ignore malformed lines
                    continue
    except FileNotFoundError:
        pass
    return ids


async def read_banned_users() -> Set[int]:
    return await asyncio.to_thread(_read_banned_users_sync)


def _write_banned_users_sync(ids: Set[int]):
    _ensure_file()
    try:
        with open(BAN_FILE, "w", encoding="utf-8") as f:
            for uid in sorted(ids):
                f.write(f"{uid}\n")
    except Exception:
        # best effort write; ignore errors to avoid crashing bot
        pass


def _add_ban_sync(user_id: int):
    ids = _read_banned_users_sync()
    if user_id in ids:
        return
    ids.add(int(user_id))
    _write_banned_users_sync(ids)


async def add_ban(user_id: int):
    await asyncio.to_thread(_add_ban_sync, user_id)


def _remove_ban_sync(user_id: int):
    ids = _read_banned_users_sync()
    if int(user_id) not in ids:
        return
    ids.discard(int(user_id))
    _write_banned_users_sync(ids)


async def remove_ban(user_id: int):
    await asyncio.to_thread(_remove_ban_sync, user_id)
