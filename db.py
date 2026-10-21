import pandas as pd
import sqlparse
from sqlalchemy import create_engine, text, URL
from sqlalchemy.engine import Engine
from typing import Any


def get_engine(host: str, port: int, user: str, password: str, database: str) -> Engine:
    """Create a SQLAlchemy engine with timeouts and verify connectivity."""
    url = URL.create(
        "mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "read_timeout": 15,
            "write_timeout": 15,
            "connect_timeout": 10,
        },
        execution_options={"timeout": 15},
    )
    with engine.connect() as conn:
        try:
            # Set server-side SELECT query execution timeout to 15 seconds (MySQL 8.0+)
            conn.execute(text("SET SESSION max_execution_time = 15000"))
        except Exception:
            pass
        conn.execute(text("SELECT 1"))  # raises on connection failure
    return engine


def extract_schema(engine: Engine, database: str) -> str:
    """
    Return an enriched schema string with column types, primary keys, foreign keys,
    comments, and 2 sample rows per table to ground LLM query generation.
    """
    col_query = text("""
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY, COLUMN_COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = :db
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """)

    fk_query = text("""
        SELECT TABLE_NAME, COLUMN_NAME,
               REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = :db
          AND REFERENCED_TABLE_NAME IS NOT NULL
    """)

    with engine.connect() as conn:
        cols = conn.execute(col_query, {"db": database}).fetchall()
        fks = conn.execute(fk_query, {"db": database}).fetchall()

    # Build FK lookup: (table, column) -> "ref_table.ref_col"
    fk_map: dict[tuple[str, str], str] = {
        (row[0], row[1]): f"{row[2]}.{row[3]}" for row in fks
    }

    # Group columns by table
    tables: dict[str, list[str]] = {}
    for table_name, col_name, col_type, col_key, comment in cols:
        tables.setdefault(table_name, [])
        parts = [col_name, col_type.upper()]
        if col_key == "PRI":
            parts.append("PK")
        fk_ref = fk_map.get((table_name, col_name))
        if fk_ref:
            parts.append(f"FK->{fk_ref}")
        if comment:
            parts.append(f"COMMENT '{comment}'")
        tables[table_name].append(" ".join(parts))

    lines: list[str] = []
    with engine.connect() as conn:
        for tbl, col_list in tables.items():
            lines.append(f"Table {tbl}({', '.join(col_list)})")
            # Fetch up to 2 sample rows to provide formatting context
            try:
                samples = conn.execute(text(f"SELECT * FROM `{tbl}` LIMIT 2")).fetchall()
                if samples:
                    sample_strs = [str(tuple(str(item) for item in row)) for row in samples]
                    lines.append(f"  Sample rows: {'; '.join(sample_strs)}")
            except Exception:
                pass

    return "\n".join(lines)


def validate_and_classify_sql(sql: str) -> tuple[str, str]:
    """
    Parses and validates the SQL query using sqlparse.
    Rejects multi-statement queries, dangerous DDL (DROP, TRUNCATE, ALTER),
    and categorizes the query as 'DQL' or 'DML'.
    """
    raw = sql.strip()
    if not raw:
        raise ValueError("Empty SQL query provided.")

    statements = [s.strip() for s in sqlparse.split(raw) if s.strip()]
    if len(statements) > 1:
        raise ValueError("Multiple SQL statements detected. Only a single query can be executed at a time.")

    cleaned_sql = statements[0].rstrip(";")
    parsed = sqlparse.parse(cleaned_sql)
    if not parsed:
        raise ValueError("Could not parse SQL statement.")

    stmt_type = parsed[0].get_type().upper()

    # Read-only query types
    if stmt_type in ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN"):
        return cleaned_sql, "DQL"

    # Common Table Expressions starting with WITH
    first_token = parsed[0].token_first(skip_ws=True, skip_cm=True)
    first_word = first_token.value.upper() if first_token else ""
    if first_word == "WITH":
        return cleaned_sql, "DQL"

    # Mutation query types
    if stmt_type in ("INSERT", "UPDATE", "DELETE"):
        return cleaned_sql, "DML"

    # Disallow destructive DDL / Administrative commands
    disallowed = ("DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE", "RENAME")
    if stmt_type in disallowed or first_word in disallowed:
        raise ValueError(f"Execution of '{stmt_type or first_word}' statements is prohibited for database safety.")

    raise ValueError(f"Unsupported statement type: '{stmt_type or first_word}'. Only SELECT, INSERT, UPDATE, and DELETE are permitted.")


def run_query(engine: Engine, sql: str) -> dict[str, Any]:
    """
    Validate and execute a SQL statement.
    - DQL (SELECT/WITH): Returns a dictionary with the DataFrame and row count.
    - DML (INSERT/UPDATE/DELETE): Executes in a transaction, commits, and returns affected rows.
    """
    cleaned_sql, category = validate_and_classify_sql(sql)

    if category == "DQL":
        with engine.connect() as conn:
            df = pd.read_sql(text(cleaned_sql), conn)
        if len(df) > 1000:
            df = df.iloc[:1000]
        return {
            "type": "DQL",
            "sql": cleaned_sql,
            "data": df,
            "rows": len(df),
        }

    # Category is DML (INSERT / UPDATE / DELETE)
    with engine.begin() as conn:
        result = conn.execute(text(cleaned_sql))
        affected = result.rowcount

    return {
        "type": "DML",
        "sql": cleaned_sql,
        "rows_affected": affected,
        "message": f"Successfully executed operation ({affected} row(s) affected).",
    }
