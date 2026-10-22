"""LLM integration: generate SQL from natural language questions via Ollama."""

import os
import re
import requests
from typing import Optional, Any
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL") or "qwen2.5-coder:7b"
MODEL = DEFAULT_MODEL

_SYSTEM_PROMPT = """You are an expert MySQL database administrator and query generator.
Using ONLY the tables, columns, and data conventions present in the database schema below, generate ONE valid MySQL query to satisfy the user request.

Operational Rules:
1. READ REQUESTS (find, show, count, list, calculate):
   - Write a valid SELECT query.
   - Include LIMIT 100 unless an aggregate (COUNT, SUM, AVG) or explicit limit is specified.
2. INSERT REQUESTS (add, insert, create, register):
   - Write a valid INSERT INTO query specifying the target table, explicit column names, and appropriately formatted values.
3. UPDATE REQUESTS (update, edit, modify, change):
   - Write a valid UPDATE query with precise WHERE conditions.
4. DELETE REQUESTS (delete, remove):
   - Write a valid DELETE FROM query with precise WHERE conditions.
5. PROHIBITIONS:
   - NEVER generate DROP, TRUNCATE, ALTER, GRANT, or REVOKE queries.
   - Do NOT generate multiple queries or batch statements.
6. OUTPUT FORMAT:
   - Return ONLY the executable raw SQL query.
   - Do NOT include markdown code fences (no ```sql), explanations, commentary, or greetings.

SCHEMA:
{schema}"""


def get_available_models() -> list[str]:
    """Fetch locally installed models from Ollama's REST API."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2.0)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if models:
                return models
    except Exception:
        pass
    return [DEFAULT_MODEL]


def _get_llm(model_name: Optional[str] = None, temperature: float = 0.0) -> ChatOllama:
    chosen_model = model_name or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
    return ChatOllama(model=chosen_model, temperature=temperature)


def clean_sql_output(raw: str) -> str:
    """Strip markdown code fences, leading tags, and trailing spaces."""
    cleaned = re.sub(r"^```(?:sql)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    # Remove any stray comments at the start
    cleaned = re.sub(r"^--.*?\n", "", cleaned.strip())
    return cleaned.strip()


def generate_sql(
    schema: str,
    question: str,
    history: Optional[list[dict]] = None,
    model_name: Optional[str] = None,
) -> str:
    """
    Send schema + question + optional conversation history to Ollama and return a clean SQL string.
    """
    messages = [SystemMessage(content=_SYSTEM_PROMPT.format(schema=schema))]

    # Append recent conversation turns for multi-turn coreference resolution
    if history:
        for turn in history[-3:]:
            if "question" in turn and "sql" in turn:
                messages.append(HumanMessage(content=turn["question"]))
                messages.append(AIMessage(content=turn["sql"]))

    messages.append(HumanMessage(content=question))

    llm = _get_llm(model_name=model_name, temperature=0.0)
    response = llm.invoke(messages)
    return clean_sql_output(response.content)


def explain_sql(schema: str, sql: str, model_name: Optional[str] = None) -> str:
    """
    Provide a concise, friendly 1-2 sentence plain-English explanation
    of what the SQL query does and which tables/conditions it uses.
    """
    explain_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a helpful database teacher. Provide a concise, clear 1-2 sentence explanation
of what this SQL query calculates, displays, or modifies. Mention the key tables and filters in plain English.
Do not output SQL, code blocks, or preamble."""),
        ("human", """DATABASE SCHEMA:
{schema}

SQL QUERY:
{sql}""")
    ])
    chain = explain_prompt | _get_llm(model_name=model_name, temperature=0.0) | StrOutputParser()
    try:
        return chain.invoke({"schema": schema, "sql": sql}).strip()
    except Exception as e:
        return f"Executes query on active database ({e})"


def fix_sql(
    schema: str,
    failed_sql: str,
    error_message: str,
    question: str,
    model_name: Optional[str] = None,
) -> str:
    """
    Self-healing: Given a failed SQL query and the exact MySQL error message,
    prompts the LLM to analyze the schema and output a corrected query.
    """
    repair_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a MySQL debugging expert. You are provided with a database schema, the user's original request, a SQL query that failed to execute, and the exact MySQL database error message.

Your task is to fix the SQL query so that it successfully executes on MySQL without errors and correctly fulfills the user request.
Rules:
- Respect table names, column names, and foreign keys from the schema.
- Return ONLY the corrected raw SQL query. No explanations, no markdown fences."""),
        ("human", """DATABASE SCHEMA:
{schema}

ORIGINAL REQUEST:
{question}

FAILED SQL:
{failed_sql}

MYSQL ERROR MESSAGE:
{error_message}""")
    ])

    chain = repair_prompt | _get_llm(model_name=model_name, temperature=0.0) | StrOutputParser()
    raw = chain.invoke({
        "schema": schema,
        "question": question,
        "failed_sql": failed_sql,
        "error_message": error_message,
    })
    return clean_sql_output(raw)
