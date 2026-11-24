import re
from typing import Any

from .config import settings
from .extractor import render_table, render_table_names_only


def _words(value: str) -> set[str]:
    return {word[:-1] if word.endswith("s") else word for word in re.findall(r"[a-z0-9]{3,}", value.lower())}


def build_schema_context(metadata_json: dict[str, Any], metadata_text: str, question: str) -> str:
    if len(metadata_text) <= settings.metadata_max_chars:
        return metadata_text
    question_words = _words(question)
    tables = metadata_json["tables"]
    relevant = {
        table["name"] for table in tables
        if question_words & (_words(table["name"]) | set().union(*(_words(column["name"]) for column in table["columns"])))
    }
    for table in tables:
        for foreign_key in table.get("foreign_keys", []):
            if table["name"] in relevant or foreign_key["ref_table"] in relevant:
                relevant.add(table["name"])
                relevant.add(foreign_key["ref_table"])
    context = "\n\n".join(
        render_table(table) if table["name"] in relevant else render_table_names_only(table) for table in tables
    )
    if len(context) > settings.metadata_max_chars:
        context = "\n\n".join(
            render_table(table, include_samples=False) if table["name"] in relevant else render_table_names_only(table)
            for table in tables
        )
    return context


def history_block(history: list[dict[str, Any]]) -> str:
    if not history:
        return ""
    return "".join(f"Q: {item['question']}\nSQL: {item['executed_sql']}\n" for item in history) + "\n"
