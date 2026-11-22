export type Cell = string | number | boolean | null;

export type ConnectRequest = { host: string; port: number; username: string; password: string; database: string };
export type ConnectResponse = { session_id: string; connection_id: number; has_metadata: boolean };
export type ConnectionSummary = { id: number; host: string; port: number; db_name: string; last_used_at: string; has_metadata: boolean };
export type ExtractResponse = { connection_id: number; table_count: number; tables: string[]; extracted_at: string };
export type GenerateSqlResponse = { chat_id: number; sql: string };
export type ExecuteResponse = { chat_id: number; sql: string; retried: boolean; columns: string[]; rows: Cell[][]; row_count: number; truncated: boolean; metadata_stale: boolean };
export type SummaryMode = "summary" | "analysis";
export type SummarizeResponse = { summary_id: number; mode: SummaryMode; text: string; rows_analyzed: number; truncated: boolean };
export type ChatStatus = "generated" | "executed" | "error";
export type SummaryRecord = { id: number; kind: SummaryMode; text: string; created_at: string };
export type ChatRecord = {
  id: number; question: string; generated_sql: string; executed_sql: string | null;
  row_count: number | null; status: ChatStatus; error: string | null; created_at: string;
  summaries: SummaryRecord[];
};
