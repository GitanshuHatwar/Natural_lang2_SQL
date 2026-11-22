import json
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .config import settings
from .executor import DatabaseError, run_select
from .extractor import extract_metadata, render_metadata
from .llm import clean_sql, fix_sql, generate_sql, summarize_result
from .prompting import build_schema_context, history_block
from .schemas import (
    ChatResponse, ConnectRequest, ConnectResponse, ConnectionResponse, ExecuteRequest,
    ExecuteResponse, ExtractRequest, ExtractResponse, GenerateSQLRequest, GenerateSQLResponse,
    SummarizeRequest, SummarizeResponse,
)
from .sessions import Session, create_session, get_session, make_engine
from .sql_guard import GuardError
from .storage import (
    chats_with_summaries, create_chat, create_summary, executed_history, get_chat, get_connection,
    get_schema_cache, has_metadata, init_db, list_connections, mark_chat_error, mark_chat_executed,
    save_schema_cache, upsert_connection, utc_now,
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


def _session_or_401(session_id: str) -> Session:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(401, "Session not found. Reconnect.")
    return session


def _chat_for_session(chat_id: int, session: Session) -> dict[str, Any]:
    chat = get_chat(chat_id)
    if chat is None or chat["connection_id"] != session.connection_id:
        raise HTTPException(404, "Chat not found.")
    return chat


def _statistics(columns: list[str], rows: list[list[Any]]) -> tuple[str, str]:
    frame = pd.DataFrame(rows, columns=columns)
    lines = [f"Total rows analyzed: {len(frame)}"]
    for index, column in enumerate(columns):
        series = frame.iloc[:, index]
        lines.append(f"{column}: null count={int(series.isna().sum())}")
        if pd.api.types.is_numeric_dtype(series):
            lines.append(
                f"  min={series.min()} max={series.max()} mean={series.mean()} sum={series.sum()}"
            )
        else:
            values = series.dropna()
            lines.append(f"  distinct count={int(values.nunique())}")
            top = values.value_counts().head(5)
            if not top.empty:
                lines.append("  top values: " + ", ".join(f"{value!s} ({count})" for value, count in top.items()))
    sample = frame.head(settings.summary_sample_rows).copy()
    for column_index in range(len(sample.columns)):
        sample.iloc[:, column_index] = sample.iloc[:, column_index].map(
            lambda value: value if pd.isna(value) else str(value)[:100]
        )
    return "\n".join(lines), sample.to_csv(index=False)


@app.post("/connect", response_model=ConnectResponse)
def connect(request: ConnectRequest) -> dict[str, Any]:
    engine = make_engine(request.username, request.password, request.host, request.port, request.database)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except DBAPIError as exc:
        engine.dispose()
        raise HTTPException(400, str(exc.orig)) from exc
    connection_id = upsert_connection(request.host, request.port, request.database)
    session_id = create_session(engine, connection_id, request.database)
    return {"session_id": session_id, "connection_id": connection_id, "has_metadata": has_metadata(connection_id)}


@app.get("/connections", response_model=list[ConnectionResponse])
def connections() -> list[dict[str, Any]]:
    return list_connections()


@app.post("/extract", response_model=ExtractResponse)
def extract(request: ExtractRequest) -> dict[str, Any]:
    session = _session_or_401(request.session_id)
    try:
        metadata = extract_metadata(session.engine, session.database)
    except DBAPIError as exc:
        raise HTTPException(400, str(exc.orig)) from exc
    metadata_text = render_metadata(metadata)
    extracted_at = utc_now()
    save_schema_cache(session.connection_id, json.dumps(metadata), metadata_text, extracted_at)
    tables = [table["name"] for table in metadata["tables"]]
    return {"connection_id": session.connection_id, "table_count": len(tables), "tables": tables, "extracted_at": extracted_at}


@app.post("/generate-sql", response_model=GenerateSQLResponse)
def generate(request: GenerateSQLRequest) -> dict[str, Any]:
    session = _session_or_401(request.session_id)
    cache = get_schema_cache(session.connection_id)
    if cache is None:
        raise HTTPException(400, "Run /extract first.")
    metadata = json.loads(cache["metadata_json"])
    schema_context = build_schema_context(metadata, cache["metadata_text"], request.question)
    history = history_block(executed_history(session.connection_id, settings.history_pairs))
    sql = clean_sql(generate_sql(schema_context, history, request.question))
    chat_id = create_chat(session.connection_id, request.question, sql)
    return {"chat_id": chat_id, "sql": sql}


@app.post("/execute", response_model=ExecuteResponse)
def execute(request: ExecuteRequest) -> dict[str, Any]:
    session = _session_or_401(request.session_id)
    chat = _chat_for_session(request.chat_id, session)
    retried = False
    sql_that_ran = request.sql
    try:
        columns, rows, truncated = run_select(session.engine, sql_that_ran)
    except GuardError as exc:
        mark_chat_error(chat["id"], str(exc))
        raise HTTPException(400, str(exc)) from exc
    except DatabaseError as exc:
        error = str(exc)
        if request.sql.strip() != chat["generated_sql"].strip():
            mark_chat_error(chat["id"], error)
            raise HTTPException(400, error) from exc
        cache = get_schema_cache(session.connection_id)
        if cache is None:
            mark_chat_error(chat["id"], error)
            raise HTTPException(400, error) from exc
        schema_context = build_schema_context(json.loads(cache["metadata_json"]), cache["metadata_text"], chat["question"])
        sql_that_ran = clean_sql(fix_sql(schema_context, chat["question"], request.sql, error))
        retried = True
        try:
            columns, rows, truncated = run_select(session.engine, sql_that_ran)
        except (GuardError, DatabaseError) as retry_exc:
            message = str(retry_exc)
            mark_chat_error(chat["id"], message)
            raise HTTPException(400, message) from retry_exc
    mark_chat_executed(chat["id"], sql_that_ran, len(rows))
    return {
        "chat_id": chat["id"], "sql": sql_that_ran, "retried": retried, "columns": columns,
        "rows": rows, "row_count": len(rows), "truncated": truncated,
    }


@app.post("/summarize", response_model=SummarizeResponse)
def summarize(request: SummarizeRequest) -> dict[str, Any]:
    session = _session_or_401(request.session_id)
    chat = _chat_for_session(request.chat_id, session)
    if chat["executed_sql"] is None:
        raise HTTPException(400, "Execute the query first.")
    try:
        columns, rows, truncated = run_select(session.engine, chat["executed_sql"])
    except (GuardError, DatabaseError) as exc:
        raise HTTPException(400, str(exc)) from exc
    stats_block, sample_csv = _statistics(columns, rows)
    mode_instruction = (
        "Answer the user's question in plain English in 2-5 sentences."
        if request.mode == "summary"
        else "Describe notable patterns, comparisons, trends and outliers visible in the data as a short bullet list. Do not speculate about causes the data does not show."
    )
    truncated_note = f", the result was cut at {settings.result_row_limit} rows" if truncated else ""
    text_result = summarize_result(
        mode_instruction, chat["question"], chat["executed_sql"], len(rows), truncated_note,
        stats_block, min(len(rows), settings.summary_sample_rows), sample_csv,
    )
    summary_id = create_summary(chat["id"], request.mode, text_result)
    return {"summary_id": summary_id, "mode": request.mode, "text": text_result, "rows_analyzed": len(rows), "truncated": truncated}


@app.get("/connections/{connection_id}/chats", response_model=list[ChatResponse])
def connection_chats(connection_id: int) -> list[dict[str, Any]]:
    if get_connection(connection_id) is None:
        raise HTTPException(404, "Connection not found.")
    return chats_with_summaries(connection_id)
