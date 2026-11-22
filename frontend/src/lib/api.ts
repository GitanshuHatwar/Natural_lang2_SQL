import type { ChatRecord, ConnectRequest, ConnectResponse, ConnectionSummary, ExecuteResponse, ExtractResponse, GenerateSqlResponse, SummarizeResponse, SummaryMode } from "./types";

declare global {
  interface ImportMetaEnv { readonly VITE_API_BASE_URL?: string; }
  interface ImportMeta { readonly env: ImportMetaEnv; }
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function errorMessage(value: unknown): string {
  if (typeof value === "object" && value !== null && "detail" in value) {
    const detail = (value as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : String(item)).join("; ");
    }
  }
  return "The backend returned an unexpected error.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the backend at ${BASE_URL}. Is it running?`);
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(payload));
  return payload as T;
}

export const connect = (body: ConnectRequest): Promise<ConnectResponse> => request("/connect", { method: "POST", body: JSON.stringify(body) });
export const listConnections = (): Promise<ConnectionSummary[]> => request("/connections");
export const extract = (sessionId: string): Promise<ExtractResponse> => request("/extract", { method: "POST", body: JSON.stringify({ session_id: sessionId }) });
export const generateSql = (sessionId: string, question: string): Promise<GenerateSqlResponse> => request("/generate-sql", { method: "POST", body: JSON.stringify({ session_id: sessionId, question }) });
export const execute = (sessionId: string, chatId: number, sql: string): Promise<ExecuteResponse> => request("/execute", { method: "POST", body: JSON.stringify({ session_id: sessionId, chat_id: chatId, sql }) });
export const summarize = (sessionId: string, chatId: number, mode: SummaryMode): Promise<SummarizeResponse> => request("/summarize", { method: "POST", body: JSON.stringify({ session_id: sessionId, chat_id: chatId, mode }) });
export const listChats = (connectionId: number): Promise<ChatRecord[]> => request(`/connections/${connectionId}/chats`);
