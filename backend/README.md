# NL → SQL backend

## Setup and run

Use Python 3.11 or later. From the `backend` directory, create and activate a virtual environment, install dependencies, then copy `.env.example` to `.env` if you need to change defaults.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The server is deliberately bound only to `127.0.0.1`; `/connect` receives MySQL credentials. Startup creates `app.db` and its four storage tables. Ollama must be running locally and the configured model must be available. Use a MySQL account with only the permissions needed for the operations you intend to run.

## Routes

- `POST /connect` — validate a MySQL connection and create an in-memory session.
- `GET /connections` — list prior credential-free connection records.
- `POST /extract` — profile the connected database and cache schema metadata.
- `POST /generate-sql` — turn a question into SQL without executing it.
- `POST /execute` — run user-reviewed permitted SQL (SELECT, row changes, and schema changes).
- `POST /summarize` — summarize or analyze an executed query by re-running it.
- `GET /connections/{connection_id}/chats` — read persisted chat and summary history.

Interactive request shapes are available at `http://127.0.0.1:8000/docs` while the server is running.

# working 
/connect
  → tests MySQL credentials
  → saves credential-free connection history
  → creates an in-memory session

/extract
  → reads MySQL schema and samples
  → saves metadata in SQLite

/generate-sql
  → sends question + schema context to Ollama
  → stores generated SQL, but does not execute it

/execute
  → validates SELECT-only SQL
  → runs it against MySQL
  → retries once with Ollama only if unedited generated SQL fails

/summarize
  → re-runs executed SQL
  → computes pandas statistics
  → asks Ollama to explain the supplied results
