"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
// NOTE: no <Navbar /> here — app/layout.js already renders it for every page.
// Adding one produced a duplicate nav bar.

const fmtThb = (v) =>
  v == null ? "—" : "฿" + Math.round(v).toLocaleString();
const fmtQty = (v) => (v == null ? "—" : Math.round(v).toLocaleString());

// Matches the "19/mo" / "7.0/mo" style already used on the location pages:
// whole numbers above 10, one decimal below, so small movers stay legible.
const fmtVelocity = (v) => {
  if (v == null) return <span className="text-gray-300">—</span>;
  if (v === 0) return <span className="text-gray-400">0/mo</span>;
  return <span>{v >= 10 ? Math.round(v) : v.toFixed(1)}/mo</span>;
};

// "2026-05" -> "May 25"
const monthLabel = (p) => {
  const [y, m] = String(p).split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[Number(m) - 1] || p} ${String(y).slice(2)}`;
};

export default function LocationPlanogramPage() {
  const params = useParams();
  // Location names can contain slashes and Thai characters; Next gives us the
  // raw segment, so decode explicitly.
  const location = decodeURIComponent(
    Array.isArray(params.location) ? params.location.join("/") : params.location || ""
  );

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [edits, setEdits] = useState({});     // { item_code: value-as-string }
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [monthsRange, setMonthsRange] = useState("3m"); // "3m" | "year" | "2y"
  const [monthMetric, setMonthMetric] = useState("revenue"); // "revenue" | "qty"
  const PAGE_SIZE = 50;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/location_planogram?location=${encodeURIComponent(location)}&all_items=true&months_range=${monthsRange}`
      );
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
      setData(json);
      setEdits({});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [location, monthsRange]);

  useEffect(() => {
    if (location) load();
  }, [location, load]);

  const items = data?.items || [];
  const months = data?.months || [];

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (i) =>
        i.item_code.toLowerCase().includes(q) ||
        (i.item_name || "").toLowerCase().includes(q) ||
        (i.brand || "").toLowerCase().includes(q)
    );
  }, [items, search]);

  // The catalog is large (~1k SKUs), so paginate. Reset to page 1 whenever the
  // filter changes so the user isn't stranded on an out-of-range page.
  useEffect(() => { setPage(1); }, [search]);
  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const paged = useMemo(
    () => visible.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [visible, safePage]
  );

  // Only send what actually changed — the save is a merge, so untouched rows
  // must not be re-sent (they'd churn updated_at for no reason).
  const dirty = useMemo(() => {
    const out = {};
    for (const it of items) {
      const raw = edits[it.item_code];
      if (raw === undefined) continue;
      const n = raw === "" ? 0 : Number(raw);
      if (Number.isFinite(n) && n !== it.min_qty) out[it.item_code] = n;
    }
    return out;
  }, [items, edits]);

  const dirtyCount = Object.keys(dirty).length;

  const invalid = useMemo(() => {
    return Object.entries(edits).filter(([, raw]) => {
      if (raw === "") return false;
      const n = Number(raw);
      return !Number.isFinite(n) || n < 0 || !Number.isInteger(n);
    });
  }, [edits]);

  async function onSave() {
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await fetch(
        `/api/location_planogram?location=${encodeURIComponent(location)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: dirty }),
        }
      );
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
      setSaveMsg({ kind: "ok", text: `Saved ${Object.keys(dirty).length} SKU setting(s).` });
      await load();
    } catch (e) {
      setSaveMsg({ kind: "err", text: e.message });
    } finally {
      setSaving(false);
    }
  }

  function downloadCsv() {
    const isQty = monthMetric === "qty";
    const head = [
      "Rank", "Item Code", "Item Name", "Brand", "Revenue (THB, Actual)",
      ...months.map((m) => `${isQty ? "Units" : "Revenue"} ${monthLabel(m)}${isQty ? " (units)" : " (THB)"}`),
      "Monthly Velocity (units/mo)", "Sold Qty", "On-Hand Qty", "Planogram Min Qty",
    ];
    const rows = items.map((i) => [
      i.rank, i.item_code, `"${(i.item_name || "").replace(/"/g, '""')}"`,
      `"${(i.brand || "").replace(/"/g, '""')}"`,
      i.sold_thb,
      ...months.map((_m, mi) => (isQty ? i.month_qty?.[mi] : i.month_revenue?.[mi]) ?? 0),
      i.monthly_velocity ?? 0,
      i.sold_qty, i.onhand_qty,
      edits[i.item_code] !== undefined ? edits[i.item_code] : i.min_qty,
    ]);
    const csv = [head.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `planogram_${location.replace(/[^\w]+/g, "_")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const s = data?.summary || {};
  const plannedUnits =
    items.reduce((acc, i) => {
      const raw = edits[i.item_code];
      const n = raw === undefined ? i.min_qty : raw === "" ? 0 : Number(raw);
      return acc + (Number.isFinite(n) ? n : 0);
    }, 0);

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)]">
      <main className="max-w-[1400px] mx-auto px-4 py-6">
        <nav className="text-sm text-gray-500 mb-3">
          <Link href="/" className="hover:underline">Home</Link>
          {" › "}
          <Link href="/dashboards/locations" className="hover:underline">Locations</Link>
          {" › "}
          <Link
            href={`/dashboards/locations/${encodeURIComponent(location)}`}
            className="hover:underline"
          >
            {location}
          </Link>
          {" › "}
          <span className="text-gray-800 font-medium">Planogram</span>
        </nav>

        <h1 className="text-2xl font-bold text-[var(--nichi-blue)]">
          Planogram — {location}
        </h1>
        <p className="text-sm text-gray-600 mt-1">
          Minimum units to keep on shelf for each SKU.{" "}
          {data?.all_items ? (
            <>
              Showing <strong>all {fmtQty(data?.catalog_size ?? items.length)} catalog SKUs</strong>{" "}
              (every active product), sorted by {data?.ranked_by || "revenue at this location"}.
            </>
          ) : (
            <>
              Showing the <strong>top {data?.top_n ?? 100} SKUs</strong> ranked by{" "}
              {data?.ranked_by || "revenue at this location"}.
            </>
          )}
        </p>

        {/* ---- summary badges ---- */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          <Badge label="SKUs with stock here" value={fmtQty(s.skus_with_onhand)}
                 sub="all SKUs on-hand at this location" />
          <Badge label="Total units on hand" value={fmtQty(s.total_onhand_units)} />
          <Badge label="SKUs with a planogram" value={`${fmtQty(s.skus_with_planogram)} / ${fmtQty(s.skus_shown)}`}
                 sub="across the full catalog" />
          <Badge label="Planned shelf units" value={fmtQty(plannedUnits)}
                 sub="sum of minimums below" />
        </div>

        {/* ---- WhsCode mapping / primary base code ---- */}
        {data?.whs_mapping?.sub_codes?.length > 0 && (
          <WhsMappingPanel mapping={data.whs_mapping} />
        )}

        {data && data.storage_available === false && (
          <div className="mt-4 p-3 rounded border border-amber-300 bg-amber-50 text-amber-900 text-sm">
            MongoDB is not configured on this server, so planogram settings
            cannot be saved. Values below are read-only.
          </div>
        )}

        {/* ---- revenue period toggle — controls which monthly columns show ---- */}
        <div className="flex flex-wrap items-center gap-2 mt-5">
          <span className="text-sm text-gray-600 mr-1">Revenue columns:</span>
          {[
            { key: "3m", label: "Past 3 months" },
            { key: "year", label: "This year" },
            { key: "2y", label: "This & last year" },
          ].map((opt) => (
            <button
              key={opt.key}
              onClick={() => setMonthsRange(opt.key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                monthsRange === opt.key
                  ? "bg-[var(--nichi-blue)] text-white"
                  : "border border-gray-200 hover:bg-gray-100"
              }`}
            >
              {opt.label}
            </button>
          ))}
          {loading && <span className="text-xs text-gray-400">updating…</span>}
          <div className="w-6" />
          <span className="text-sm text-gray-600 mr-1">Show:</span>
          {[
            { key: "revenue", label: "Revenue" },
            { key: "qty", label: "Units" },
          ].map((opt) => (
            <button
              key={opt.key}
              onClick={() => setMonthMetric(opt.key)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                monthMetric === opt.key
                  ? "bg-[var(--nichi-blue)] text-white"
                  : "border border-gray-200 hover:bg-gray-100"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* ---- controls ---- */}
        <div className="flex flex-wrap items-center gap-2 mt-3 mb-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by item code, name or brand…"
            className="px-3 py-1.5 border border-gray-300 rounded text-sm w-72"
          />
          <div className="flex-1" />
          <button onClick={downloadCsv} disabled={!items.length}
            className="px-3 py-1.5 rounded border border-gray-300 text-sm hover:bg-gray-100 disabled:opacity-40">
            Download CSV
          </button>
          <button
            onClick={onSave}
            disabled={saving || dirtyCount === 0 || invalid.length > 0 || data?.storage_available === false}
            className="px-4 py-1.5 rounded bg-[var(--nichi-blue)] text-white text-sm font-semibold disabled:opacity-40"
          >
            {saving ? "Saving…" : dirtyCount ? `Save ${dirtyCount} change${dirtyCount > 1 ? "s" : ""}` : "Save"}
          </button>
        </div>

        {invalid.length > 0 && (
          <div className="mb-2 text-sm text-red-700">
            {invalid.length} value(s) are not whole numbers ≥ 0 — fix them before saving.
          </div>
        )}
        {saveMsg && (
          <div className={`mb-2 text-sm ${saveMsg.kind === "ok" ? "text-green-700" : "text-red-700"}`}>
            {saveMsg.text}
          </div>
        )}

        {/* ---- table ---- */}
        {loading && <div className="p-8 text-center text-gray-500">Loading…</div>}
        {error && (
          <div className="p-4 rounded border border-red-300 bg-red-50 text-red-800 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr className="text-left text-gray-700">
                  <Th>#</Th>
                  <Th>Item Code</Th>
                  <Th>Item Name</Th>
                  <Th>Brand</Th>
                  <Th right>Revenue (THB, Actual)</Th>
                  {months.map((m) => (
                    <Th key={m} right>{monthLabel(m)}</Th>
                  ))}
                  <Th right>Monthly Velocity</Th>
                  <Th right>Sold Qty</Th>
                  <Th right>On-Hand Qty</Th>
                  <Th right title="Demand-based shelf target for the current month, from the AI demand-ceiling engine (corrects for past stockouts + seasonality). Read-only preview.">
                    AI Suggested Planogram
                  </Th>
                  <Th right>Min Units on Shelf</Th>
                </tr>
              </thead>
              <tbody>
                {paged.map((i, idx) => {
                  const raw = edits[i.item_code];
                  const value = raw === undefined ? String(i.min_qty ?? 0) : raw;
                  const changed = dirty[i.item_code] !== undefined;
                  return (
                    <tr key={i.item_code}
                        className={idx % 2 ? "bg-gray-50/50" : ""}>
                      <Td>{i.rank}</Td>
                      <Td>
                        <Link
                          href={`/dashboards/item-detail/${encodeURIComponent(i.item_code)}/${encodeURIComponent(location)}`}
                          className="text-[var(--nichi-blue)] hover:underline font-medium"
                        >
                          {i.item_code}
                        </Link>
                      </Td>
                      <Td className="max-w-[280px] truncate" title={i.item_name}>{i.item_name || "—"}</Td>
                      <Td>{i.brand || "—"}</Td>
                      <Td right>{fmtThb(i.sold_thb)}</Td>
                      {months.map((m, mi) => (
                        <Td key={m} right className="text-gray-600">
                          {monthMetric === "qty"
                            ? fmtQty(i.month_qty?.[mi])
                            : fmtThb(i.month_revenue?.[mi])}
                        </Td>
                      ))}
                      <Td right>{fmtVelocity(i.monthly_velocity)}</Td>
                      <Td right>{fmtQty(i.sold_qty)}</Td>
                      <Td right>{fmtQty(i.onhand_qty)}</Td>
                      <Td right>
                        <AiSuggestion item={i} />
                      </Td>
                      <Td right>
                        <input
                          type="number"
                          min={0}
                          step={1}
                          value={value}
                          onChange={(e) =>
                            setEdits((prev) => ({ ...prev, [i.item_code]: e.target.value }))
                          }
                          disabled={data?.storage_available === false}
                          className={`w-24 px-2 py-1 border rounded text-right ${
                            changed ? "border-[var(--nichi-blue)] bg-blue-50 font-semibold" : "border-gray-300"
                          }`}
                        />
                      </Td>
                    </tr>
                  );
                })}
                {!visible.length && (
                  <tr>
                    <td colSpan={10 + months.length} className="p-8 text-center text-gray-500">
                      {items.length ? "No SKUs match that filter." : "No catalog items for this location."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            {visible.length > PAGE_SIZE && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 text-sm text-gray-600">
                <span>
                  Showing {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, visible.length)} of{" "}
                  {visible.length}{search ? " matching" : ""} SKUs
                </span>
                <div className="flex items-center gap-2">
                  <button onClick={() => setPage(safePage - 1)} disabled={safePage <= 1}
                    className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed text-xs">
                    ← Prev
                  </button>
                  <span>Page {safePage} of {totalPages}</span>
                  <button onClick={() => setPage(safePage + 1)} disabled={safePage >= totalPages}
                    className="px-3 py-1 rounded border border-gray-300 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed text-xs">
                    Next →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function AiSuggestion({ item }) {
  const v = item.ai_suggested_planogram;
  if (v == null) return <span className="text-gray-300">—</span>;
  const conf = item.ai_confidence;
  const color =
    conf === "high" ? "text-green-700" : conf === "medium" ? "text-amber-600" : "text-gray-500";
  const title = [
    `AI suggested (this month): ${v} units`,
    `Peak: ${item.ai_peak_planogram} in ${item.ai_peak_month}`,
    `Base demand/mo (deseasonalized): ${item.ai_base_demand}`,
    `Status: ${item.ai_status}`,
    `Confidence: ${conf} — ${item.ai_months_history} mo history, seasonality from ${item.ai_seasonal_source}`,
  ].join("\n");
  return (
    <div title={title} className="inline-flex flex-col items-end leading-tight">
      <span className={`font-semibold ${color}`}>{v}</span>
      <span className="text-[11px] text-gray-400">
        peak {item.ai_peak_planogram} · {conf}
      </span>
    </div>
  );
}

function WhsMappingPanel({ mapping }) {
  const { primary_whs_code, heterogeneous, sub_codes = [] } = mapping;
  return (
    <div className="mt-4 p-3 rounded-lg border border-gray-200 bg-white">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div>
          <div className="text-xs text-gray-500">Primary Warehouse Code (refill destination)</div>
          {heterogeneous ? (
            <div className="mt-0.5 text-sm font-semibold text-amber-700">
              ⚠ needs review — mixed branches
            </div>
          ) : (
            <div className="mt-0.5 font-mono text-lg font-bold text-[var(--nichi-blue)]">
              {primary_whs_code || "—"}
            </div>
          )}
          <div className="text-[11px] text-gray-400">common base of the sub-codes</div>
        </div>
        <div className="text-xs text-gray-500 flex-1 min-w-[240px]">
          {heterogeneous ? (
            <>This location merges <strong>{sub_codes.length}</strong> unrelated branch codes
            under one name, so there is no single base code. It should be split into separate
            branches (pending). The planogram is still stored against all its codes.</>
          ) : (
            <>This shop maps to <strong>{sub_codes.length}</strong> warehouse sub-code
            {sub_codes.length > 1 ? "s" : ""} (GP-tier splits of the same store). The planogram
            is stored against all of them; refills target the base code above.</>
          )}
          <div className="mt-1 flex flex-wrap gap-1">
            {sub_codes.map((s) => (
              <span key={s.whs_code}
                    className="font-mono text-[11px] px-1.5 py-0.5 rounded border border-gray-200 text-gray-500"
                    title={s.whs_name}>
                {s.whs_code}: {s.onhand_units.toLocaleString()}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Badge({ label, value, sub }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-xl font-bold text-[var(--nichi-blue)]">{value}</div>
      {sub && <div className="text-[11px] text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

const Th = ({ children, right }) => (
  <th className={`px-3 py-2 font-semibold whitespace-nowrap ${right ? "text-right" : ""}`}>{children}</th>
);
const Td = ({ children, right, className = "", title }) => (
  <td title={title} className={`px-3 py-1.5 ${right ? "text-right" : ""} ${className}`}>{children}</td>
);
