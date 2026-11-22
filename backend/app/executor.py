from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from .config import settings
from .sql_guard import check_select_only


class DatabaseError(Exception):
    pass


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, bytes):
        return "<binary>"
    return value


def run_select(engine: Engine, sql: str) -> tuple[list[str], list[list[Any]], bool]:
    cleaned = check_select_only(sql)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {settings.query_timeout_seconds * 1000}")
            result = conn.execution_options(no_parameters=True).exec_driver_sql(cleaned)
            records = result.fetchmany(settings.result_row_limit + 1)
            truncated = len(records) > settings.result_row_limit
            records = records[: settings.result_row_limit]
            return list(result.keys()), [[_json_value(value) for value in row] for row in records], truncated
    except DBAPIError as exc:
        raise DatabaseError(str(exc.orig)) from exc
