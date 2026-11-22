import { LoaderCircle } from "lucide-react";
import { forwardRef, useEffect, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";

const buttonStyles = {
  primary: "bg-accent-solid border border-accent/40 text-fg hover:bg-accent-solid-hover",
  secondary: "bg-surface-2 border border-border-strong text-fg hover:border-muted",
  ghost: "bg-transparent text-muted hover:text-fg",
};

export function Button({ className = "", variant = "primary", loading = false, children, disabled, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof buttonStyles; loading?: boolean }): JSX.Element {
  return <button className={`h-8 rounded-md px-3 inline-flex items-center justify-center gap-2 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${buttonStyles[variant]} ${className}`} disabled={disabled || loading} {...props}>
    {loading && <LoaderCircle className="size-3.5 animate-spin" />}{children}
  </button>;
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { label?: string; error?: string }>(({ className = "", label, error, id, ...props }, ref) => (
  <label className="block">
    {label && <span className="mb-1 block text-xs text-muted">{label}</span>}
    <input ref={ref} id={id} className={`h-9 w-full rounded-md border border-border bg-surface-2 px-2.5 text-sm outline-none placeholder:text-dim focus:border-accent focus:ring-1 focus:ring-accent ${className}`} {...props} />
    {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
  </label>
));
Input.displayName = "Input";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }): JSX.Element {
  return <section className={`rounded-lg border border-border bg-surface ${className}`}>{children}</section>;
}

export function Alert({ children, variant = "error", className = "" }: { children: ReactNode; variant?: "error" | "warning" | "info"; className?: string }): JSX.Element {
  const styles = { error: "border-danger/40 bg-danger/10 text-danger", warning: "border-warning/40 bg-warning/10 text-warning", info: "border-accent/30 bg-accent/10 text-fg" };
  return <div role="alert" className={`rounded-md border px-3 py-2 text-xs ${styles[variant]} ${className}`}>{children}</div>;
}

export function Spinner({ label, elapsed = false }: { label?: string; elapsed?: boolean }): JSX.Element {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!elapsed) return;
    const interval = window.setInterval(() => setSeconds((current) => current + 1), 1000);
    return () => window.clearInterval(interval);
  }, [elapsed]);
  return <span className="inline-flex items-center gap-2 text-xs text-muted"><LoaderCircle className="size-4 animate-spin text-accent" />{label}{elapsed && <span>{seconds}s</span>}</span>;
}

export function Badge({ children, variant = "neutral" }: { children: ReactNode; variant?: "neutral" | "success" | "danger" }): JSX.Element {
  const styles = { neutral: "border-border-strong bg-surface-2 text-muted", success: "border-accent/40 bg-accent/10 text-accent", danger: "border-danger/40 bg-danger/10 text-danger" };
  return <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium ${styles[variant]}`}>{children}</span>;
}
