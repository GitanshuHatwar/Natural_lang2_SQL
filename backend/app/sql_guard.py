import re


class GuardError(Exception):
    pass


_ALLOWED = "select, insert, update, delete, replace, create, alter, truncate, drop, rename"


def check_allowed_sql(sql: str) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise GuardError("SQL query is empty.")
    if ";" in cleaned:
        raise GuardError("Only one SQL statement is allowed.")
    if not re.match(r"^(select|with|insert|update|delete|replace|create|alter|truncate|drop|rename)\b", cleaned, re.IGNORECASE):
        raise GuardError(f"Only these SQL statements are allowed: {_ALLOWED}.")
    if re.match(r"^(create|alter|drop|rename)\s+(user|role)\b", cleaned, re.IGNORECASE):
        raise GuardError("User and role management statements are not allowed.")
    return cleaned


def is_select_statement(sql: str) -> bool:
    cleaned = check_allowed_sql(sql)
    return re.match(r"^(select|with)\b", cleaned, re.IGNORECASE) is not None
