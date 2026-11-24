import { useEffect, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { generateSql, execute, listChats, summarize } from "../lib/api";
import type { ChatRecord, SummaryMode } from "../lib/types";
import { useSession, useSessionErrorHandler } from "../lib/session";
import { ChatTurn, type Turn } from "../components/ChatTurn";
import { Alert, Button, Spinner } from "../components/ui";

function message(error: unknown): string { return error instanceof Error ? error.message : "Something went wrong."; }
function fromRecord(record: ChatRecord): Turn {
  return { chatId: record.id, question: record.question, createdAt: record.created_at, sql: record.executed_sql ?? record.generated_sql, executedSql: record.executed_sql, status: record.status, error: record.error, rowCount: record.row_count, result: null, summaries: record.summaries, running: false, summarizing: null, notice: null, confirmation: null };
}

function warningFor(sql: string): string | null {
  const statement = sql.trim().replace(/;+\s*$/, "");
  if (/^delete\b/i.test(statement) && !/\bwhere\b/i.test(statement)) return "This DELETE has no WHERE clause and may remove every row in the table.";
  if (/^truncate\b/i.test(statement)) return "TRUNCATE removes every row in a table and cannot be undone.";
  if (/^drop\b/i.test(statement)) return "DROP permanently removes a database object and its data.";
  if (/^rename\b/i.test(statement)) return "RENAME changes a database object's name and can affect existing queries.";
  return null;
}

export function Chat(): JSX.Element | null {
  const { session, markMetadataStale } = useSession();
  const navigate = useNavigate();
  const handleSessionError = useSessionErrorHandler();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [generating, setGenerating] = useState(false);
  const feed = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const stickToBottom = useRef(true);
  if (!session) return null;
  const load = async (): Promise<void> => {
    setLoading(true); setError(null);
    try { setTurns((await listChats(session.connectionId)).map(fromRecord)); } catch (caught) { if (!handleSessionError(caught)) setError(message(caught)); } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [session.connectionId]);
  useEffect(() => { if (stickToBottom.current) feed.current?.scrollTo({ top: feed.current.scrollHeight }); }, [turns, generating]);
  const resizeComposer = (): void => { const element = composer.current; if (!element) return; element.style.height = "auto"; element.style.height = `${Math.min(element.scrollHeight, 144)}px`; };
  const ask = async (): Promise<void> => {
    const text = question.trim(); if (!text || generating) return;
    const temporaryId = -Date.now(); const pending: Turn = { chatId: temporaryId, question: text, createdAt: new Date().toISOString(), sql: "", executedSql: null, status: "generated", error: null, rowCount: null, result: null, summaries: [], running: false, summarizing: null, notice: "Generating SQL…", confirmation: null };
    setTurns((current) => [...current, pending]); setQuestion(""); setGenerating(true);
    try {
      const response = await generateSql(session.sessionId, text);
      setTurns((current) => current.map((turn) => turn.chatId === temporaryId ? { ...turn, chatId: response.chat_id, sql: response.sql, notice: null } : turn));
    } catch (caught) {
      setTurns((current) => current.filter((turn) => turn.chatId !== temporaryId)); setQuestion(text);
      if (!handleSessionError(caught)) setError(message(caught));
    } finally { setGenerating(false); }
  };
  const updateTurn = (chatId: number, update: (turn: Turn) => Turn): void => setTurns((current) => current.map((turn) => turn.chatId === chatId ? update(turn) : turn));
  const run = async (chatId: number, sql: string, confirmed = false): Promise<void> => {
    if (!sql.trim()) return;
    const warning = warningFor(sql);
    if (warning && !confirmed) { updateTurn(chatId, (turn) => ({ ...turn, confirmation: warning })); return; }
    updateTurn(chatId, (turn) => ({ ...turn, running: true, notice: null, confirmation: null }));
    try {
      const response = await execute(session.sessionId, chatId, sql);
      updateTurn(chatId, (turn) => ({ ...turn, sql: response.sql, executedSql: response.sql, status: "executed", error: null, rowCount: response.row_count, result: { columns: response.columns, rows: response.rows, truncated: response.truncated, retried: response.retried }, running: false, notice: response.metadata_stale ? "Schema changed. Return to Connect and extract the database again before generating more SQL." : null }));
      if (response.metadata_stale) {
        markMetadataStale();
        navigate("/connect", { state: { notice: "Schema changed. Extract the database again before generating more SQL." } });
      }
    } catch (caught) {
      if (handleSessionError(caught)) return;
      const status = (caught as { status?: number }).status;
      updateTurn(chatId, (turn) => status === 400 ? { ...turn, status: "error", error: message(caught), running: false } : { ...turn, notice: message(caught), running: false });
    }
  };
  const requestSummary = async (chatId: number, mode: SummaryMode): Promise<void> => {
    updateTurn(chatId, (turn) => ({ ...turn, summarizing: mode, notice: null }));
    try {
      const response = await summarize(session.sessionId, chatId, mode);
      const note = `Based on ${response.rows_analyzed} rows${response.truncated ? " (the result was cut off, so figures cover only those rows)" : ""}`;
      updateTurn(chatId, (turn) => ({ ...turn, summarizing: null, summaries: [...turn.summaries, { id: response.summary_id, kind: response.mode, text: response.text, created_at: new Date().toISOString(), note }] }));
    } catch (caught) {
      if (handleSessionError(caught)) return;
      updateTurn(chatId, (turn) => ({ ...turn, summarizing: null, notice: message(caught) }));
    }
  };
  return <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-4xl flex-col px-4"><div ref={feed} onScroll={(event) => { const element = event.currentTarget; stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 64; }} className="flex-1 space-y-5 overflow-y-auto py-6">
    {loading ? <div className="py-16 text-center"><Spinner label="Loading chat history…" /></div> : error ? <div className="space-y-3"><Alert>{error}</Alert><Button variant="secondary" onClick={() => void load()}>Retry</Button></div> : turns.length === 0 ? <p className="py-16 text-center text-muted">No questions yet. Ask something about <strong>{session.database}</strong>.</p> : turns.map((turn) => <ChatTurn key={turn.chatId} turn={turn} onRun={(id, sql, confirmed) => void run(id, sql, confirmed)} onSummarize={(id, mode) => void requestSummary(id, mode)} onSqlChange={(id, sql) => updateTurn(id, (turn) => ({ ...turn, sql, confirmation: null }))} onDismissWarning={(id) => updateTurn(id, (turn) => ({ ...turn, confirmation: null }))} />)}
  </div><div className="sticky bottom-0 border-t border-border bg-bg py-3"><form className="flex items-end gap-2" onSubmit={(event) => { event.preventDefault(); void ask(); }}><textarea ref={composer} value={question} rows={1} placeholder="Ask a question about your data…" onChange={(event) => { setQuestion(event.target.value); resizeComposer(); }} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void ask(); } }} className="max-h-36 min-h-9 flex-1 overflow-auto rounded-md border border-border bg-surface-2 px-3 py-2 outline-none placeholder:text-dim focus:border-accent focus:ring-1 focus:ring-accent" /><Button type="submit" loading={generating} disabled={!question.trim()}><ArrowUp className="size-3.5" />Generate SQL</Button></form>{error && !loading && <Alert className="mt-2">{error}</Alert>}</div></div>;
}
