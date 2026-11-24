import sqlite3
from datetime import datetime, timezone
from typing import Any

from .config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.sqlite_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    with _connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS connections (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              host TEXT NOT NULL, port INTEGER NOT NULL, db_name TEXT NOT NULL,
              created_at TEXT NOT NULL, last_used_at TEXT NOT NULL,
              UNIQUE (host, port, db_name)
            );
            CREATE TABLE IF NOT EXISTS schema_cache (
              connection_id INTEGER PRIMARY KEY REFERENCES connections(id),
              metadata_json TEXT NOT NULL, metadata_text TEXT NOT NULL,
              extracted_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chats (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              connection_id INTEGER NOT NULL REFERENCES connections(id),
              question TEXT NOT NULL, generated_sql TEXT NOT NULL, executed_sql TEXT,
              row_count INTEGER, status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS summaries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              chat_id INTEGER NOT NULL REFERENCES chats(id), kind TEXT NOT NULL,
              text TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """
        )


def upsert_connection(host: str, port: int, db_name: str) -> int:
    now = utc_now()
    with _connection() as conn:
        conn.execute(
            """INSERT INTO connections (host, port, db_name, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(host, port, db_name) DO UPDATE SET last_used_at=excluded.last_used_at""",
            (host, port, db_name, now, now),
        )
        row = conn.execute(
            "SELECT id FROM connections WHERE host=? AND port=? AND db_name=?",
            (host, port, db_name),
        ).fetchone()
        return int(row["id"])


def list_connections() -> list[dict[str, Any]]:
    with _connection() as conn:
        rows = conn.execute(
            """SELECT c.id, c.host, c.port, c.db_name, c.last_used_at,
               EXISTS(SELECT 1 FROM schema_cache s WHERE s.connection_id=c.id) AS has_metadata
               FROM connections c ORDER BY c.last_used_at DESC"""
        ).fetchall()
        return [dict(row) for row in rows]


def get_connection(connection_id: int) -> dict[str, Any] | None:
    with _connection() as conn:
        row = conn.execute("SELECT * FROM connections WHERE id=?", (connection_id,)).fetchone()
        return dict(row) if row else None


def has_metadata(connection_id: int) -> bool:
    with _connection() as conn:
        return conn.execute(
            "SELECT 1 FROM schema_cache WHERE connection_id=?", (connection_id,)
        ).fetchone() is not None


def save_schema_cache(connection_id: int, metadata_json: str, metadata_text: str, extracted_at: str) -> None:
    with _connection() as conn:
        conn.execute(
            """INSERT INTO schema_cache (connection_id, metadata_json, metadata_text, extracted_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(connection_id) DO UPDATE SET metadata_json=excluded.metadata_json,
               metadata_text=excluded.metadata_text, extracted_at=excluded.extracted_at""",
            (connection_id, metadata_json, metadata_text, extracted_at),
        )


def get_schema_cache(connection_id: int) -> dict[str, Any] | None:
    with _connection() as conn:
        row = conn.execute("SELECT * FROM schema_cache WHERE connection_id=?", (connection_id,)).fetchone()
        return dict(row) if row else None


def clear_schema_cache(connection_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM schema_cache WHERE connection_id=?", (connection_id,))


def create_chat(connection_id: int, question: str, generated_sql: str) -> int:
    with _connection() as conn:
        cursor = conn.execute(
            """INSERT INTO chats (connection_id, question, generated_sql, status, created_at)
               VALUES (?, ?, ?, 'generated', ?)""",
            (connection_id, question, generated_sql, utc_now()),
        )
        return int(cursor.lastrowid)


def get_chat(chat_id: int) -> dict[str, Any] | None:
    with _connection() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        return dict(row) if row else None


def mark_chat_error(chat_id: int, message: str) -> None:
    with _connection() as conn:
        conn.execute("UPDATE chats SET status='error', error=? WHERE id=?", (message, chat_id))


def mark_chat_executed(chat_id: int, sql: str, row_count: int) -> None:
    with _connection() as conn:
        conn.execute(
            """UPDATE chats SET executed_sql=?, row_count=?, status='executed', error=NULL
               WHERE id=?""",
            (sql, row_count, chat_id),
        )


def executed_history(connection_id: int, limit: int) -> list[dict[str, Any]]:
    with _connection() as conn:
        rows = conn.execute(
            """SELECT question, executed_sql FROM (
                 SELECT question, executed_sql, id FROM chats
                 WHERE connection_id=? AND status='executed'
                 ORDER BY id DESC LIMIT ?
               ) ORDER BY id ASC""",
            (connection_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def create_summary(chat_id: int, kind: str, text: str) -> int:
    with _connection() as conn:
        cursor = conn.execute(
            "INSERT INTO summaries (chat_id, kind, text, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, kind, text, utc_now()),
        )
        return int(cursor.lastrowid)


def chats_with_summaries(connection_id: int) -> list[dict[str, Any]]:
    with _connection() as conn:
        chats = [dict(row) for row in conn.execute(
            "SELECT * FROM chats WHERE connection_id=? ORDER BY id ASC", (connection_id,)
        ).fetchall()]
        for chat in chats:
            rows = conn.execute(
                "SELECT id, kind, text, created_at FROM summaries WHERE chat_id=? ORDER BY id ASC",
                (chat["id"],),
            ).fetchall()
            chat["summaries"] = [dict(row) for row in rows]
        return chats
