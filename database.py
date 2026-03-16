"""
SQLite database for user registration and profiles.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "users.db"


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password    TEXT    NOT NULL,
            salt        TEXT    NOT NULL,
            display_name TEXT   NOT NULL DEFAULT '',
            games_played INTEGER NOT NULL DEFAULT 0,
            games_won    INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def create_user(username: str, password: str, display_name: str = "") -> dict | None:
    """Register a new user. Returns user dict or None if username taken."""
    salt = secrets.token_hex(16)
    hashed = _hash_password(password, salt)
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password, salt, display_name) VALUES (?, ?, ?, ?)",
            (username, hashed, salt, display_name or username),
        )
        conn.commit()
        user = conn.execute(
            "SELECT id, username, display_name, games_played, games_won, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(user) if user else None
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    """Check credentials. Returns user dict or None."""
    conn = _get_db()
    row = conn.execute(
        "SELECT id, username, password, salt, display_name, games_played, games_won, created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    if _hash_password(password, row["salt"]) != row["password"]:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "games_played": row["games_played"],
        "games_won": row["games_won"],
        "created_at": row["created_at"],
    }


def get_user_by_id(user_id: int) -> dict | None:
    conn = _get_db()
    row = conn.execute(
        "SELECT id, username, display_name, games_played, games_won, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_stats(user_id: int, won: bool) -> None:
    """Increment games_played (and games_won if won)."""
    conn = _get_db()
    if won:
        conn.execute(
            "UPDATE users SET games_played = games_played + 1, games_won = games_won + 1 WHERE id = ?",
            (user_id,),
        )
    else:
        conn.execute(
            "UPDATE users SET games_played = games_played + 1 WHERE id = ?",
            (user_id,),
        )
    conn.commit()
    conn.close()
