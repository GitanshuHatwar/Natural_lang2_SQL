import { DatabaseZap } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../lib/session";

export const APP_NAME = "NL2SQL";

export function Layout({ children }: { children: ReactNode }): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const { session, clearSession } = useSession();
  const isLanding = location.pathname === "/";
  const isChat = location.pathname === "/chat";
  return <>
    <header className="sticky top-0 z-20 h-12 border-b border-border bg-bg/80 backdrop-blur">
      <div className="mx-auto flex h-full max-w-5xl items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <Link to="/" className="inline-flex items-center gap-2 font-semibold tracking-tight text-fg"><DatabaseZap className="size-4 text-accent" />{APP_NAME}</Link>
          {isChat && session && <span className="border-l border-border pl-3 text-xs text-muted">/ {session.database}</span>}
        </div>
        <nav className="flex items-center gap-2">
          {isLanding && <><a className="h-8 px-3 inline-flex items-center text-xs text-muted hover:text-fg" href="#how-it-works">How it works</a><Link className="h-8 rounded-md border border-accent/40 bg-accent-solid px-3 inline-flex items-center text-xs font-medium hover:bg-accent-solid-hover" to="/connect">Connect database</Link></>}
          {location.pathname === "/connect" && <Link className="h-8 px-3 inline-flex items-center text-xs text-muted hover:text-fg" to="/">Home</Link>}
          {isChat && session && <><span className="hidden items-center gap-1.5 rounded border border-accent/30 bg-accent/10 px-2 py-1 font-mono text-[10px] text-accent sm:inline-flex"><i className="size-1.5 rounded-full bg-accent" />{session.host}:{session.port}</span><button className="h-8 px-3 text-xs text-muted hover:text-fg" onClick={() => { clearSession(); navigate("/connect"); }}>Switch database</button></>}
        </nav>
      </div>
    </header>
    <main>{children}</main>
  </>;
}
