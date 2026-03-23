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
            password    TEXT    NOT NULL DEFAULT '',
            salt        TEXT    NOT NULL DEFAULT '',
            display_name TEXT   NOT NULL DEFAULT '',
            google_id   TEXT    UNIQUE,
            games_played INTEGER NOT NULL DEFAULT 0,
            games_won    INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Migration: add google_id column if missing (for existing databases)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN google_id TEXT UNIQUE")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_games (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            board_size  INTEGER NOT NULL DEFAULT 19,
            human_color TEXT    NOT NULL DEFAULT 'black',
            result      TEXT    NOT NULL DEFAULT '',
            played_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            sgf_text    TEXT    NOT NULL DEFAULT ''
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


def find_or_create_google_user(google_id: str, email: str, name: str) -> dict:
    """Find existing user by google_id, or create a new one. Returns user dict."""
    conn = _get_db()
    # Check if user already linked
    row = conn.execute(
        "SELECT id, username, display_name, games_played, games_won, created_at FROM users WHERE google_id = ?",
        (google_id,),
    ).fetchone()
    if row:
        conn.close()
        return dict(row)

    # Create new user with Google identity
    display_name = name or email.split("@")[0]
    # Use email prefix as username, dedup if needed
    base_username = email.split("@")[0][:20]
    username = base_username
    suffix = 1
    while True:
        try:
            conn.execute(
                "INSERT INTO users (username, display_name, google_id) VALUES (?, ?, ?)",
                (username, display_name, google_id),
            )
            conn.commit()
            break
        except sqlite3.IntegrityError:
            suffix += 1
            username = f"{base_username[:17]}_{suffix}"

    row = conn.execute(
        "SELECT id, username, display_name, games_played, games_won, created_at FROM users WHERE google_id = ?",
        (google_id,),
    ).fetchone()
    conn.close()
    return dict(row)


def save_game(user_id: int, board_size: int, human_color: str, result: str, sgf_text: str) -> int:
    """Save a completed game. Returns the new game id."""
    conn = _get_db()
    cur = conn.execute(
        "INSERT INTO user_games (user_id, board_size, human_color, result, sgf_text) VALUES (?, ?, ?, ?, ?)",
        (user_id, board_size, human_color, result, sgf_text),
    )
    game_id = cur.lastrowid
    conn.commit()
    conn.close()
    return game_id


def list_user_games(user_id: int) -> list[dict]:
    """Return summary rows for a user's saved games, newest first."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT id, board_size, human_color, result, played_at FROM user_games WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_game(game_id: int, user_id: int) -> dict | None:
    """Fetch one game, verifying ownership. Returns dict with sgf_text or None."""
    conn = _get_db()
    row = conn.execute(
        "SELECT id, board_size, human_color, result, played_at, sgf_text FROM user_games WHERE id = ? AND user_id = ?",
        (game_id, user_id),
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
