"use client";

import { useState } from "react";

const prettify = (k) =>
  k.replace(/_/g, " ")
   .replace(/\bthb\b/gi, "THB").replace(/\bqty\b/gi, "Qty").replace(/\bpct\b/gi, "%")
   .replace(/\bd1\b/gi, "D1").replace(/^\w/, (c) => c.toUpperCase());

const fmtCell = (v) =>
  typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
                        : (v == null ? "" : String(v));

function toCsv(cols, rows) {
  const esc = (v) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [cols.map(esc).join(",")];
  for (const r of rows) lines.push(cols.map((c) => esc(r[c])).join(","));
  return lines.join("\n");
}

// The single table the assistant chose to show: its columns, its rows (already
// selected/sorted/limited by the model to fit the question). `total_available`
// notes how many rows exist in full when this is a preview.
export default function DataTable({ title, columns, rows, total_available }) {
  const [open, setOpen] = useState(true);
  if (!rows || !rows.length) return null;
  const cols = (columns && columns.length) ? columns : Object.keys(rows[0]);
  const more = total_available && total_available > rows.length;

  const download = () => {
    const blob = new Blob([toCsv(cols, rows)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = ((title || "toyvault_data").replace(/[^\w]+/g, "_").toLowerCase()) + ".csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mt-1 rounded-lg border border-gray-200 bg-white">
      <div className="flex items-center gap-2 px-2 py-1.5 text-xs">
        <button onClick={() => setOpen((o) => !o)} className="font-medium text-[var(--nichi-blue)] truncate">
          {open ? "▾" : "▸"} {title || "Data"} · {rows.length}{more ? ` of ${total_available}` : ""} rows
        </button>
        <div className="flex-1" />
        <button onClick={download}
                className="px-2 py-0.5 rounded border border-[var(--nichi-blue)] text-[var(--nichi-blue)] hover:bg-blue-50 whitespace-nowrap">
          ⬇ CSV ({rows.length})
        </button>
      </div>
      {open && (
        <div className="overflow-auto max-h-80 border-t border-gray-100">
          <table className="text-[11px] border-collapse w-full">
            <thead className="bg-gray-100 sticky top-0">
              <tr>{cols.map((c) => (
                <th key={c} className="px-2 py-1 text-left border-b border-gray-200 whitespace-nowrap font-semibold">{prettify(c)}</th>
              ))}</tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={i % 2 ? "bg-gray-50/60" : ""}>
                  {cols.map((c) => (
                    <td key={c} className="px-2 py-1 border-b border-gray-100 whitespace-nowrap tabular-nums">{fmtCell(r[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
