import streamlit as st

from db import get_engine, extract_schema, run_query
from llm import generate_sql

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="NL2SQL", page_icon="🗄️", layout="wide")
st.title("🗄️ NL2SQL — Natural Language to SQL")

# ── Sidebar: connection status + disconnect ───────────────────────────────────
with st.sidebar:
    st.header("Connection")
    if st.session_state.get("engine"):
        st.success(f"Connected to **{st.session_state['database']}**")
        if st.button("Disconnect"):
            for key in ["engine", "database", "schema", "sql"]:
                st.session_state.pop(key, None)
            st.rerun()
    else:
        st.info("Not connected")

# ── Step 1: Connect ───────────────────────────────────────────────────────────
if not st.session_state.get("engine"):
    st.subheader("Step 1 — Connect to MySQL")
    with st.form("connect_form"):
        host = st.text_input("Host", value="localhost")
        port = st.number_input("Port", value=3306, step=1, min_value=1, max_value=65535)
        user = st.text_input("User", value="root")
        password = st.text_input("Password", type="password")
        database = st.text_input("Database")
        submitted = st.form_submit_button("Connect")

    if submitted:
        try:
            engine = get_engine(host, int(port), user, password, database)
            st.session_state["engine"] = engine
            st.session_state["database"] = database
            st.success("Connection established successfully")
            st.rerun()
        except Exception as exc:
            st.error(f"Connection failed: {exc}")
    st.stop()

# ── Step 2: Extract schema ────────────────────────────────────────────────────
if not st.session_state.get("schema"):
    st.subheader("Step 2 — Extract Database Schema")
    if st.button("Extract Database"):
        try:
            with st.spinner("Reading schema from INFORMATION_SCHEMA…"):
                schema = extract_schema(
                    st.session_state["engine"],
                    st.session_state["database"],
                )
            st.session_state["schema"] = schema
            st.rerun()
        except Exception as exc:
            st.error(f"Schema extraction failed: {exc}")
    st.stop()

# Show schema summary in an expander
with st.expander("📋 Schema summary", expanded=False):
    st.code(st.session_state["schema"], language="text")

# ── Step 3 + 4: Ask + Review generated SQL ───────────────────────────────────
st.subheader("Step 3 — Ask a Question")
question = st.text_input("Natural-language question", placeholder="e.g. How many orders were placed last month?")

if st.button("Generate SQL", disabled=not question.strip()):
    try:
        with st.spinner("Generating SQL…"):
            sql = generate_sql(st.session_state["schema"], question)
        st.session_state["sql"] = sql
    except Exception as exc:
        st.error(f"SQL generation failed: {exc}")

if st.session_state.get("sql"):
    st.subheader("Step 4 — Review & Execute")
    edited_sql = st.text_area("Generated SQL (editable)", value=st.session_state["sql"], height=150)

    if st.button("▶ Execute"):
        try:
            with st.spinner("Running query…"):
                df = run_query(st.session_state["engine"], edited_sql)
            st.dataframe(df, use_container_width=True)
            st.caption(f"{len(df):,} row(s) returned" + (" (capped at 1 000)" if len(df) == 1000 else ""))
        except ValueError as ve:
            st.error(str(ve))
        except Exception as exc:
            st.error(f"Query failed: {exc}")
