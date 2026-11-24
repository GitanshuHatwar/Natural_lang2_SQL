import { BrainCircuit, Database, FileSearch, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { APP_NAME } from "../components/Layout";
import { Card } from "../components/ui";

const exampleSql = `SELECT c.name, COUNT(o.id) AS order_count
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.id
WHERE o.created_at >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
GROUP BY c.id, c.name
ORDER BY order_count DESC
LIMIT 5;`;

export function Landing(): JSX.Element {
  const scroll = () => document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" });
  return <div className="mx-auto max-w-5xl px-4">
    <section className="relative overflow-hidden py-20 text-center sm:py-28">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-80 bg-[radial-gradient(ellipse_at_top,rgba(62,207,142,0.12),transparent_60%)]" />
      <div className="relative mx-auto max-w-3xl"><span className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs text-accent">Prototype · runs locally with Ollama</span><h1 className="mt-5 text-4xl font-semibold tracking-tight sm:text-5xl">Ask your database in plain English.</h1><p className="mt-4 text-base leading-relaxed text-muted">Connect a MySQL database, ask a question, review the generated SQL, run it, and get a plain-English summary of the results.</p><div className="mt-7 flex justify-center gap-3"><Link to="/connect" className="h-8 rounded-md border border-accent/40 bg-accent-solid px-3 inline-flex items-center text-xs font-medium hover:bg-accent-solid-hover">Connect a database</Link><button className="h-8 rounded-md border border-border-strong bg-surface-2 px-3 text-xs font-medium hover:border-muted" onClick={scroll}>How it works</button></div></div>
      <Card className="relative mx-auto mt-12 max-w-3xl p-4 text-left font-mono text-xs"><div className="mb-3 flex items-center justify-between text-muted"><span>Which customers placed the most orders last month?</span><span className="rounded border border-border px-1.5 py-0.5 text-[10px]">Example</span></div><pre className="overflow-auto text-accent whitespace-pre-wrap">{exampleSql}</pre></Card>
    </section>
    <section id="how-it-works" className="py-12"><h2 className="text-xl font-semibold tracking-tight">How it works</h2><div className="mt-5 grid gap-3 md:grid-cols-3">{[["1", "Connect", "Point it at a local MySQL database using an account with only the permissions you need."], ["2", "Extract", "It explores tables, columns, keys, and sample values once, and remembers them."], ["3", "Ask", "Type a question. Review the SQL, run it, then summarize or analyze the result."]].map(([number, title, description]) => <Card key={number} className="p-4"><span className="font-mono text-xs text-accent">{number}</span><h3 className="mt-3 font-semibold">{title}</h3><p className="mt-1 leading-relaxed text-muted">{description}</p></Card>)}</div></section>
    <section className="py-12"><h2 className="text-xl font-semibold tracking-tight">Features</h2><div className="mt-5 grid gap-3 sm:grid-cols-2">{[[BrainCircuit, "Natural language to SQL", "No need to remember syntax or table names."], [FileSearch, "Review before running", "Generated SQL is shown and editable. Nothing runs until you press Run. Local models can make mistakes, so you stay in control."], [Database, "Summarize & analyze", "Turn a result table into a short answer or a list of notable patterns."], [ShieldCheck, "Local by design", "Uses a model on your machine through Ollama. Your database credentials are never saved."]].map(([Icon, title, description]) => { const FeatureIcon = Icon as typeof BrainCircuit; return <Card key={title as string} className="p-4"><FeatureIcon className="size-4 text-accent" /><h3 className="mt-3 font-semibold">{title as string}</h3><p className="mt-1 leading-relaxed text-muted">{description as string}</p></Card>; })}</div></section>
    <footer className="border-t border-border py-8 text-xs text-muted">{APP_NAME} · prototype</footer>
  </div>;
}
