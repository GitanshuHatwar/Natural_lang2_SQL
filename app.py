import os
import io
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from db import (
    get_engine,
    get_available_databases,
    extract_schema,
    run_query,
    validate_and_transform_sql,
    analyze_query_cost,
)
from llm import (
    generate_sql,
    explain_sql,
    fix_sql,
    get_available_models,
    DEFAULT_MODEL,
)
from security import (
    sanitize_and_check_prompt,
    audit_logger,
    SecurityError,
)
from chat_store import chat_store

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NL2SQL Enterprise AI Copilot",
    page_icon="🌿",
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


# ── Chart & Export Helpers ───────────────────────────────────────────────────
def generate_excel_bytes(df: pd.DataFrame) -> bytes:
    """Generate Excel bytes using openpyxl."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Query_Results")
    return buffer.getvalue()


def render_intelligent_chart(df: pd.DataFrame):
    """Automatically render an appropriate chart based on column data types."""
    if len(df) < 2:
        return

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    date_cols = [
        c for c in df.columns
        if "date" in c.lower() or "time" in c.lower() or pd.api.types.is_datetime64_any_dtype(df[c])
    ]
    categorical_cols = [
        c for c in df.select_dtypes(include=["object", "string", "category"]).columns
        if c not in date_cols
    ]

    with st.expander("📊 Data Visualization", expanded=False):
        if date_cols and numeric_cols:
            st.caption(f"📈 Trend Chart ({date_cols[0]} vs {numeric_cols[0]})")
            try:
                chart_data = df[[date_cols[0], numeric_cols[0]]].dropna().set_index(date_cols[0])
                st.line_chart(chart_data, width="stretch")
            except Exception as e:
                st.caption(f"Could not render line chart: {e}")
        elif categorical_cols and numeric_cols:
            st.caption(f"📊 Bar Chart ({categorical_cols[0]} vs {numeric_cols[0]})")
            try:
                chart_data = df[[categorical_cols[0], numeric_cols[0]]].dropna().set_index(categorical_cols[0])
                st.bar_chart(chart_data, width="stretch")
            except Exception as e:
                st.caption(f"Could not render bar chart: {e}")
        else:
            st.info("No categorical/date pairs found for automatic charting.")


# ── Session State Initialization ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "engine" not in st.session_state:
    st.session_state["engine"] = None
if "schema" not in st.session_state:
    st.session_state["schema"] = None
if "database" not in st.session_state:
    st.session_state["database"] = None
if "username" not in st.session_state:
    st.session_state["username"] = "appuser"
if "selected_model" not in st.session_state:
    st.session_state["selected_model"] = DEFAULT_MODEL
if "active_session_id" not in st.session_state:
    st.session_state["active_session_id"] = None
if "draft_prompt" not in st.session_state:
    st.session_state["draft_prompt"] = None


# ── Synchronize Active Session Messages ──────────────────────────────────────
if st.session_state["database"] and not st.session_state["active_session_id"]:
    sessions = chat_store.list_sessions(st.session_state["database"])
    if sessions:
        st.session_state["active_session_id"] = sessions[0]["session_id"]
    else:
        st.session_state["active_session_id"] = chat_store.create_session(
            st.session_state["database"], "New Conversation"
        )
    st.session_state["messages"] = chat_store.get_session_messages(st.session_state["active_session_id"])


# ── Sidebar Controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🌿 NL2SQL Copilot")
    st.caption("Enterprise AI-Assisted Database Intelligence")

    # Dynamic Model Selector
    available_models = get_available_models()
    default_idx = 0
    if st.session_state["selected_model"] in available_models:
        default_idx = available_models.index(st.session_state["selected_model"])

    selected_model = st.selectbox(
        "🧠 Active Model (Ollama)",
        options=available_models,
        index=default_idx,
        help="Switch dynamically between locally installed Ollama models.",
    )
    st.session_state["selected_model"] = selected_model

    st.divider()

    if st.session_state["engine"]:
        st.success(
            f"Connected to **{st.session_state['database']}**",
            icon=":material/check_circle:",
        )
        st.caption(f"Authenticated as: `{st.session_state['username']}`")
        if st.button("Disconnect", icon=":material/link_off:", width="stretch"):
            for key in ["engine", "database", "schema", "messages", "active_session_id", "draft_prompt"]:
                st.session_state[key] = None if key != "messages" else []
            success_toast("Disconnected from database.")
            st.rerun()

        st.divider()
        st.subheader("💬 Conversations")

        # Start New Chat Button
        if st.button("New Chat", type="primary", icon=":material/add:", width="stretch"):
            new_id = chat_store.create_session(st.session_state["database"], "New Conversation")
            st.session_state["active_session_id"] = new_id
            st.session_state["messages"] = []
            st.session_state["draft_prompt"] = None
            success_toast("Started a new conversation.")
            st.rerun()

        # List existing sessions from local SQLite store
        sessions = chat_store.list_sessions(st.session_state["database"])
        for s in sessions:
            s_id = s["session_id"]
            is_active = (s_id == st.session_state["active_session_id"])
            btn_label = s['title'][:22]

            col_s_btn, col_s_del = st.columns([5, 1])
            with col_s_btn:
                btn_icon = ":material/arrow_right_alt:" if is_active else ":material/chat_bubble:"
                if st.button(btn_label, key=f"session_btn_{s_id}", icon=btn_icon, width="stretch", disabled=is_active):
                    st.session_state["active_session_id"] = s_id
                    st.session_state["messages"] = chat_store.get_session_messages(s_id)
                    st.session_state["draft_prompt"] = None
                    st.rerun()
            with col_s_del:
                if st.button("✕", key=f"session_del_{s_id}", help="Delete this chat"):
                    chat_store.delete_session(s_id)
                    if st.session_state["active_session_id"] == s_id:
                        st.session_state["active_session_id"] = None
                        st.session_state["messages"] = []
                    success_toast("Chat deleted.")
                    st.rerun()

        # Audit Trail Expander
        st.divider()
        with st.expander(":material/history: Audit Trail (Recent)", expanded=False):
            try:
                logs_df = audit_logger.get_recent_logs(limit=10)
                if not logs_df.empty:
                    st.dataframe(
                        logs_df[["timestamp", "statement_type", "status", "rows_affected", "execution_time_ms"]],
                        width="stretch"
                    )
                else:
                    st.caption("No audit entries yet.")
            except Exception as e:
                st.caption(f"Audit log unavailable: {e}")
    else:
        st.info("MySQL connection offline.", icon=":material/info:")


# ── Step 1: Connect to Database ──────────────────────────────────────────────
if not st.session_state["engine"]:
    # Top announcement pill matching reference aesthetic
    st.html(
        """
        <div style="background-color: #1B4D3E; color: #FFFFFF; padding: 8px 18px; border-radius: 9999px; text-align: center; font-size: 0.85rem; font-weight: 500; letter-spacing: 0.02em; margin-bottom: 2rem;">
            🔒 Enterprise Privacy Mode &nbsp;•&nbsp; 100% Offline Local AI &nbsp;•&nbsp; Direct MySQL Engine
        </div>
        """
    )

    # Hero headline matching reference image
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1 style="font-size: 2.8rem; font-weight: 700; margin-bottom: 0.8rem; color: #192823; line-height: 1.2;">
                The <em style="font-style: italic; color: #1B4D3E;">sweet spot</em> for enterprise database queries.
            </h1>
            <p style="font-size: 1.15rem; color: #4A5B53; max-width: 680px; margin: 0 auto 1.8rem auto; line-height: 1.6;">
                Anyone can explore databases with natural language. We make sure every query is verified, secure, and blazing fast.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Laurel-style feature cards
    col_v1, col_v2, col_v3 = st.columns(3)
    with col_v1:
        with st.container(border=True):
            st.caption("PRIVACY ASSURED")
            st.markdown("### 🛡️ 100% Local")
            st.caption("Zero cloud leaks with local Ollama models.")
    with col_v2:
        with st.container(border=True):
            st.caption("PERFORMANCE")
            st.markdown("### ⚡ < 500ms")
            st.caption("Direct MySQL connection & optimized execution.")
    with col_v3:
        with st.container(border=True):
            st.caption("SECURITY")
            st.markdown("### 🔒 Guardrails")
            st.caption("Strict AST verification and DML confirmation.")

    st.write("")

    # Form card
    with st.container(border=True):
        st.subheader(":material/database: Connect to Database")
        st.caption("Enter your MySQL credentials to initialize your conversational intelligence workspace.")

        with st.form("connect_form"):
            col1, col2 = st.columns(2)
            with col1:
                host = st.text_input("Host", value="localhost")
                port = st.number_input("Port", value=3306, step=1, min_value=1, max_value=65535)
                database = st.text_input("Database", value="ecommerce_db")
            with col2:
                user = st.text_input("User", value="appuser")
                password = st.text_input("Password", type="password", value="Password123!")

            submitted = st.form_submit_button(
                "Connect to Database",
                type="primary",
                icon=":material/arrow_forward:",
                width="stretch",
            )

    if submitted:
        try:
            with st.spinner("Verifying connection to MySQL…"):
                engine = get_engine(host, int(port), user, password, database)
            st.session_state["engine"] = engine
            st.session_state["database"] = database
            st.session_state["username"] = user
            success_toast(f"Successfully connected to {database}!")
            st.rerun()
        except Exception as exc:
            error_toast(f"Connection failed: {exc}")
            st.error(f"❌ Connection Error: {exc}")
    st.stop()


# ── Step 2: Extract Schema ───────────────────────────────────────────────────
if not st.session_state["schema"]:
    st.html(
        """
        <div style="background-color: #1B4D3E; color: #FFFFFF; padding: 8px 18px; border-radius: 9999px; text-align: center; font-size: 0.85rem; font-weight: 500; letter-spacing: 0.02em; margin-bottom: 2rem;">
            ✅ Database Connected &nbsp;•&nbsp; Schema Grounding Required
        </div>
        """
    )

    with st.container(border=True):
        st.subheader(f":material/schema: Ground Schema for `{st.session_state['database']}`")
        st.markdown(
            "Extract table structures, data types, primary & foreign key relationships, and masked records "
            "so the local AI model can generate precise SQL statements."
        )

        if st.button(
            "Extract & Ground Database Schema",
            type="primary",
            icon=":material/bolt:",
            width="stretch",
        ):
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
st.html(
    f"""
    <div style="background-color: #1B4D3E; color: #FFFFFF; padding: 10px 22px; border-radius: 9999px; display: flex; justify-content: space-between; align-items: center; font-size: 0.88rem; font-weight: 500; margin-bottom: 1.5rem;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 1.1rem;">🌿</span>
            <span><strong>NL2SQL Copilot</strong> &nbsp;|&nbsp; Database: <code>{st.session_state['database']}</code></span>
        </div>
        <div style="display: flex; align-items: center; gap: 14px; font-size: 0.82rem; opacity: 0.92;">
            <span>🧠 <code>{st.session_state['selected_model']}</code></span>
            <span>👤 <code>{st.session_state['username']}</code></span>
        </div>
    </div>
    """
)

# Collapsible schema summary
with st.expander(":material/schema: View Active Database Schema & Grounding Data", expanded=False):
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
                st.warning(
                    "This operation will modify database records (`INSERT` / `UPDATE` / `DELETE`).",
                    title="Data Modification Operation",
                    icon=":material/warning:",
                )
            else:
                st.caption("🔍 Read Query (`SELECT`)")

            # Query Explanation Card
            if msg.get("explanation"):
                st.info(msg["explanation"], title="Query Explanation", icon=":material/lightbulb:")

            st.code(msg["sql"], language="sql")

            # Execution Results
            if msg.get("status") == "success":
                if category == "DQL" and isinstance(msg.get("data"), pd.DataFrame):
                    df = msg["data"]
                    cost_info = msg.get("cost_info", {})
                    metrics_str = f"📊 Returned **{len(df):,}** row(s) &nbsp;|&nbsp; ⏱️ {msg.get('latency_ms', 0)} ms"
                    if cost_info.get("query_cost"):
                        metrics_str += f" &nbsp;|&nbsp; 💰 Cost: {cost_info['query_cost']}"
                    st.caption(metrics_str)

                    st.dataframe(df, width="stretch")

                    # Intelligent Chart
                    render_intelligent_chart(df)

                    # Export options: CSV & Excel
                    col_csv, col_xlsx = st.columns(2)
                    with col_csv:
                        csv_data = df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            label="Download CSV",
                            data=csv_data,
                            file_name=f"query_result_{i}.csv",
                            mime="text/csv",
                            key=f"dl_csv_{i}",
                            icon=":material/download:",
                            width="stretch",
                        )
                    with col_xlsx:
                        try:
                            xlsx_data = generate_excel_bytes(df)
                            st.download_button(
                                label="Download Excel (.xlsx)",
                                data=xlsx_data,
                                file_name=f"query_result_{i}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_xlsx_{i}",
                                icon=":material/table_view:",
                                width="stretch",
                            )
                        except Exception:
                            pass

                elif category == "DML":
                    st.success(
                        f"{msg.get('message', 'Executed successfully.')} (⏱️ {msg.get('latency_ms', 0)} ms)",
                        icon=":material/check_circle:",
                    )

            elif msg.get("status") == "error":
                st.error(f"**Execution Failed:** {msg.get('error')}", icon=":material/error:")

                # Auto-Fix Button
                if st.button("Auto-Fix with Ollama", type="primary", icon=":material/build:", key=f"autofix_{i}"):
                    try:
                        with st.spinner("Ollama is analyzing the error and repairing SQL…"):
                            repaired_sql = fix_sql(
                                st.session_state["schema"],
                                msg["sql"],
                                msg["error"],
                                msg.get("original_question", ""),
                                model_name=st.session_state["selected_model"],
                            )
                            # Re-execute repaired SQL
                            result = run_query(
                                st.session_state["engine"],
                                repaired_sql,
                                username=st.session_state["username"],
                                database=st.session_state["database"],
                            )
                            new_explanation = explain_sql(
                                st.session_state["schema"],
                                repaired_sql,
                                model_name=st.session_state["selected_model"],
                            )

                        st.session_state["messages"][i]["sql"] = repaired_sql
                        st.session_state["messages"][i]["status"] = "success"
                        st.session_state["messages"][i]["error"] = None
                        st.session_state["messages"][i]["category"] = result["type"]
                        st.session_state["messages"][i]["latency_ms"] = result.get("latency_ms", 0)
                        st.session_state["messages"][i]["explanation"] = new_explanation

                        if result["type"] == "DQL":
                            st.session_state["messages"][i]["data"] = result["data"]
                            st.session_state["messages"][i]["cost_info"] = result.get("cost_info", {})
                        else:
                            st.session_state["messages"][i]["message"] = result["message"]

                        # Persist repaired message
                        chat_store.save_message(st.session_state["active_session_id"], st.session_state["messages"][i])
                        success_toast("Query repaired and executed successfully!")
                        st.rerun()
                    except Exception as fix_exc:
                        error_toast(f"Auto-fix failed: {fix_exc}")
                        st.error(f"Auto-fix failed: {fix_exc}")

            # Editable Query Expander
            with st.expander(":material/edit: Edit & Re-run SQL", expanded=False):
                edited = st.text_area("SQL Statement", value=msg["sql"], key=f"edit_box_{i}", height=100)
                if st.button("Re-run Modified Query", icon=":material/play_arrow:", key=f"rerun_btn_{i}", width="stretch"):
                    try:
                        with st.spinner("Executing updated SQL…"):
                            rerun_res = run_query(
                                st.session_state["engine"],
                                edited,
                                username=st.session_state["username"],
                                database=st.session_state["database"],
                            )
                            rerun_expl = explain_sql(
                                st.session_state["schema"],
                                edited,
                                model_name=st.session_state["selected_model"],
                            )

                        st.session_state["messages"][i]["sql"] = edited
                        st.session_state["messages"][i]["status"] = "success"
                        st.session_state["messages"][i]["error"] = None
                        st.session_state["messages"][i]["category"] = rerun_res["type"]
                        st.session_state["messages"][i]["latency_ms"] = rerun_res.get("latency_ms", 0)
                        st.session_state["messages"][i]["explanation"] = rerun_expl

                        if rerun_res["type"] == "DQL":
                            st.session_state["messages"][i]["data"] = rerun_res["data"]
                            st.session_state["messages"][i]["cost_info"] = rerun_res.get("cost_info", {})
                        else:
                            st.session_state["messages"][i]["message"] = rerun_res["message"]

                        # Persist rerun message
                        chat_store.save_message(st.session_state["active_session_id"], st.session_state["messages"][i])
                        success_toast("Updated query executed successfully!")
                        st.rerun()
                    except Exception as rerun_exc:
                        error_toast(f"Execution Error: {rerun_exc}")
                        st.session_state["messages"][i]["status"] = "error"
                        st.session_state["messages"][i]["error"] = str(rerun_exc)
                        st.rerun()


# ── Empty State: Suggested Prompts ───────────────────────────────────────────
if not st.session_state["messages"] and not st.session_state.get("draft_prompt"):
    with st.container(border=True):
        st.subheader(":material/lightbulb: Quick Starters")
        st.caption("Click any template below to load and customize it for your needs:")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Show all customers from Pune", icon=":material/search:", width="stretch"):
                st.session_state["draft_prompt"] = "Show all customers from Pune"
                st.rerun()
            if st.button("Total revenue from completed orders", icon=":material/payments:", width="stretch"):
                st.session_state["draft_prompt"] = "What is the total revenue from completed orders?"
                st.rerun()
        with col_b:
            if st.button("Which products cost more than $50?", icon=":material/inventory_2:", width="stretch"):
                st.session_state["draft_prompt"] = "Which products cost more than $50?"
                st.rerun()
            if st.button("Add customer Chhagan Batliwala (Pune)", icon=":material/person_add:", width="stretch"):
                st.session_state["draft_prompt"] = "add one more entry in customers table for chhagan batliwala, email is chhagan@gmail.com, location pune."
                st.rerun()


# ── Interactive Prompt Verification & Customization Card ─────────────────────
execute_prompt_text = None

if st.session_state.get("draft_prompt"):
    st.divider()
    with st.container(border=True):
        st.subheader(":material/edit_note: Verify & Customize Query Prompt")
        st.caption("Review or modify the template question below according to your exact use case before sending:")

        edited_draft = st.text_area(
            "Prompt Template",
            value=st.session_state["draft_prompt"],
            height=85,
            key="draft_editor_area",
            label_visibility="collapsed"
        )

        col_run, col_cancel = st.columns([2, 5])
        with col_run:
            if st.button("Send to Copilot", type="primary", icon=":material/send:", width="stretch"):
                execute_prompt_text = edited_draft.strip()
                st.session_state["draft_prompt"] = None
        with col_cancel:
            if st.button("Cancel", icon=":material/close:", width="stretch"):
                st.session_state["draft_prompt"] = None
                st.rerun()


# ── Handle Input: Chat Input or Verified Draft Prompt ────────────────────────
chat_input_val = st.chat_input("Ask a question about your database or instruct an operation...")

prompt = execute_prompt_text or chat_input_val

if prompt:
    # Ensure an active session exists
    if not st.session_state["active_session_id"]:
        st.session_state["active_session_id"] = chat_store.create_session(
            st.session_state["database"], "New Conversation"
        )

    # 1. Security Check against Prompt Injection
    try:
        sanitize_and_check_prompt(prompt)
    except SecurityError as sec_err:
        error_toast(str(sec_err))
        user_err_msg = {"role": "user", "content": prompt}
        asst_err_msg = {
            "role": "assistant",
            "original_question": prompt,
            "sql": "-- Blocked by Security Guard",
            "category": "BLOCKED",
            "status": "error",
            "error": str(sec_err),
        }
        st.session_state["messages"].append(user_err_msg)
        st.session_state["messages"].append(asst_err_msg)
        chat_store.save_message(st.session_state["active_session_id"], user_err_msg)
        chat_store.save_message(st.session_state["active_session_id"], asst_err_msg)
        st.rerun()

    # 2. Append User Message
    user_msg = {"role": "user", "content": prompt}
    st.session_state["messages"].append(user_msg)
    chat_store.save_message(st.session_state["active_session_id"], user_msg)

    # Auto-rename session title based on the first question
    if len(st.session_state["messages"]) <= 2:
        title_snippet = prompt[:35] + ("…" if len(prompt) > 35 else "")
        chat_store.update_session_title(st.session_state["active_session_id"], title_snippet)

    # Prepare conversation history for multi-turn prompt
    chat_history = []
    msgs = st.session_state["messages"]
    for idx in range(0, len(msgs) - 1, 2):
        if idx + 1 < len(msgs):
            u_msg = msgs[idx]
            a_msg = msgs[idx + 1]
            if u_msg.get("role") == "user" and a_msg.get("role") == "assistant" and a_msg.get("sql"):
                chat_history.append({"question": u_msg["content"], "sql": a_msg["sql"]})

    # 3. Generate and Execute SQL
    try:
        with st.spinner("Generating SQL with Ollama…"):
            generated_sql = generate_sql(
                schema=st.session_state["schema"],
                question=prompt,
                history=chat_history,
                model_name=st.session_state["selected_model"],
            )

        # Validate statement & AST constraints
        cleaned_sql, category = validate_and_transform_sql(generated_sql)

        # Execute statement
        with st.spinner("Executing on MySQL…"):
            result = run_query(
                st.session_state["engine"],
                cleaned_sql,
                username=st.session_state["username"],
                database=st.session_state["database"],
            )

        # Generate friendly plain-English explanation
        explanation = explain_sql(
            st.session_state["schema"],
            cleaned_sql,
            model_name=st.session_state["selected_model"],
        )

        # Assistant Success Message
        asst_msg = {
            "role": "assistant",
            "original_question": prompt,
            "sql": cleaned_sql,
            "category": category,
            "explanation": explanation,
            "status": "success",
            "latency_ms": result.get("latency_ms", 0),
        }
        if category == "DQL":
            asst_msg["data"] = result["data"]
            asst_msg["cost_info"] = result.get("cost_info", {})
            success_toast(f"Returned {result['rows']:,} row(s)!")
        else:
            asst_msg["message"] = result["message"]
            success_toast(result["message"])

        st.session_state["messages"].append(asst_msg)
        chat_store.save_message(st.session_state["active_session_id"], asst_msg)

    except Exception as exc:
        error_msg = str(exc)
        error_toast(f"Failed: {error_msg}")

        # Assistant Error Message with Auto-Fix Option
        err_asst_msg = {
            "role": "assistant",
            "original_question": prompt,
            "sql": locals().get("generated_sql", "-- Could not generate query"),
            "category": locals().get("category", "DQL"),
            "status": "error",
            "error": error_msg,
        }
        st.session_state["messages"].append(err_asst_msg)
        chat_store.save_message(st.session_state["active_session_id"], err_asst_msg)

    st.rerun()
