"""Local SQLite-backed persistent chat store for NL2SQL."""

import io
import json
import sqlite3
import uuid
import datetime
from pathlib import Path
from typing import Optional, Any
import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "conversations.db"


class ChatStore:
    """Manages persistent chat sessions and message history entirely on the local filesystem."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    database_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sql TEXT,
                    category TEXT,
                    explanation TEXT,
                    status TEXT,
                    data_json TEXT,
                    message TEXT,
                    error TEXT,
                    latency_ms REAL DEFAULT 0.0,
                    cost_info_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def create_session(self, database_name: str, title: str = "New Conversation") -> str:
        """Create a new chat session and return its unique session_id."""
        session_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO chat_sessions (session_id, title, database_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, title, database_name, now, now),
            )
            conn.commit()
        return session_id

    def list_sessions(self, database_name: Optional[str] = None) -> list[dict[str, Any]]:
        """List all past chat sessions, optionally filtered by database name."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if database_name:
                cur = conn.execute(
                    "SELECT * FROM chat_sessions WHERE database_name = ? ORDER BY updated_at DESC",
                    (database_name,),
                )
            else:
                cur = conn.execute("SELECT * FROM chat_sessions ORDER BY updated_at DESC")
            return [dict(row) for row in cur.fetchall()]

    def update_session_title(self, session_id: str, title: str):
        """Update the human-readable title of a session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE chat_sessions SET title = ? WHERE session_id = ?",
                (title, session_id),
            )
            conn.commit()

    def delete_session(self, session_id: str):
        """Delete a chat session and its corresponding messages."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            conn.commit()

    def get_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Retrieve all messages for a specific session, restoring any Pandas DataFrames."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            )
            rows = cur.fetchall()

        messages = []
        for r in rows:
            msg = {
                "role": r["role"],
                "content": r["content"],
                "sql": r["sql"],
                "category": r["category"],
                "explanation": r["explanation"],
                "status": r["status"],
                "message": r["message"],
                "error": r["error"],
                "latency_ms": r["latency_ms"],
            }
            if r["data_json"]:
                try:
                    msg["data"] = pd.read_json(io.StringIO(r["data_json"]), orient="split")
                except Exception:
                    msg["data"] = None
            if r["cost_info_json"]:
                try:
                    msg["cost_info"] = json.loads(r["cost_info_json"])
                except Exception:
                    msg["cost_info"] = {}
            messages.append(msg)
        return messages

    def save_message(self, session_id: str, msg: dict[str, Any]):
        """Persist a message (user or assistant) to the session history."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        data_json = None
        if "data" in msg and isinstance(msg["data"], pd.DataFrame):
            data_json = msg["data"].to_json(orient="split")

        cost_info_json = None
        if "cost_info" in msg and isinstance(msg["cost_info"], dict):
            cost_info_json = json.dumps(msg["cost_info"])

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (
                    session_id, role, content, sql, category, explanation, status,
                    data_json, message, error, latency_ms, cost_info_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    msg.get("role", "user"),
                    msg.get("content", ""),
                    msg.get("sql"),
                    msg.get("category"),
                    msg.get("explanation"),
                    msg.get("status"),
                    data_json,
                    msg.get("message"),
                    msg.get("error"),
                    msg.get("latency_ms", 0.0),
                    cost_info_json,
                    now,
                ),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()


chat_store = ChatStore()
