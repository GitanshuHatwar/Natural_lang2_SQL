# NL2SQL

Ask your MySQL database questions in plain English. The app turns your question into SQL with a local Ollama model, lets you review and run it, shows the results, and can summarize or analyze them.

- **Backend:** FastAPI, SQLAlchemy, LangChain, SQLite (app history)
- **Frontend:** React, TypeScript, Tailwind (Vite)
- **Model:** runs locally through Ollama. No data leaves your machine.

## How it works

```
React UI  ──HTTP──▶  FastAPI backend ──▶ MySQL (your database, read-only user)
                          │
                          ├──▶ Ollama (local model)
                          └──▶ SQLite (connection history, metadata, chats)
```

1. **Connect:** enter host, port, database, username and password. Credentials stay in the backend's memory for the session and are never saved to disk.
2. **Extract (once per database):** the backend reads table structure, keys, value ranges, common values and a few sample rows, and stores that as text in SQLite.
3. **Ask:** your question plus the stored description of the database goes to the model, which returns a SQL query. **It is not run yet.**
4. **Review and run:** you can edit the SQL, then run it. Results appear as a table.
5. **Summarize / Analyze (optional):** the model explains the result in plain English, using statistics computed in code.

## Requirements

| Requirement | Version / notes |
|---|---|
| Python | 3.11+ |
| Node.js | 20+ |
| MySQL | 5.7.8+ or 8.x, with an existing database to query |
| Ollama | Latest, running locally (default `http://localhost:11434`) |
| Model | `qwen2.5-coder:7b` (about 5 GB download; plan for roughly 8 GB RAM, and a GPU makes it much faster) |

## Setup

### 1. MySQL: create a read-only user

This is the real safeguard against destructive queries. Do not connect as `root`.

```sql
CREATE USER 'nl2sql_ro'@'localhost' IDENTIFIED BY 'your_password';
GRANT SELECT ON your_db.* TO 'nl2sql_ro'@'localhost';
```

### 2. Ollama: install and pull the model

1. Install Ollama from https://ollama.com and make sure it is running.
2. Pull the model:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
3. Check it is available:
   ```bash
   ollama list
   ```

### 3. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check it: open http://127.0.0.1:8000/docs. You should see the 7 routes listed below.

Main settings in `backend/.env`:

| Setting | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Model used for SQL and summaries |
| `OLLAMA_NUM_CTX` | `8192` | Context window passed to Ollama (it silently truncates anything longer) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama runs |
| `RESULT_ROW_LIMIT` | `1000` | Maximum rows returned per query |
| `QUERY_TIMEOUT_SECONDS` | `30` | Maximum time per query |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend origin |
| `SQLITE_PATH` | `app.db` | App history database file |

### 4. Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env               # Windows: copy .env.example .env
npm run dev
```

Open **http://localhost:5173** (use `localhost`, not `127.0.0.1`, or the browser blocks requests to the backend).

`frontend/.env` contains `VITE_API_BASE_URL=http://127.0.0.1:8000`.

### 5. Use it

1. Go to **Connect**, enter your read-only user's details, and click **Connect**.
2. Click **Extract database** (or **Continue to chat** if it was extracted before).
3. In **Chat**, type a question and click **Generate SQL**.
4. Read the SQL, edit it if needed, and click **Run query**.
5. Click **Summarize** or **Analyze** to get a plain-English answer.

## Routes

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/connect` | Test credentials, start a session, record the connection (host, port, database only) |
| `GET` | `/connections` | List previous connections |
| `POST` | `/extract` | Explore the database and store its description |
| `POST` | `/generate-sql` | Turn a question into SQL (does not run it) |
| `POST` | `/execute` | Run the reviewed SQL and return rows |
| `POST` | `/summarize` | Summary or analysis of a query result |
| `GET` | `/connections/{id}/chats` | Chat history for a connection |

## Functionality

- Connect to a local MySQL database and remember previous connections
- One-time database exploration (tables, columns, keys, value ranges, common values, sample rows)
- Natural language to SQL, with your previous questions used as context for follow-ups
- Editable SQL and manual run; one automatic correction attempt if a generated query fails
- Results table with automatic row cap
- Summarize and analyze results in plain English
- Persistent history of questions, SQL, and summaries per connection

## What queries can be performed

**Read-only: `SELECT` and `WITH ... SELECT` only.** Anything else is rejected.

Questions you can ask:

- **Lookup and filter:** "Show orders from customer 57"
- **Aggregates:** counts, sums, averages, minimum and maximum
- **Grouping:** "Total sales per category", "Orders per month"
- **Sorting and top-N:** "Top 5 products by revenue"
- **Joins:** questions spanning several related tables
- **Dates:** "Signups in the last 30 days"
- **Text search:** "Customers whose name contains 'sharma'"
- **Subqueries and CTEs:** "Customers whose spend is above the average"
- **Window functions:** rankings and running totals (MySQL 8+)

Not supported, and rejected by the app: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, and multiple statements in one query.

## Things to know

- **Generated SQL can be wrong.** Local models guess column names and mix up joins, especially on complex questions. That is why SQL is shown and editable before anything runs.
- **Simple questions work best.** Single-table filters and aggregates are reliable. Multi-table joins and nested queries fail more often.
- **Limits:** results are capped at 1000 rows and queries at 30 seconds by default. Summaries of larger results cover only the first 1000 rows, and the UI says so.
- **Statistics are approximate:** extraction samples the first 10,000 rows of each table.
- **Re-extract after schema changes.** The stored description is not refreshed automatically.
- **Sessions are in memory.** Restarting the backend ends them. The app returns you to Connect, and you enter your credentials again.
- **MySQL only, local use.** This is a prototype: no login, and the backend listens only on `127.0.0.1`.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Cannot reach the backend" | Start the backend and check `VITE_API_BASE_URL` |
| Browser blocks requests (CORS) | Open the app at `http://localhost:5173`, not `127.0.0.1` |
| "Ollama is not reachable or the model is not available" | Start Ollama and run `ollama list` to confirm the model is pulled |
| "Run /extract first." | Click **Extract database** on the Connect page |
| Connection refused or access denied | Check host, port, and that the MySQL user has `SELECT` on the database |
| Slow answers | Normal on CPU. Try a smaller model via `OLLAMA_MODEL` |

## Project structure

```
backend/    FastAPI app (app/main.py, extractor, prompting, llm, executor, ...)
frontend/   React app (pages: Landing, Connect, Chat)
```
