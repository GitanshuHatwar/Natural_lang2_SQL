import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { connect, extract, listConnections } from "../lib/api";
import type { ConnectionSummary } from "../lib/types";
import { useSession, useSessionErrorHandler } from "../lib/session";
import { Alert, Badge, Button, Card, Input, Spinner } from "../components/ui";

type Stage = "idle" | "connecting" | "connected" | "extracting" | "extracted";
type Form = { host: string; port: string; database: string; username: string; password: string };

function message(error: unknown): string { return error instanceof Error ? error.message : "Something went wrong."; }

function relativeTime(timestamp: string): string {
  const seconds = Math.round((new Date(timestamp).getTime() - Date.now()) / 1000);
  const unit = Math.abs(seconds) < 60 ? "second" : Math.abs(seconds) < 3600 ? "minute" : Math.abs(seconds) < 86400 ? "hour" : "day";
  const divisor = unit === "second" ? 1 : unit === "minute" ? 60 : unit === "hour" ? 3600 : 86400;
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(Math.round(seconds / divisor), unit);
}

export function Connect(): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const { session, setSession, markExtracted } = useSession();
  const handleSessionError = useSessionErrorHandler();
  const usernameInput = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState<Form>({ host: session?.host ?? "localhost", port: String(session?.port ?? 3306), database: session?.database ?? "", username: "", password: "" });
  const [stage, setStage] = useState<Stage>(session ? "connected" : "idle");
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof Form, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [extractResult, setExtractResult] = useState<{ count: number; tables: string[] } | null>(null);
  const [recent, setRecent] = useState<ConnectionSummary[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState<string | null>(null);
  const notice = (location.state as { notice?: string } | null)?.notice;

  const loadRecent = async (): Promise<void> => {
    setRecentLoading(true); setRecentError(null);
    try { setRecent(await listConnections()); } catch (caught) { setRecentError(message(caught)); } finally { setRecentLoading(false); }
  };
  useEffect(() => { void loadRecent(); }, []);

  const update = (field: keyof Form, value: string) => setForm((current) => ({ ...current, [field]: value }));
  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault(); setError(null);
    const errors: Partial<Record<keyof Form, string>> = {};
    if (!form.host.trim()) errors.host = "Host is required.";
    if (!form.database.trim()) errors.database = "Database is required.";
    if (!form.username.trim()) errors.username = "Username is required.";
    const port = Number(form.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) errors.port = "Enter a port from 1 to 65535.";
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setStage("connecting");
    try {
      const response = await connect({ host: form.host.trim(), port, database: form.database.trim(), username: form.username, password: form.password });
      setSession({ sessionId: response.session_id, connectionId: response.connection_id, host: form.host.trim(), port, database: form.database.trim(), hasMetadata: response.has_metadata });
      setForm((current) => ({ ...current, password: "" }));
      setStage("connected");
      void loadRecent();
    } catch (caught) { setError(message(caught)); setStage("idle"); }
  };
  const runExtract = async (): Promise<void> => {
    if (!session) return;
    setError(null); setStage("extracting");
    try {
      const response = await extract(session.sessionId);
      markExtracted(); setExtractResult({ count: response.table_count, tables: response.tables }); setStage("extracted");
    } catch (caught) {
      if (!handleSessionError(caught)) { setError(message(caught)); setStage("connected"); }
    }
  };
  const prefill = (connection: ConnectionSummary): void => {
    setForm((current) => ({ ...current, host: connection.host, port: String(connection.port), database: connection.db_name }));
    setStage("idle"); setError(null);
    window.setTimeout(() => usernameInput.current?.focus(), 0);
  };
  const isConnected = stage === "connected" || stage === "extracting" || stage === "extracted";
  const metadataAvailable = isConnected && session?.hasMetadata && !extractResult;

  return <div className="mx-auto max-w-5xl px-4 py-8">
    {notice && <Alert variant="warning" className="mb-4">{notice}</Alert>}
    <div className="grid gap-4 lg:grid-cols-3"><div className="space-y-4 lg:col-span-2">
      <Card className="p-5"><div className="mb-4"><h1 className="font-semibold tracking-tight">1 · Connect</h1><p className="mt-1 text-xs text-muted">Connect to a local MySQL database.</p></div>
        {isConnected ? <div className="flex items-center justify-between gap-3"><p>Connected to <span className="font-mono">{form.database}</span> at <span className="font-mono">{form.host}:{form.port}</span></p><Button variant="ghost" onClick={() => setStage("idle")}>Change</Button></div> : <form className="space-y-3" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-[1fr_9rem]"><Input label="Host" value={form.host} onChange={(event) => update("host", event.target.value)} error={fieldErrors.host} autoComplete="off" /><Input label="Port" type="number" value={form.port} onChange={(event) => update("port", event.target.value)} error={fieldErrors.port} /></div>
          <Input label="Database" value={form.database} onChange={(event) => update("database", event.target.value)} error={fieldErrors.database} autoComplete="off" />
          <Input ref={usernameInput} label="Username" value={form.username} onChange={(event) => update("username", event.target.value)} error={fieldErrors.username} autoComplete="off" />
          <Input label="Password" type="password" value={form.password} onChange={(event) => update("password", event.target.value)} autoComplete="off" />
          {error && <Alert>{error}</Alert>}<p className="text-xs leading-relaxed text-muted">Use a read-only MySQL user. Credentials are held in the backend's memory for this session only and are never saved.</p><Button type="submit" loading={stage === "connecting"}>Connect</Button>
        </form>}
      </Card>
      <Card className={`p-5 ${!isConnected ? "opacity-50" : ""}`}><div className="mb-4"><h2 className="font-semibold tracking-tight">2 · Extract</h2><p className="mt-1 text-xs text-muted">Explore structure and a small sample of data.</p></div>
        {isConnected && error && <Alert className="mb-3">{error}</Alert>}
        {!isConnected ? <p className="text-muted">Connect first to enable extraction.</p> : stage === "extracting" ? <Spinner label="Exploring tables…" elapsed /> : extractResult ? <div className="space-y-3"><p><span className="font-medium">{extractResult.count} tables extracted</span></p><div className="max-h-40 overflow-auto flex flex-wrap gap-1.5">{extractResult.tables.map((table) => <span key={table} className="rounded border border-border bg-surface-2 px-1.5 py-1 font-mono text-[10px]">{table}</span>)}</div><Button onClick={() => navigate("/chat")}>Start chatting</Button></div> : metadataAvailable ? <div className="space-y-3"><p className="text-muted">Metadata from a previous extraction is available.</p><div className="flex gap-2"><Button onClick={() => navigate("/chat")}>Continue to chat</Button><Button variant="secondary" onClick={() => void runExtract()}>Re-extract</Button></div></div> : <div className="space-y-3"><p className="text-muted">This database hasn't been explored yet. Extraction reads table structure and a small sample of data.</p><Button onClick={() => void runExtract()}>Extract database</Button></div>}
      </Card>
    </div>
    <Card className="h-fit p-4"><h2 className="font-semibold tracking-tight">Recent connections</h2>{recentLoading ? <div className="mt-4"><Spinner label="Loading…" /></div> : recentError ? <div className="mt-4 space-y-2"><Alert>{recentError}</Alert><Button variant="secondary" onClick={() => void loadRecent()}>Retry</Button></div> : recent.length === 0 ? <p className="mt-4 text-muted">No previous connections.</p> : <div className="mt-3 divide-y divide-border">{recent.map((connection) => <button key={connection.id} onClick={() => prefill(connection)} className="w-full py-3 text-left hover:text-accent"><div className="flex items-center justify-between gap-2"><span className="font-medium">{connection.db_name}</span>{connection.has_metadata && <Badge>metadata</Badge>}</div><div className="mt-1 font-mono text-[10px] text-muted">{connection.host}:{connection.port}</div><div className="mt-1 text-[10px] text-dim">{relativeTime(connection.last_used_at)}</div></button>)}</div>}</Card>
    </div>
  </div>;
}
