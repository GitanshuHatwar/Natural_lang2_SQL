
import pandas as pd
from sqlalchemy import create_engine, text, URL
from sqlalchemy.engine import Engine


def get_engine(host: str, port: int, user: str, password: str, database: str) -> Engine:
    """Create a SQLAlchemy engine and verify connectivity with SELECT 1."""
    url = URL.create(
        "mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))  # raises on failure
    return engine


def extract_schema(engine: Engine, database: str) -> str:
    """
    Return a compact schema string, one line per table, e.g.:
      Table customers(id INT PK, name VARCHAR(100))
    Queries INFORMATION_SCHEMA for columns and foreign keys.
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
    for table_name, col_name, col_type, col_key, _comment in cols:
        tables.setdefault(table_name, [])
        parts = [col_name, col_type.upper()]
        if col_key == "PRI":
            parts.append("PK")
        fk_ref = fk_map.get((table_name, col_name))
        if fk_ref:
            parts.append(f"FK->{fk_ref}")
        tables[table_name].append(" ".join(parts))

    lines = [f"Table {tbl}({', '.join(cols)})" for tbl, cols in tables.items()]
    return "\n".join(lines)


def run_query(engine: Engine, sql: str) -> pd.DataFrame:
    """
    Execute a SELECT/WITH query and return results as a DataFrame (max 1000 rows).
    Raises ValueError for non-SELECT statements or multiple statements.
    """
    cleaned = sql.strip().rstrip(";")

    upper = cleaned.upper()
    first_word = upper.split()[0] if upper.split() else ""
    if first_word not in ("SELECT", "WITH"):
        raise ValueError("Only SELECT queries are allowed.")
    if ";" in cleaned:
        raise ValueError("Only SELECT queries are allowed.")

    with engine.connect() as conn:
        df = pd.read_sql(text(cleaned), conn)

    if len(df) > 1000:
        df = df.iloc[:1000]
    return df
