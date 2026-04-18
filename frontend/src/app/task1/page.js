"use client";

import { useMemo, useState } from "react";
import api from "@/utils/api";

function parseLinesToBarcodes(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function Task1() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [result, setResult] = useState(null);

  const barcodes = useMemo(() => parseLinesToBarcodes(input), [input]);

  const run = async () => {
    setLoading(true);
    setErr(null);
    setResult(null);
    try {
      if (barcodes.length === 0) throw new Error("Paste at least 1 barcode");
      const res = await api.post(
        "/api/match",
        { barcodes },
        { responseType: "json" }
      );
      setResult(res.data);
    } catch (e) {
      setErr(e?.response?.data?.details || e?.message || "Failed");
    } finally {
      setLoading(false);
    }
  };

  const rows = useMemo(() => {
    const items = result?.item_numbers;
    if (!Array.isArray(items)) return [];
    return barcodes.map((bc, i) => ({ barcode: bc, item: items[i] ?? null }));
  }, [result, barcodes]);

  const exportCsv = () => {
    const header = "barcode,item_number";
    const lines = rows.map((r) => {
      const b = String(r.barcode).replaceAll('"', '""');
      const it = (r.item == null ? "" : String(r.item)).replaceAll('"', '""');
      return `"${b}","${it}"`;
    });
    const csv = [header, ...lines].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "barcode_to_itemcode.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)] text-slate-800 p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Barcode to Itemcode</h1>
            <p className="text-sm text-slate-500 mt-1">
              Paste barcodes (one per line). Uses backend `/api/barcodes` via BFF.
            </p>
          </div>
        </header>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <label className="text-sm font-medium">Barcodes</label>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={8}
            className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-mono"
            placeholder={"8850000000000\n8850000000001"}
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={run}
              disabled={loading}
              className="rounded-lg bg-[var(--nichi-blue)] text-white px-4 py-2 text-sm hover:bg-[var(--nichi-blue-dark)] disabled:opacity-50"
            >
              {loading ? "Matching…" : `Match (${barcodes.length})`}
            </button>
            <button
              type="button"
              onClick={() => {
                setInput("");
                setResult(null);
                setErr(null);
              }}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm hover:bg-slate-100"
            >
              Clear
            </button>
            {rows.length > 0 && (
              <button
                type="button"
                onClick={exportCsv}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm hover:bg-slate-100"
              >
                Download CSV
              </button>
            )}
          </div>
          {err && <p className="mt-3 text-sm text-red-600">{String(err)}</p>}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="text-left px-3 py-2 font-medium">Barcode</th>
                <th className="text-left px-3 py-2 font-medium">Item No.</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={`${r.barcode}-${i}`}
                  className="border-b border-slate-100"
                >
                  <td className="px-3 py-2 font-mono whitespace-nowrap">
                    {r.barcode}
                  </td>
                  <td className="px-3 py-2 font-mono whitespace-nowrap">
                    {r.item ?? ""}
                  </td>
                </tr>
              ))}
              {!loading && rows.length === 0 && (
                <tr>
                  <td className="px-3 py-4 text-slate-500" colSpan={2}>
                    No results yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

