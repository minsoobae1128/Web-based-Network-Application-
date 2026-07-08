"""
database.py — SQLite helpers for CN2026 HW5
"""

import sqlite3, time
from pathlib import Path

DB_PATH = Path("db/messenger.db")

# ── Init ──────────────────────────────────────────────────────────────────────
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            is_online     INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            sender    TEXT NOT NULL,
            receiver  TEXT NOT NULL,
            content   TEXT NOT NULL,
            msg_type  TEXT DEFAULT 'text',
            timestamp TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uploader    TEXT NOT NULL,
            receiver    TEXT NOT NULL,
            filename    TEXT NOT NULL,
            orig_name   TEXT NOT NULL,
            uploaded_at TEXT DEFAULT (datetime('now'))
        );
        """)

    # Seed the virtual Ollama bot if absent
    with _conn() as con:
        existing = con.execute(
            "SELECT 1 FROM users WHERE username='Ollama'"
        ).fetchone()
        if not existing:
            con.execute(
                "INSERT INTO users (username, password_hash, is_online) VALUES ('Ollama','<bot>',1)"
            )

# ── Users ─────────────────────────────────────────────────────────────────────
def create_user(username: str, password_hash: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO users (username, password_hash) VALUES (?,?)",
            (username, password_hash)
        )

def get_user(username: str):
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        return dict(row) if row else None

def set_online(username: str, online: bool):
    with _conn() as con:
        con.execute(
            "UPDATE users SET is_online=? WHERE username=?",
            (1 if online else 0, username)
        )

def get_all_users():
    with _conn() as con:
        rows = con.execute(
            "SELECT username, is_online FROM users ORDER BY is_online DESC, username"
        ).fetchall()
        return [dict(r) for r in rows]

# ── Messages ──────────────────────────────────────────────────────────────────
def save_message(sender: str, receiver: str, content: str, msg_type: str = "text") -> dict:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO messages (sender, receiver, content, msg_type) VALUES (?,?,?,?)",
            (sender, receiver, content, msg_type)
        )
        row = con.execute(
            "SELECT * FROM messages WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

def get_messages(user_a: str, user_b: str) -> list:
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM messages
               WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
               ORDER BY id""",
            (user_a, user_b, user_b, user_a)
        ).fetchall()
        return [dict(r) for r in rows]
