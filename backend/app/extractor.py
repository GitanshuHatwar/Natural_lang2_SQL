from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from .config import settings

_NON_DISTINCT = {
    "tinyblob", "blob", "mediumblob", "longblob", "tinytext", "text", "mediumtext",
    "longtext", "json", "geometry", "point", "linestring", "polygon", "multipoint",
    "multilinestring", "multipolygon", "geometrycollection",
}
_RANGED = {
    "tinyint", "smallint", "mediumint", "int", "bigint", "decimal", "numeric", "float",
    "double", "date", "datetime", "timestamp", "time", "year",
}


def quote_identifier(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


def _scalar_text(value: Any, limit: int = 50) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return "<binary>"
    if isinstance(value, (date, datetime, time)):
        rendered = value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    elif isinstance(value, timedelta):
        rendered = str(value)
    elif isinstance(value, Decimal):
        rendered = str(value)
    else:
        rendered = str(value)
    return rendered[:limit]


def _display(value: Any) -> str:
    if value is None:
        return "NULL"
    return str(value)


def render_table(table: dict[str, Any], include_samples: bool = True) -> str:
    title = f"TABLE {table['name']} (~{table.get('approx_rows')} rows)"
    primary_key = table.get("primary_key", [])
    if primary_key:
        title += " PK: " + ", ".join(primary_key)
    if table.get("comment"):
        title += f" -- {table['comment']}"
    foreign_keys = {fk["column"]: fk for fk in table.get("foreign_keys", [])}
    lines = [title]
    for column in table.get("columns", []):
        line = f"  {column['name']} {column['type'].upper()}"
        fk = foreign_keys.get(column["name"])
        if fk:
            line += f" -> {fk['ref_table']}.{fk['ref_column']}"
        if column.get("values"):
            line += " values: " + ",".join(repr(value) for value in column["values"])
        if column.get("min") is not None or column.get("max") is not None:
            line += f" range: {_display(column.get('min'))} to {_display(column.get('max'))}"
        if column.get("comment"):
            line += f" -- {column['comment']}"
        lines.append(line)
    if include_samples:
        for sample in table.get("sample_rows", []):
            lines.append("  sample: (" + ", ".join("NULL" if value is None else repr(value) for value in sample) + ")")
    return "\n".join(lines)


def render_table_names_only(table: dict[str, Any]) -> str:
    return "TABLE " + table["name"] + ": " + ", ".join(column["name"] for column in table["columns"])


def extract_metadata(engine: Engine, database: str) -> dict[str, Any]:
    tables_sql = """
        SELECT TABLE_NAME AS table_name, TABLE_ROWS AS approx_rows, TABLE_COMMENT AS comment
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = :db AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME
    """
    columns_sql = """
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name, DATA_TYPE AS data_type,
               COLUMN_TYPE AS column_type, IS_NULLABLE AS is_nullable, COLUMN_KEY AS column_key,
               COLUMN_COMMENT AS comment
        FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = :db
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """
    foreign_keys_sql = """
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
               REFERENCED_TABLE_NAME AS ref_table, REFERENCED_COLUMN_NAME AS ref_column
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = :db AND REFERENCED_TABLE_NAME IS NOT NULL
    """
    with engine.connect() as conn:
        conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {settings.extract_query_timeout_seconds * 1000}")
        table_rows = [dict(row) for row in conn.execute(text(tables_sql), {"db": database}).mappings()]
        column_rows = [dict(row) for row in conn.execute(text(columns_sql), {"db": database}).mappings()]
        foreign_key_rows = [dict(row) for row in conn.execute(text(foreign_keys_sql), {"db": database}).mappings()]

        names = {row["table_name"] for row in table_rows}
        tables: dict[str, dict[str, Any]] = {
            row["table_name"]: {
                "name": row["table_name"], "approx_rows": row["approx_rows"], "comment": row["comment"] or "",
                "primary_key": [], "columns": [], "foreign_keys": [], "sample_rows": [],
            }
            for row in table_rows
        }
        columns_by_table: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
        for row in column_rows:
            if row["table_name"] not in names:
                continue
            column = {
                "name": row["column_name"], "type": row["column_type"], "nullable": row["is_nullable"] == "YES",
                "comment": row["comment"] or "", "data_type": row["data_type"].lower(),
                "column_key": row["column_key"], "distinct_count": None, "values": [], "min": None, "max": None,
            }
            tables[row["table_name"]]["columns"].append(column)
            columns_by_table[row["table_name"]].append(column)
            if row["column_key"] == "PRI":
                tables[row["table_name"]]["primary_key"].append(row["column_name"])
        for row in foreign_key_rows:
            if row["table_name"] in names:
                tables[row["table_name"]]["foreign_keys"].append({
                    "column": row["column_name"], "ref_table": row["ref_table"], "ref_column": row["ref_column"]
                })

        for name in (row["table_name"] for row in table_rows):
            table = tables[name]
            table_sql = quote_identifier(name)
            try:
                expressions = ["COUNT(*) AS sample_size"]
                distinct_columns: list[dict[str, Any]] = []
                ranged_columns: list[dict[str, Any]] = []
                for column in columns_by_table[name]:
                    identifier = quote_identifier(column["name"])
                    if column["data_type"] not in _NON_DISTINCT:
                        alias = len(distinct_columns)
                        expressions.append(f"COUNT(DISTINCT {identifier}) AS d{alias}")
                        distinct_columns.append(column)
                    if column["data_type"] in _RANGED:
                        alias = len(ranged_columns)
                        expressions.extend([f"MIN({identifier}) AS min{alias}", f"MAX({identifier}) AS max{alias}"])
                        ranged_columns.append(column)
                aggregate_sql = "SELECT " + ", ".join(expressions) + f" FROM (SELECT * FROM {table_sql} LIMIT {settings.extract_sample_rows}) AS s"
                aggregate = dict(conn.exec_driver_sql(aggregate_sql).mappings().one())
                for index, column in enumerate(distinct_columns):
                    column["distinct_count"] = aggregate.get(f"d{index}")
                for index, column in enumerate(ranged_columns):
                    column["min"] = _scalar_text(aggregate.get(f"min{index}"))
                    column["max"] = _scalar_text(aggregate.get(f"max{index}"))
                sample_size = aggregate.get("sample_size") or 0
            except DBAPIError:
                conn.rollback()
                sample_size = 0

            for column in columns_by_table[name]:
                if not (
                    column["data_type"] in {"char", "varchar", "enum", "set", "tinyint"}
                    and column["column_key"] not in {"PRI", "UNI"}
                    and column["distinct_count"] is not None
                    and column["distinct_count"] <= 20
                    and column["distinct_count"] < sample_size
                ):
                    continue
                try:
                    column_sql = quote_identifier(column["name"])
                    values_sql = f"SELECT DISTINCT {column_sql} FROM (SELECT {column_sql} FROM {table_sql} LIMIT {settings.extract_sample_rows}) AS s WHERE {column_sql} IS NOT NULL LIMIT 20"
                    column["values"] = [_scalar_text(row[0]) for row in conn.exec_driver_sql(values_sql).fetchall()]
                except DBAPIError:
                    conn.rollback()

            try:
                result = conn.exec_driver_sql(f"SELECT * FROM {table_sql} LIMIT 3")
                table["sample_rows"] = [[_scalar_text(value) for value in row] for row in result.fetchall()]
            except DBAPIError:
                conn.rollback()

    table_list = [tables[row["table_name"]] for row in table_rows]
    for table in table_list:
        for column in table["columns"]:
            column.pop("data_type", None)
            column.pop("column_key", None)
    return {"database": database, "tables": table_list}


def render_metadata(metadata: dict[str, Any]) -> str:
    return "\n\n".join(render_table(table) for table in metadata["tables"])
