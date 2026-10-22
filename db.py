import time
import json
from typing import Any, Optional
import pandas as pd
import sqlparse
import sqlglot
from sqlglot import exp
import networkx as nx
from sqlalchemy import create_engine, text, URL
from sqlalchemy.engine import Engine

from security import mask_sample_row, audit_logger


def get_engine(host: str, port: int, user: str, password: str, database: Optional[str] = None) -> Engine:
    """Create a SQLAlchemy engine with timeouts and verify connectivity."""
    url = URL.create(
        "mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database or "",
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
            # Set server-side SELECT execution timeout to 15 seconds (MySQL 8.0+)
            conn.execute(text("SET SESSION max_execution_time = 15000"))
        except Exception:
            pass
        conn.execute(text("SELECT 1"))
    return engine


def get_available_databases(engine: Engine) -> list[str]:
    """Fetch user-accessible databases, filtering out internal MySQL system schemas."""
    system_schemas = {"information_schema", "performance_schema", "mysql", "sys"}
    with engine.connect() as conn:
        result = conn.execute(text("SHOW DATABASES")).fetchall()
        dbs = [row[0] for row in result if row[0].lower() not in system_schemas]
    return sorted(dbs)


def extract_schema(engine: Engine, database: str) -> str:
    """
    Return an enriched schema string with column types, primary keys, foreign keys,
    comments, categorical distinct values, relationship graphs, and PII-masked sample rows.
    """
    col_query = text("""
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY, COLUMN_COMMENT, DATA_TYPE
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

    # Build relationship graph using NetworkX
    graph = nx.DiGraph()
    relationships: list[str] = []
    fk_map: dict[tuple[str, str], str] = {}

    for tbl, col, ref_tbl, ref_col in fks:
        fk_map[(tbl, col)] = f"{ref_tbl}.{ref_col}"
        graph.add_edge(tbl, ref_tbl, label=f"{col}->{ref_col}")
        relationships.append(f"{tbl}.{col} -> {ref_tbl}.{ref_col}")

    # Group columns by table
    tables: dict[str, list[dict[str, str]]] = {}
    for table_name, col_name, col_type, col_key, comment, data_type in cols:
        tables.setdefault(table_name, [])
        tables[table_name].append({
            "name": col_name,
            "type": col_type.upper(),
            "key": col_key,
            "comment": comment or "",
            "data_type": data_type.lower()
        })

    lines: list[str] = []

    with engine.connect() as conn:
        for tbl, col_list in tables.items():
            formatted_cols = []
            col_names = []
            for col in col_list:
                c_name = col["name"]
                col_names.append(c_name)
                parts = [c_name, col["type"]]
                if col["key"] == "PRI":
                    parts.append("PK")
                fk_ref = fk_map.get((tbl, c_name))
                if fk_ref:
                    parts.append(f"FK->{fk_ref}")
                if col["comment"]:
                    parts.append(f"COMMENT '{col['comment']}'")
                formatted_cols.append(" ".join(parts))

            lines.append(f"Table {tbl}({', '.join(formatted_cols)})")

            # Extract distinct categorical values for ENUMs or low-cardinality columns
            for col in col_list:
                if "ENUM" in col["type"] or col["data_type"] in ("varchar", "char"):
                    try:
                        distinct_rows = conn.execute(
                            text(f"SELECT DISTINCT `{col['name']}` FROM `{tbl}` WHERE `{col['name']}` IS NOT NULL LIMIT 10")
                        ).fetchall()
                        if 1 < len(distinct_rows) <= 8:
                            values = [str(r[0]) for r in distinct_rows]
                            lines.append(f"  Column '{col['name']}' sample values: {values}")
                    except Exception:
                        pass

            # Fetch up to 2 PII-masked sample rows
            try:
                samples = conn.execute(text(f"SELECT * FROM `{tbl}` LIMIT 2")).fetchall()
                if samples:
                    masked_samples = []
                    for row in samples:
                        masked_row = mask_sample_row(col_names, tuple(row))
                        masked_samples.append(str(tuple(str(item) for item in masked_row)))
                    lines.append(f"  Sample records: {'; '.join(masked_samples)}")
            except Exception:
                pass

    if relationships:
        lines.append("\nTable Relationships (Foreign Keys):")
        for rel in relationships:
            lines.append(f"  - {rel}")

    return "\n".join(lines)


def validate_and_transform_sql(sql: str) -> tuple[str, str]:
    """
    Validates and transforms the SQL query using sqlparse and sqlglot.
    - Enforces single statement
    - Requires WHERE clauses on UPDATE and DELETE to prevent whole-table overwrites
    - Automatically appends LIMIT 100 on unbounded SELECT queries
    - Blocks dangerous DDL (DROP, TRUNCATE, ALTER, GRANT, REVOKE)
    - Returns (canonical_sql, category) where category is 'DQL' or 'DML'
    """
    raw = sql.strip()
    if not raw:
        raise ValueError("Empty SQL query provided.")

    # 1. Statement splitting & multi-statement check
    statements = [s.strip() for s in sqlparse.split(raw) if s.strip()]
    if len(statements) > 1:
        raise ValueError("Security Violation: Multiple SQL statements detected. Batch execution is prohibited.")

    cleaned_sql = statements[0].rstrip(";")

    # 2. Block prohibited DDL commands
    parsed_parse = sqlparse.parse(cleaned_sql)
    if not parsed_parse:
        raise ValueError("Could not parse SQL statement.")

    stmt_type = parsed_parse[0].get_type().upper()
    first_token = parsed_parse[0].token_first(skip_ws=True, skip_cm=True)
    first_word = first_token.value.upper() if first_token else ""

    disallowed = ("DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE", "RENAME")
    if stmt_type in disallowed or first_word in disallowed:
        raise ValueError(f"Security Violation: '{stmt_type or first_word}' statements are prohibited.")

    # 3. Deep AST analysis and transformation via sqlglot
    try:
        ast = sqlglot.parse_one(cleaned_sql, read="mysql")
    except Exception as e:
        # Fallback to sqlparse classification if sqlglot dialect parse encounters custom tokens
        if stmt_type in ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN") or first_word == "WITH":
            return cleaned_sql, "DQL"
        elif stmt_type in ("INSERT", "UPDATE", "DELETE"):
            return cleaned_sql, "DML"
        raise ValueError(f"Invalid SQL syntax: {e}")

    # Enforce mandatory WHERE clause on UPDATE and DELETE
    if isinstance(ast, (exp.Update, exp.Delete)):
        if ast.find(exp.Where) is None:
            raise ValueError(
                f"Safety Guard: {stmt_type or first_word} operations must include a WHERE clause to prevent catastrophic data loss."
            )
        return ast.sql(dialect="mysql"), "DML"

    if isinstance(ast, exp.Insert):
        return ast.sql(dialect="mysql"), "DML"

    if isinstance(ast, exp.Select):
        # Auto-append LIMIT 100 if missing and not an aggregation
        has_agg = any(isinstance(node, (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)) for node in ast.find_all(exp.Func))
        if ast.find(exp.Limit) is None and not has_agg:
            ast = ast.limit(100)
        return ast.sql(dialect="mysql"), "DQL"

    # Catch other read-only statement types
    if stmt_type in ("SELECT", "SHOW", "DESCRIBE", "EXPLAIN") or first_word == "WITH":
        return cleaned_sql, "DQL"

    raise ValueError(f"Unsupported statement type: '{stmt_type or first_word}'. Only SELECT, INSERT, UPDATE, and DELETE are permitted.")


def analyze_query_cost(engine: Engine, sql: str) -> dict[str, Any]:
    """
    Executes EXPLAIN FORMAT=JSON for read queries to analyze execution cost and scan volume.
    Returns metrics and safety warnings.
    """
    result = {
        "query_cost": 0.0,
        "rows_examined": 0,
        "has_full_scan": False,
        "warning": None,
        "summary": "Explain plan unavailable"
    }
    try:
        with engine.connect() as conn:
            explain_raw = conn.execute(text(f"EXPLAIN FORMAT=JSON {sql}")).scalar()
            if not explain_raw:
                return result
            plan = json.loads(explain_raw)

        q_block = plan.get("query_block", {})
        cost = float(q_block.get("cost_info", {}).get("query_cost", 0.0))
        result["query_cost"] = round(cost, 2)

        # Traverse nested loop or table info
        tables = []
        if "nested_loop" in q_block:
            for item in q_block["nested_loop"]:
                if "table" in item:
                    tables.append(item["table"])
        elif "table" in q_block:
            tables.append(q_block["table"])

        total_rows = 0
        has_full_scan = False
        table_summaries = []

        for tbl in tables:
            t_name = tbl.get("table_name", "unknown")
            access_type = tbl.get("access_type", "unknown")
            rows = int(tbl.get("rows_examined_per_scan", 0))
            total_rows += rows
            if access_type.upper() == "ALL":
                has_full_scan = True
            table_summaries.append(f"{t_name} (access: {access_type}, rows: {rows:,})")

        result["rows_examined"] = total_rows
        result["has_full_scan"] = has_full_scan
        result["summary"] = f"Cost: {cost:.2f} | Scanned rows: {total_rows:,} | " + ", ".join(table_summaries)

        if total_rows > 100000:
            result["warning"] = f"Heavy query detected: Scans {total_rows:,} rows."

    except Exception as exc:
        result["summary"] = f"Could not compute EXPLAIN plan: {exc}"

    return result


def run_query(engine: Engine, sql: str, username: str = "appuser", database: str = "") -> dict[str, Any]:
    """
    Validate, measure, and execute a SQL statement with audit logging.
    - DQL (SELECT): Returns DataFrame, cost metrics, and execution latency.
    - DML (INSERT/UPDATE/DELETE): Executes in a transaction and returns affected rows.
    """
    start_time = time.perf_counter()
    status = "SUCCESS"
    err_msg = None
    affected_rows = 0

    try:
        cleaned_sql, category = validate_and_transform_sql(sql)

        if category == "DQL":
            # Perform query cost analysis
            cost_info = analyze_query_cost(engine, cleaned_sql)

            with engine.connect() as conn:
                df = pd.read_sql(text(cleaned_sql), conn)

            affected_rows = len(df)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            audit_logger.log(
                username=username,
                database_name=database,
                prompt=cleaned_sql,
                generated_sql=cleaned_sql,
                statement_type="DQL",
                status="SUCCESS",
                rows_affected=affected_rows,
                execution_time_ms=elapsed_ms,
            )

            return {
                "type": "DQL",
                "sql": cleaned_sql,
                "data": df,
                "rows": len(df),
                "cost_info": cost_info,
                "latency_ms": round(elapsed_ms, 2),
            }

        # Category is DML (INSERT / UPDATE / DELETE)
        with engine.begin() as conn:
            exec_res = conn.execute(text(cleaned_sql))
            affected_rows = exec_res.rowcount

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        audit_logger.log(
            username=username,
            database_name=database,
            prompt=cleaned_sql,
            generated_sql=cleaned_sql,
            statement_type="DML",
            status="SUCCESS",
            rows_affected=affected_rows,
            execution_time_ms=elapsed_ms,
        )

        return {
            "type": "DML",
            "sql": cleaned_sql,
            "rows_affected": affected_rows,
            "message": f"Successfully executed operation ({affected_rows} row(s) affected).",
            "latency_ms": round(elapsed_ms, 2),
        }

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        audit_logger.log(
            username=username,
            database_name=database,
            prompt=sql,
            generated_sql=sql,
            statement_type="UNKNOWN",
            status="ERROR",
            error_message=str(exc),
            execution_time_ms=elapsed_ms,
        )
        raise exc
