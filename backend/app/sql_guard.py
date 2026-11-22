import re


class GuardError(Exception):
    pass


def check_select_only(sql: str) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise GuardError("SQL query is empty.")
    if ";" in cleaned:
        raise GuardError("Only one SQL statement is allowed.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise GuardError("Only SELECT queries are allowed.")
    return cleaned
