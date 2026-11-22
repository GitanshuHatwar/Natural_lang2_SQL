import { ChartNoAxesColumn, Play, Sparkles } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Cell, ChatStatus, SummaryMode, SummaryRecord } from "../lib/types";
import { Alert, Badge, Button, Card, Spinner } from "./ui";
import { ResultTable } from "./ResultTable";

export type Turn = {
  chatId: number; question: string; createdAt: string; sql: string; executedSql: string | null;
  status: ChatStatus; error: string | null; rowCount: number | null;
  result: { columns: string[]; rows: Cell[][]; truncated: boolean; retried: boolean } | null;
  summaries: (SummaryRecord & { note?: string })[];
  running: boolean; summarizing: SummaryMode | null; notice: string | null; confirmation: string | null;
};

type Props = {
  turn: Turn;
  onRun: (chatId: number, sql: string, confirmed?: boolean) => void;
  onSummarize: (chatId: number, mode: SummaryMode) => void;
  onSqlChange: (chatId: number, sql: string) => void;
  onDismissWarning: (chatId: number) => void;
};

function statusVariant(status: ChatStatus): "neutral" | "success" | "danger" {
  return status === "executed" ? "success" : status === "error" ? "danger" : "neutral";
}

export function ChatTurn({ turn, onRun, onSummarize, onSqlChange, onDismissWarning }: Props): JSX.Element {
  const editor = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const element = editor.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 288)}px`;
  }, [turn.sql]);
  return <article className="space-y-3">
    <div className="ml-auto max-w-[80%] rounded-lg bg-surface-2 px-3 py-2 leading-relaxed">{turn.question}</div>
    <Card className="p-3">
      <div className="mb-2 flex items-center gap-2"><span className="font-mono text-xs text-muted">SQL</span><Badge variant={statusVariant(turn.status)}>{turn.status}</Badge>{turn.rowCount !== null && <span className="text-xs text-muted">{turn.rowCount} rows</span>}</div>
      <textarea ref={editor} spellCheck={false} value={turn.sql} onChange={(event) => onSqlChange(turn.chatId, event.target.value)} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); onRun(turn.chatId, turn.sql); } }} className="min-h-16 max-h-72 w-full overflow-auto rounded-md border border-border bg-surface-2 p-2 font-mono text-xs leading-relaxed outline-none focus:border-accent focus:ring-1 focus:ring-accent" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button onClick={() => onRun(turn.chatId, turn.sql)} disabled={!turn.sql.trim()} loading={turn.running}><Play className="size-3.5" />{turn.status === "generated" ? "Run query" : "Run again"}</Button>
        {turn.running && <Spinner label="Running query…" />}
      </div>
      {turn.error && <Alert className="mt-3">{turn.error}</Alert>}
      {turn.notice && <div className="mt-3">{turn.notice === "Generating SQL…" ? <Spinner label={turn.notice} elapsed /> : <Alert variant="info">{turn.notice}</Alert>}</div>}
      {turn.confirmation && <Alert variant="warning" className="mt-3"><div>{turn.confirmation}</div><div className="mt-2 flex gap-2"><Button variant="secondary" onClick={() => onRun(turn.chatId, turn.sql, true)}>I understand, run query</Button><Button variant="ghost" onClick={() => onDismissWarning(turn.chatId)}>Cancel</Button></div></Alert>}
      {turn.result?.retried && <p className="mt-3 text-xs text-muted">The first attempt failed, so the model corrected the query once. Showing the SQL that ran.</p>}
      {turn.result && <div className="mt-3 space-y-2">{turn.result.columns.length > 0 ? <ResultTable columns={turn.result.columns} rows={turn.result.rows} /> : <p className="text-xs text-muted">Query executed. {turn.rowCount} rows affected.</p>}{turn.result.truncated && <p className="text-xs text-muted">Result truncated. Showing the first {turn.rowCount} rows.</p>}</div>}
      {turn.status === "executed" && !turn.result && <p className="mt-3 text-xs text-muted">This query ran earlier ({turn.rowCount} rows). Run again to view the rows.</p>}
    </Card>
    {turn.executedSql !== null && /^(select|with)\b/i.test(turn.executedSql.trim()) && <div className="flex gap-2"><Button variant="secondary" title="Uses the last query that ran successfully." disabled={turn.summarizing !== null} loading={turn.summarizing === "summary"} onClick={() => onSummarize(turn.chatId, "summary")}><Sparkles className="size-3.5" />Summarize</Button><Button variant="secondary" title="Uses the last query that ran successfully." disabled={turn.summarizing !== null} loading={turn.summarizing === "analysis"} onClick={() => onSummarize(turn.chatId, "analysis")}><ChartNoAxesColumn className="size-3.5" />Analyze</Button></div>}
    {turn.summaries.map((summary) => <Card key={summary.id} className="p-3"><div className="mb-2 text-xs text-muted">{summary.kind === "summary" ? "Summary" : "Analysis"} · {new Date(summary.created_at).toLocaleString()}</div><div className="whitespace-pre-wrap leading-relaxed">{summary.text}</div>{summary.note && <div className="mt-2 text-xs text-muted">{summary.note}</div>}</Card>)}
  </article>;
}
