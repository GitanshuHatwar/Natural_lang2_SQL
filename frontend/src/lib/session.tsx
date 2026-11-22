import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "./api";

export type Session = { sessionId: string; connectionId: number; host: string; port: number; database: string; hasMetadata: boolean };
type SessionContextValue = { session: Session | null; setSession: (session: Session) => void; clearSession: () => void; markExtracted: () => void; markMetadataStale: () => void };
const SessionContext = createContext<SessionContextValue | null>(null);
const STORAGE_KEY = "nl2sql.session";

function readSession(): Session | null {
  try {
    const item: unknown = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "null");
    if (typeof item !== "object" || item === null) return null;
    const value = item as Record<string, unknown>;
    if (typeof value.sessionId !== "string" || typeof value.connectionId !== "number" || typeof value.host !== "string" || typeof value.port !== "number" || typeof value.database !== "string" || typeof value.hasMetadata !== "boolean") return null;
    return { sessionId: value.sessionId, connectionId: value.connectionId, host: value.host, port: value.port, database: value.database, hasMetadata: value.hasMetadata };
  } catch { return null; }
}

export function SessionProvider({ children }: { children: ReactNode }): JSX.Element {
  const [session, updateSession] = useState<Session | null>(readSession);
  const setSession = useCallback((next: Session) => {
    updateSession(next);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }, []);
  const clearSession = useCallback(() => {
    updateSession(null);
    sessionStorage.removeItem(STORAGE_KEY);
  }, []);
  const markExtracted = useCallback(() => {
    updateSession((current) => {
      if (!current) return current;
      const next = { ...current, hasMetadata: true };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);
  const markMetadataStale = useCallback(() => {
    updateSession((current) => {
      if (!current) return current;
      const next = { ...current, hasMetadata: false };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);
  const value = useMemo(() => ({ session, setSession, clearSession, markExtracted, markMetadataStale }), [session, setSession, clearSession, markExtracted, markMetadataStale]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used within SessionProvider");
  return value;
}

export function useSessionErrorHandler(): (error: unknown) => boolean {
  const { clearSession } = useSession();
  const navigate = useNavigate();
  return useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) {
      clearSession();
      navigate("/connect", { state: { notice: "Session expired. Please reconnect." } });
      return true;
    }
    return false;
  }, [clearSession, navigate]);
}
