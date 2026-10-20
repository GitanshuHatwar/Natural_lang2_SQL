# NL2SQL — Natural Language to SQL

Turn plain-English questions into MySQL queries using a local Ollama model.

## Quick start

```bash
# 1. Install and start Ollama, then pull the default model
ollama pull qwen2.5-coder:7b

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Launch the app
streamlit run app.py
```

> **Optional:** set `OLLAMA_MODEL=<model-name>` before running to use a different model.

## Usage

1. Enter your MySQL host, port, user, password, and database name → **Connect**.
2. Click **Extract Database** to read the schema.
3. Type a question in plain English → **Generate SQL**.
4. Review (and edit) the generated SQL → **Execute**.

## Security note

Connect with a **read-only MySQL user** rather than `root`.  
Only `SELECT` and `WITH` queries are accepted — all others are rejected.  
Credentials are never written to disk; they live only in the browser session.
