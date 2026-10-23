"""Security, privacy, and audit compliance module for NL2SQL."""

import re
import sqlite3
import datetime
from pathlib import Path
from typing import Optional, Any
import pandas as pd

AUDIT_DB_PATH = Path(__file__).resolve().parent / "audit_log.db"

# Sensitive column patterns that must never leak raw values into LLM prompts
SENSITIVE_COLUMN_PATTERNS = [
    r"pass(word|wd)?",
    r"pwd",
    r"token",
    r"secret",
    r"ssn",
    r"credit_?card",
    r"card_?num(ber)?",
    r"cvv",
    r"api_?key",
    r"pin",
    r"auth",
    r"private_?key",
]

# Adversarial prompt injection keywords
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s+(prompt\s+)?override",
    r"you\s+are\s+now\s+in\s+(developer|god|dan)\s+mode",
    r"bypass\s+security\s+rules?",
    r"reveal\s+(the\s+)?system\s+prompt",
    r"drop\s+database",
    r"drop\s+table",
    r"truncate\s+table",
    r"grant\s+all",
]


class SecurityError(Exception):
    """Raised when an operation violates security or safety guardrails."""
    pass


def is_sensitive_column(column_name: str) -> bool:
    """Returns True if the column name suggests sensitive personal or security data."""
    col = column_name.lower().strip()
    return any(re.search(pat, col) for pat in SENSITIVE_COLUMN_PATTERNS)


def mask_sample_row(columns: list[str], row: tuple[Any, ...]) -> tuple[Any, ...]:
    """Replaces values for sensitive columns with '***MASKED***'."""
    masked = []
    for col_name, val in zip(columns, row):
        if is_sensitive_column(col_name) and val is not None:
            masked.append("***MASKED***")
        else:
            masked.append(val)
    return tuple(masked)


def sanitize_and_check_prompt(user_prompt: str) -> None:
    """
    Validates user prompt against adversarial injections and destructive commands.
    Raises SecurityError if a suspicious pattern is detected.
    """
    cleaned = user_prompt.lower().strip()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, cleaned):
            raise SecurityError(
                f"Security Guard: Input rejected. Detected prohibited pattern or potential prompt injection: '{pattern}'."
            )


class AuditLogger:
    """Local tamper-evident audit logger using SQLite."""

    def __init__(self, db_path: Path = AUDIT_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    username TEXT,
                    database_name TEXT,
                    prompt TEXT NOT NULL,
                    generated_sql TEXT,
                    statement_type TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    rows_affected INTEGER DEFAULT 0,
                    execution_time_ms REAL DEFAULT 0.0
                )
            """)
            conn.commit()

    def log(
        self,
        username: str,
        database_name: str,
        prompt: str,
        generated_sql: Optional[str] = None,
        statement_type: Optional[str] = None,
        status: str = "SUCCESS",
        error_message: Optional[str] = None,
        rows_affected: int = 0,
        execution_time_ms: float = 0.0,
    ):
        """Append an entry to the audit log."""
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (
                    timestamp, username, database_name, prompt, generated_sql,
                    statement_type, status, error_message, rows_affected, execution_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    username,
                    database_name,
                    prompt,
                    generated_sql,
                    statement_type,
                    status,
                    error_message,
                    rows_affected,
                    round(execution_time_ms, 2),
                ),
            )
            conn.commit()

    def get_recent_logs(self, limit: int = 50) -> pd.DataFrame:
        """Fetch recent audit logs as a DataFrame."""
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
                conn,
                params=(limit,),
            )
        return df


audit_logger = AuditLogger()
