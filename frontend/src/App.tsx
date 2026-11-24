import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { SessionProvider, useSession } from "./lib/session";
import { Landing } from "./pages/Landing";
import { Connect } from "./pages/Connect";
import { Chat } from "./pages/Chat";

function GuardedChat(): JSX.Element {
  const { session } = useSession();
  return session?.hasMetadata ? <Chat /> : <Navigate to="/connect" replace />;
}

function Application(): JSX.Element {
  return <SessionProvider><Layout><Routes><Route path="/" element={<Landing />} /><Route path="/connect" element={<Connect />} /><Route path="/chat" element={<GuardedChat />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></Layout></SessionProvider>;
}

export function App(): JSX.Element { return <BrowserRouter><Application /></BrowserRouter>; }
