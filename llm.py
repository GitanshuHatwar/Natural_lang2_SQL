"""LLM integration: generate SQL from a natural-language question via Ollama."""

import os
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")

_SYSTEM = """You are a MySQL expert. Using ONLY the tables and columns in the schema below, \
write ONE read-only SELECT query that answers the user's question.
Rules:
- Return only the SQL. No explanation, no markdown fences.
- Use only columns that exist in the schema.
- Add LIMIT 100 unless the question asks for an aggregate or a full count.

SCHEMA:
{schema}"""

_prompt = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", "{question}"),
])

_chain = _prompt | ChatOllama(model=MODEL, temperature=0) | StrOutputParser()


def generate_sql(schema: str, question: str) -> str:
    """Send schema + question to Ollama and return a clean SQL string."""
    raw: str = _chain.invoke({"schema": schema, "question": question})
    # Strip markdown code fences if the model includes them anyway
    cleaned = re.sub(r"^```(?:sql)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()
