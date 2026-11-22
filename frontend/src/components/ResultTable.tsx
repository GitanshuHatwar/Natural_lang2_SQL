import type { Cell } from "../lib/types";

function value(cell: Cell): string {
  if (cell === null) return "NULL";
  if (typeof cell === "boolean") return cell ? "true" : "false";
  return String(cell);
}

export function ResultTable({ columns, rows }: { columns: string[]; rows: Cell[][] }): JSX.Element {
  return <div className="max-h-[420px] overflow-auto rounded-md border border-border">
    <table className="w-full border-collapse font-mono text-xs">
      <thead className="sticky top-0 bg-surface-2 text-muted"><tr>{columns.map((column, index) => <th key={index} className="border-b border-border px-3 py-2 text-left font-medium whitespace-nowrap">{column}</th>)}</tr></thead>
      <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex} className="hover:bg-surface-2/70">{row.map((cell, columnIndex) => <td key={columnIndex} title={value(cell)} className={`max-w-xs truncate border-b border-border/60 px-3 py-2 ${cell === null ? "italic text-dim" : ""}`}>{value(cell)}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}
