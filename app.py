import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from db import get_engine, extract_schema, run_query, validate_and_classify_sql
from llm import generate_sql, fix_sql, MODEL

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NL2SQL AI Copilot",
    page_icon="💬",
    layout="wide"
)

# ── Toast Helpers ────────────────────────────────────────────────────────────
def error_toast(message: str):
    """Display a custom error toast in the UI."""
    st.toast(f"❌ {message}", icon="🚨")

def success_toast(message: str):
    """Display a custom success toast in the UI."""
    st.toast(f"{message}", icon="✅")

def warning_toast(message: str):
    """Display a custom warning toast in the UI."""
    st.toast(f"{message}", icon="⚠️")


# ── Session State Initialization ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "engine" not in st.session_state:
    st.session_state["engine"] = None
if "schema" not in st.session_state:
    st.session_state["schema"] = None
if "database" not in st.session_state:
    st.session_state["database"] = None


# ── Sidebar Controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🤖 NL2SQL Copilot")
    active_model = os.environ.get("OLLAMA_MODEL") or MODEL
    st.caption(f"🧠 **Model:** `{active_model}` (Local Ollama)")

    st.divider()
    st.subheader("🔌 Connection Status")

    if st.session_state["engine"]:
        st.success(f"Connected to **{st.session_state['database']}**")
        if st.button("🔌 Disconnect Database", width="stretch"):
            for key in ["engine", "database", "schema", "messages"]:
                st.session_state[key] = None if key != "messages" else []
            success_toast("Disconnected from database.")
            st.rerun()

        st.divider()
        st.subheader("💬 Chat Options")
        if st.session_state["messages"]:
            if st.button("🗑️ Clear Conversation", width="stretch"):
                st.session_state["messages"] = []
                success_toast("Chat history cleared.")
                st.rerun()
    else:
        st.info("Not connected to MySQL.")


# ── Step 1: Connect to Database ──────────────────────────────────────────────
if not st.session_state["engine"]:
    st.title("🗄️ NL2SQL AI Copilot")
    st.markdown("Connect to your MySQL database to begin conversational querying.")

    with st.form("connect_form"):
        col1, col2 = st.columns(2)
        with col1:
            host = st.text_input("Host", value="localhost")
            port = st.number_input("Port", value=3306, step=1, min_value=1, max_value=65535)
            database = st.text_input("Database", value="ecommerce_db")
        with col2:
            user = st.text_input("User", value="appuser")
            password = st.text_input("Password", type="password", value="Password123!")

        submitted = st.form_submit_button("Connect to Database", type="primary", width="stretch")

    if submitted:
        try:
            with st.spinner("Verifying connection to MySQL…"):
                engine = get_engine(host, int(port), user, password, database)
            st.session_state["engine"] = engine
            st.session_state["database"] = database
            success_toast(f"Successfully connected to {database}!")
            st.rerun()
        except Exception as exc:
            error_toast(f"Connection failed: {exc}")
            st.error(f"❌ Connection Error: {exc}")
    st.stop()


# ── Step 2: Extract Schema ───────────────────────────────────────────────────
if not st.session_state["schema"]:
    st.title(f"🗄️ Connected to `{st.session_state['database']}`")
    st.info("Extract and ground the database schema to enable SQL query generation.")

    if st.button("⚡ Extract & Ground Database Schema", type="primary", width="stretch"):
        try:
            with st.spinner("Extracting table definitions, foreign keys, and sample records…"):
                schema = extract_schema(st.session_state["engine"], st.session_state["database"])
            st.session_state["schema"] = schema
            success_toast("Schema extracted and grounded successfully!")
            st.rerun()
        except Exception as exc:
            error_toast(f"Schema extraction failed: {exc}")
            st.error(f"❌ Schema extraction error: {exc}")
    st.stop()


# ── Main Chat Interface ──────────────────────────────────────────────────────
st.title(f"💬 NL2SQL Copilot — `{st.session_state['database']}`")

# Collapsible schema summary
with st.expander("📋 View Active Database Schema & Grounding Data", expanded=False):
    st.code(st.session_state["schema"], language="text")

# ── Render Chat Message History ──────────────────────────────────────────────
for i, msg in enumerate(st.session_state["messages"]):
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(msg["content"])

    elif msg["role"] == "assistant":
        with st.chat_message("assistant", avatar="🤖"):
            category = msg.get("category", "DQL")
            if category == "DML":
                st.warning("⚠️ **Data Modification Operation (`INSERT` / `UPDATE` / `DELETE`)**")
            else:
                st.caption("🔍 **Read Query (`SELECT`)**")

            st.code(msg["sql"], language="sql")

            # Execution Results
            if msg.get("status") == "success":
                if category == "DQL" and isinstance(msg.get("data"), pd.DataFrame):
                    df = msg["data"]
                    st.caption(f"📊 Returned **{len(df):,}** row(s)")
                    st.dataframe(df, width="stretch")

                    # CSV Download
                    csv_data = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📥 Download Results (CSV)",
                        data=csv_data,
                        file_name=f"query_result_{i}.csv",
                        mime="text/csv",
                        key=f"dl_csv_{i}"
                    )
                elif category == "DML":
                    st.success(f"✅ {msg.get('message', 'Executed successfully.')}")

            elif msg.get("status") == "error":
                st.error(f"❌ **Execution Failed:** {msg.get('error')}")

                # Auto-Fix Button
                if st.button("🔧 Auto-Fix with Ollama", key=f"autofix_{i}"):
                    try:
                        with st.spinner("Ollama is analyzing the error and repairing SQL…"):
                            repaired_sql = fix_sql(
                                st.session_state["schema"],
                                msg["sql"],
                                msg["error"],
                                msg.get("original_question", "")
                            )
                            # Re-execute repaired SQL
                            result = run_query(st.session_state["engine"], repaired_sql)

                        st.session_state["messages"][i]["sql"] = repaired_sql
                        st.session_state["messages"][i]["status"] = "success"
                        st.session_state["messages"][i]["error"] = None
                        st.session_state["messages"][i]["category"] = result["type"]
                        if result["type"] == "DQL":
                            st.session_state["messages"][i]["data"] = result["data"]
                        else:
                            st.session_state["messages"][i]["message"] = result["message"]

                        success_toast("Query repaired and executed successfully!")
                        st.rerun()
                    except Exception as fix_exc:
                        error_toast(f"Auto-fix failed: {fix_exc}")
                        st.error(f"Auto-fix failed: {fix_exc}")

            # Editable Query Expander
            with st.expander("✏️ Edit & Re-run SQL", expanded=False):
                edited = st.text_area("SQL Statement", value=msg["sql"], key=f"edit_box_{i}", height=100)
                if st.button("▶ Re-run Modified Query", key=f"rerun_btn_{i}"):
                    try:
                        with st.spinner("Executing updated SQL…"):
                            rerun_res = run_query(st.session_state["engine"], edited)

                        st.session_state["messages"][i]["sql"] = edited
                        st.session_state["messages"][i]["status"] = "success"
                        st.session_state["messages"][i]["error"] = None
                        st.session_state["messages"][i]["category"] = rerun_res["type"]
                        if rerun_res["type"] == "DQL":
                            st.session_state["messages"][i]["data"] = rerun_res["data"]
                        else:
                            st.session_state["messages"][i]["message"] = rerun_res["message"]

                        success_toast("Updated query executed successfully!")
                        st.rerun()
                    except Exception as rerun_exc:
                        error_toast(f"Execution Error: {rerun_exc}")
                        st.session_state["messages"][i]["status"] = "error"
                        st.session_state["messages"][i]["error"] = str(rerun_exc)
                        st.rerun()


# ── Empty State: Suggested Prompts ───────────────────────────────────────────
if not st.session_state["messages"]:
    st.markdown("### 💡 What would you like to query?")
    st.markdown("Type a question below or click any of these quick examples:")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔍 Show all customers from Pune", width="stretch"):
            st.session_state["pending_input"] = "Show all customers from Pune"
            st.rerun()
        if st.button("💰 Total revenue from completed orders", width="stretch"):
            st.session_state["pending_input"] = "What is the total revenue from completed orders?"
            st.rerun()
    with col_b:
        if st.button("📦 Which products cost more than $50?", width="stretch"):
            st.session_state["pending_input"] = "Which products cost more than $50?"
            st.rerun()
        if st.button("➕ Add customer Chhagan Batliwala (Pune)", width="stretch"):
            st.session_state["pending_input"] = "add one more entry in customers table for chhagan batliwala, email is chhagan@gmail.com, location pune."
            st.rerun()


# ── Handle Pending Button Input or Chat Input ────────────────────────────────
prompt = st.chat_input("Ask a question about your database or instruct an operation...")

# Support quick-click suggested prompts
if "pending_input" in st.session_state and st.session_state["pending_input"]:
    prompt = st.session_state.pop("pending_input")


if prompt:
    # 1. Append User Message
    st.session_state["messages"].append({
        "role": "user",
        "content": prompt
    })

    # Prepare conversation history for multi-turn prompt
    chat_history = []
    msgs = st.session_state["messages"]
    for idx in range(0, len(msgs) - 1, 2):
        if idx + 1 < len(msgs):
            u_msg = msgs[idx]
            a_msg = msgs[idx + 1]
            if u_msg.get("role") == "user" and a_msg.get("role") == "assistant" and a_msg.get("sql"):
                chat_history.append({"question": u_msg["content"], "sql": a_msg["sql"]})

    # 2. Generate and Execute SQL
    try:
        with st.spinner("Generating SQL with Ollama…"):
            generated_sql = generate_sql(
                schema=st.session_state["schema"],
                question=prompt,
                history=chat_history
            )

        # Validate statement
        cleaned_sql, category = validate_and_classify_sql(generated_sql)

        # Execute statement
        with st.spinner("Executing on MySQL…"):
            result = run_query(st.session_state["engine"], cleaned_sql)

        # Assistant Success Message
        asst_msg = {
            "role": "assistant",
            "original_question": prompt,
            "sql": cleaned_sql,
            "category": category,
            "status": "success",
        }
        if category == "DQL":
            asst_msg["data"] = result["data"]
            success_toast(f"Returned {result['rows']:,} row(s)!")
        else:
            asst_msg["message"] = result["message"]
            success_toast(result["message"])

        st.session_state["messages"].append(asst_msg)

    except Exception as exc:
        error_msg = str(exc)
        error_toast(f"Failed: {error_msg}")

        # Assistant Error Message with Auto-Fix Option
        st.session_state["messages"].append({
            "role": "assistant",
            "original_question": prompt,
            "sql": locals().get("generated_sql", "-- Could not generate query"),
            "category": locals().get("category", "DQL"),
            "status": "error",
            "error": error_msg,
        })

    st.rerun()
