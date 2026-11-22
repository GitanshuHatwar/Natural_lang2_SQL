from typing import Literal

from pydantic import BaseModel


class ConnectRequest(BaseModel):
    host: str = "localhost"
    port: int = 3306
    username: str
    password: str
    database: str


class ConnectResponse(BaseModel):
    session_id: str
    connection_id: int
    has_metadata: bool


class ConnectionResponse(BaseModel):
    id: int
    host: str
    port: int
    db_name: str
    last_used_at: str
    has_metadata: bool


class ExtractRequest(BaseModel):
    session_id: str


class ExtractResponse(BaseModel):
    connection_id: int
    table_count: int
    tables: list[str]
    extracted_at: str


class GenerateSQLRequest(BaseModel):
    session_id: str
    question: str


class GenerateSQLResponse(BaseModel):
    chat_id: int
    sql: str


class ExecuteRequest(BaseModel):
    session_id: str
    chat_id: int
    sql: str


class ExecuteResponse(BaseModel):
    chat_id: int
    sql: str
    retried: bool
    columns: list[str]
    rows: list[list[object]]
    row_count: int
    truncated: bool


class SummarizeRequest(BaseModel):
    session_id: str
    chat_id: int
    mode: Literal["summary", "analysis"]


class SummarizeResponse(BaseModel):
    summary_id: int
    mode: str
    text: str
    rows_analyzed: int
    truncated: bool


class SummaryResponse(BaseModel):
    id: int
    kind: str
    text: str
    created_at: str


class ChatResponse(BaseModel):
    id: int
    question: str
    generated_sql: str
    executed_sql: str | None
    row_count: int | None
    status: str
    error: str | None
    created_at: str
    summaries: list[SummaryResponse]
