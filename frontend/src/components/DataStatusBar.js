"use client";

import { useEffect, useState } from "react";
import axios from "axios";

const POLL_MS = 45000;

const SHEET_LABELS = {
  sale: "Sale",
  onhand: "OnHand",
  master: "Item Master",
  grpo_detail: "GRPO Detail",
  whs_code: "Whs Code",
};

export default function DataStatusBar() {
  const [state, setState] = useState(null);
  const [counts, setCounts] = useState(null);
  const [err, setErr] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const load = async () => {
    try {
      const [st, ct] = await Promise.all([
        axios.get("/api/data_status", { responseType: "json" }),
        axios.get("/api/data_line_counts", { responseType: "json" }).catch(() => ({ data: null })),
      ]);
      setState(st.data);
      setErr(null);
      if (ct?.data && !ct.data.error) setCounts(ct.data);
    } catch (e) {
      setErr(e?.message || "Status unavailable");
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, []);

  const s = state?.state;
  const label =
    s === "ready"
      ? "Data ready"
      : s === "loading"
        ? "Loading workbook..."
        : s === "error"
          ? "Load error"
          : s === "idle"
            ? "Idle"
            : "Unknown";

  const tone =
    s === "ready"
      ? "bg-emerald-600"
      : s === "loading"
        ? "bg-[var(--nichi-yellow)] text-[var(--nichi-blue-dark)]"
        : s === "error"
          ? "bg-red-600"
          : "bg-slate-500";

  const textColor = s === "loading" ? "text-[var(--nichi-blue-dark)]" : "text-white";

  const fn = state?.filename;
  const fd = counts?.filedate || state?.filedate;

  // Build inline summary
  const parts = [];
  if (fd) parts.push(`As of: ${fd}`);
  if (counts?.sale != null) {
    const totalRows = Object.entries(SHEET_LABELS)
      .map(([k]) => counts[k])
      .filter((v) => v != null)
      .reduce((a, b) => a + b, 0);
    parts.push(`${totalRows.toLocaleString()} rows loaded`);
  }

  // Build sheet detail rows
  const sheetDetails = Object.entries(SHEET_LABELS)
    .map(([key, label]) => ({ key, label, count: counts?.[key] }))
    .filter((s) => s.count != null);

  return (
    <div className={`no-print ${tone} ${textColor}`}>
      <div
        className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 text-xs cursor-pointer select-none"
        role="status"
        onClick={() => s === "ready" && sheetDetails.length > 0 && setExpanded((e) => !e)}
        title={s === "ready" && sheetDetails.length > 0 ? "Click to show/hide sheet details" : undefined}
      >
        <span className="font-semibold flex items-center gap-1.5">
          {s === "ready" && (
            <span className="w-1.5 h-1.5 rounded-full bg-white inline-block animate-pulse" />
          )}
          {s === "loading" && (
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {label}
        </span>
        {parts.length > 0 && <span className="opacity-80">{parts.join(" \u00B7 ")}</span>}
        {fn && <span className="opacity-60 truncate max-w-[40vw]">{fn}</span>}
        {err && <span className="opacity-80">{err}</span>}
        {state?.error && s === "error" && (
          <span className="opacity-80 truncate max-w-[50vw]" title={state.error}>
            {state.error}
          </span>
        )}
        {s === "ready" && sheetDetails.length > 0 && (
          <span className="opacity-60 ml-auto">{expanded ? "\u25B2" : "\u25BC"}</span>
        )}
      </div>
      {expanded && sheetDetails.length > 0 && (
        <div className="flex flex-wrap gap-x-6 gap-y-0.5 px-4 pb-1.5 text-xs opacity-80">
          {sheetDetails.map((s) => (
            <span key={s.key}>
              {s.label}: <strong>{s.count.toLocaleString()}</strong>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
