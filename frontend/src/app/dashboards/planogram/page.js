"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { downloadCsv } from "@/utils/csvExport";

// "1_A" -> "A1" for a compact grade chip; keep raw if it doesn't parse.
function gradeChip(g) {
  if (!g) return null;
  const m = String(g).match(/^(\d+)_([A-Z])$/);
  return m ? `${m[2]}${m[1]}` : g;
}

export default function AllPlanogramsPage() {
  const [meta, setMeta] = useState(null);        // { locations, brands, total_skus }
  const [brand, setBrand] = useState("");
  const [rows, setRows] = useState([]);          // items for the selected brand
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [channel, setChannel] = useState("ALL"); // location filter
  const [dirty, setDirty] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [page, setPage] = useState(1);
  const [view, setView] = useState("min");       // "min" | "refill"
  const PAGE_SIZE = 200;                         // cap DOM: 200 rows x 64 cols

  // edits: { `${location}|${item}`: rawStringValue }
  const editsRef = useRef({});

  // Initial load: locations + brands (no items until a brand is chosen).
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/all_planograms");
        const j = await res.json();
        if (!res.ok) throw new Error(j.error || `HTTP ${res.status}`);
        setMeta(j);
        if (j.brands?.length) setBrand(j.brands[0].brand);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Load rows when brand changes.
  const loadBrand = useCallback(async (b) => {
    if (!b) return;
    setLoading(true);
    setError(null);
    editsRef.current = {};
    setDirty(0);
    try {
      // "__ALL__" → explicit all_brands flag so the backend returns every SKU
      // (it withholds the full set unless a brand or this flag is given).
      const qs = b === "__ALL__" ? "?all_brands=true" : `?brand=${encodeURIComponent(b)}`;
      const res = await fetch(`/api/all_planograms${qs}`);
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || `HTTP ${res.status}`);
      setRows(j.items || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (brand) loadBrand(brand);
  }, [brand, loadBrand]);

  const locations = meta?.locations || [];
  const visibleLocs = useMemo(
    () => (channel === "ALL" ? locations : locations.filter((l) => l.channel === channel)),
    [locations, channel]
  );
  const channels = useMemo(
    () => ["ALL", ...Array.from(new Set(locations.map((l) => l.channel).filter(Boolean)))],
    [locations]
  );

  const onCellChange = useCallback((loc, item, value) => {
    const key = `${loc}|${item}`;
    editsRef.current[key] = value;
    setDirty(Object.keys(editsRef.current).length);
  }, []);

  async function onSave() {
    // Group edits into { location: { item: qty } }, validating whole ints >= 0.
    const changes = {};
    let bad = 0;
    for (const [key, raw] of Object.entries(editsRef.current)) {
      const sep = key.indexOf("|");
      const loc = key.slice(0, sep);
      const item = key.slice(sep + 1);
      const n = raw === "" ? 0 : Number(raw);
      if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) { bad++; continue; }
      (changes[loc] = changes[loc] || {})[item] = n;
    }
    if (bad > 0) {
      setSaveMsg({ kind: "err", text: `${bad} value(s) are not whole numbers ≥ 0.` });
      return;
    }
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await fetch("/api/all_planograms", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ changes }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || `HTTP ${res.status}`);
      setSaveMsg({ kind: "ok", text: `Saved ${j.cells_saved} cell(s) across ${j.locations_saved} location(s).` });
      await loadBrand(brand);
    } catch (e) {
      setSaveMsg({ kind: "err", text: e.message });
    } finally {
      setSaving(false);
    }
  }

  // Export the planogram itself (min view) as a CSV with two stacked matrices —
  // the shelf minimum per SKU per location, and the current on-hand per location.
  // Both mirror the grid (SKU rows, location columns) and cover ALL loaded rows
  // for the current brand selection (pick "All brands" to export everything).
  function downloadPlanogramCsv() {
    const locs = visibleLocs;
    const header = ["Item Code", "Item Name", "D1 On-Hand", "Company On-Hand",
      ...locs.map((l) => `${l.location}${l.primary_whs_code ? ` (${l.primary_whs_code})` : ""}`)];
    const mins = [];      // shelf minimums (the planogram)
    const onhand = [];    // current on-hand per location
    for (const it of rows) {
      const lead = [it.item_code, it.item_name || "", it.onhand_d1 || 0, it.onhand_total || 0];
      const mRow = [...lead];
      const oRow = [...lead];
      for (const l of locs) {
        const min = it.mins?.[l.location] || 0;
        const oh = it.onhand_by_loc?.[l.location] || 0;
        mRow.push(min || "");    // blanks stay blank so the matrix stays scannable
        oRow.push(oh || "");
      }
      mins.push(mRow);
      onhand.push(oRow);
    }
    const tag = brand === "__ALL__" ? "all_brands" : String(brand).replace(/[^\w]+/g, "_");
    // Single CSV: shelf-minimum matrix, then the on-hand matrix below a labelled separator.
    downloadCsv(`planogram_${tag}.csv`, header, [
      ...mins,
      [],
      ["ON-HAND (units per location)"],
      header,
      ...onhand,
    ]);
  }

  // Export the refill plan as a CSV with two stacked matrices — one of satisfied
  // transfer quantities (from D1), one of the unfulfilled shortfall. Both mirror
  // the grid (SKU rows, location columns), use the same left→right D1 allocation,
  // and cover ALL loaded rows (not just the current page).
  function downloadRefillCsv() {
    const locs = visibleLocs;
    const header = ["Item Code", "Item Name", "D1 On-Hand", "Company On-Hand",
      ...locs.map((l) => `${l.location}${l.primary_whs_code ? ` (${l.primary_whs_code})` : ""}`)];
    const satisfied = [];    // transfer quantities
    const unfulfilled = [];  // shortfall quantities
    for (const it of rows) {
      let d1 = it.onhand_d1 || 0;
      const lead = [it.item_code, it.item_name || "", it.onhand_d1 || 0, it.onhand_total || 0];
      const sRow = [...lead];
      const uRow = [...lead];
      for (const l of locs) {                   // left→right priority
        const min = it.mins?.[l.location] || 0;
        const oh = it.onhand_by_loc?.[l.location] || 0;
        const need = Math.max(0, min - oh);
        if (need === 0) { sRow.push(""); uRow.push(""); continue; }
        const filled = Math.min(need, d1);
        d1 -= filled;
        sRow.push(filled || "");          // only non-zero, so the matrix stays scannable
        uRow.push(need - filled || "");
      }
      satisfied.push(sRow);
      unfulfilled.push(uRow);
    }
    const tag = brand === "__ALL__" ? "all_brands" : String(brand).replace(/[^\w]+/g, "_");
    downloadCsv(`refill_plan_${tag}.csv`, header, [
      ...satisfied,
      [],
      ["UNFULFILLED SHORTFALL (units still short after D1 allocation)"],
      header,
      ...unfulfilled,
    ]);
  }

  // Paginate the SKU rows — "All brands" is ~1k rows x 64 cols and rendering
  // every cell at once freezes the browser. Reset to page 1 on a new load.
  useEffect(() => { setPage(1); }, [rows]);
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pagedRows = useMemo(
    () => rows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [rows, safePage]
  );

  // Memoized grid body: only re-renders when data/columns/page change, NOT on
  // typing (cells are uncontrolled, edits captured in a ref). defaultValue falls
  // back to a pending edit so values survive paging away and back.
  const gridBody = useMemo(() => (
    <tbody>
      {pagedRows.map((it, ri) => {
        // Refill view: walk this SKU's locations LEFT→RIGHT and deplete its D1
        // stock. Each location splits into what D1 can ship now (green "filled")
        // and what's still short (red "missing") — strict priority to the left.
        let refill = null;
        if (view === "refill") {
          let d1 = it.onhand_d1 || 0;
          refill = {};
          for (const l of visibleLocs) {
            const min = it.mins?.[l.location] || 0;
            const oh = it.onhand_by_loc?.[l.location] || 0;
            const need = Math.max(0, min - oh);
            if (need === 0) { refill[l.location] = null; continue; }
            const filled = Math.min(need, d1);
            d1 -= filled;
            refill[l.location] = { need, filled, missing: need - filled };
          }
        }
        return (
          <tr key={it.item_code} className={ri % 2 ? "bg-gray-50/40" : ""}>
            <td className="sticky left-0 z-10 bg-inherit px-2 py-1 border-r whitespace-nowrap">
              <Link href={`/dashboards/item-detail/${encodeURIComponent(it.item_code)}`}
                    className="text-[var(--nichi-blue)] hover:underline font-medium">{it.item_code}</Link>
            </td>
            <td className="sticky left-[110px] z-10 bg-inherit px-2 py-1 border-r max-w-[220px] truncate"
                title={it.item_name}>{it.item_name}</td>
            <td className="px-2 py-1 border-r border-gray-100 text-right tabular-nums font-medium">{(it.onhand_d1 ?? 0).toLocaleString()}</td>
            <td className="px-2 py-1 border-r border-gray-100 text-right tabular-nums text-gray-500">{(it.onhand_total ?? 0).toLocaleString()}</td>
            {visibleLocs.map((l) => {
              if (view === "refill") {
                const r = refill[l.location];
                return (
                  <td key={l.location} className="px-0.5 py-0.5 text-center border-r border-gray-100"
                      title={r ? `Needs ${r.need}: ship ${r.filled} from D1, ${r.missing} short` : "At/above minimum"}>
                    {r ? (
                      <span className="inline-flex flex-col leading-tight items-center">
                        {r.filled > 0 && <span className="text-green-600 text-xs font-semibold">+{r.filled}</span>}
                        {r.missing > 0 && <span className="text-red-600 text-[10px] font-semibold">+{r.missing}</span>}
                      </span>
                    ) : (
                      <span className="text-gray-300 text-xs">·</span>
                    )}
                  </td>
                );
              }
              const edited = editsRef.current[`${l.location}|${it.item_code}`];
              const v = it.mins?.[l.location];
              const oh = it.onhand_by_loc?.[l.location] || 0;
              return (
                <td key={l.location} className="px-0.5 py-0.5 text-center border-r border-gray-100 align-top">
                  <input
                    type="number" min={0} step={1}
                    defaultValue={edited !== undefined ? edited : (v || "")}
                    onChange={(e) => onCellChange(l.location, it.item_code, e.target.value)}
                    className="w-14 px-1 py-0.5 text-right text-xs border border-transparent hover:border-gray-300 focus:border-[var(--nichi-blue)] rounded"
                  />
                  {(v > 0 || oh > 0) && (
                    <div className="text-[10px] leading-none mt-0.5 text-gray-400"
                         title={`On-hand at this location: ${oh}`}>
                      OH {oh}
                    </div>
                  )}
                </td>
              );
            })}
          </tr>
        );
      })}
    </tbody>
  ), [pagedRows, visibleLocs, onCellChange, view]);

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)]">
      <main className="max-w-[100vw] mx-auto px-4 py-6">
        <nav className="text-sm text-gray-500 mb-3">
          <Link href="/" className="hover:underline">Home</Link> {" › "}
          <span className="text-gray-800 font-medium">Planogram (all locations)</span>
        </nav>
        <h1 className="text-2xl font-bold text-[var(--nichi-blue)]">Planogram — All Locations</h1>
        <p className="text-sm text-gray-600 mt-1">
          {view === "refill" ? (
            <>
              Units each location needs to reach its shelf minimum (min − on-hand), filled
              from the <strong>D1 warehouse</strong> left→right.{" "}
              <span className="text-green-600 font-semibold">+N green</span> = D1 can cover it;{" "}
              <span className="text-red-600 font-semibold">+N red</span> = D1 stock ran out (leftmost locations get priority).
            </>
          ) : (
            <>
              Editable shelf minimum per SKU per location (from the PAR Master Con report) with the
              current <strong>on-hand (OH)</strong> at each location shown beneath it. Edit any cell and Save.
            </>
          )}
          {meta && <> {" "}<strong>{meta.total_skus?.toLocaleString()}</strong> SKUs · <strong>{locations.length}</strong> locations.</>}
        </p>

        {/* controls */}
        <div className="flex flex-wrap items-center gap-2 mt-4 mb-2">
          <label className="text-sm text-gray-600">Brand</label>
          <select value={brand} onChange={(e) => setBrand(e.target.value)}
                  className="px-2 py-1 border border-gray-300 rounded text-sm">
            <option value="__ALL__">All brands ({(meta?.total_skus ?? 0).toLocaleString()})</option>
            {(meta?.brands || []).map((b) => (
              <option key={b.brand} value={b.brand}>{b.brand} ({b.sku_count})</option>
            ))}
          </select>
          <label className="text-sm text-gray-600 ml-3">Channel</label>
          <select value={channel} onChange={(e) => setChannel(e.target.value)}
                  className="px-2 py-1 border border-gray-300 rounded text-sm">
            {channels.map((c) => <option key={c} value={c}>{c === "ALL" ? "All channels" : c}</option>)}
          </select>
          <span className="text-xs text-gray-400">{visibleLocs.length} location columns</span>
          <div className="ml-3 inline-flex rounded-lg border border-gray-200 overflow-hidden">
            {[
              { key: "min", label: "Min quantity" },
              { key: "refill", label: "Refill needed" },
            ].map((opt) => (
              <button
                key={opt.key}
                onClick={() => setView(opt.key)}
                className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                  view === opt.key
                    ? "bg-[var(--nichi-blue)] text-white"
                    : "bg-white hover:bg-gray-100 text-gray-700"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <div className="flex-1" />
          {saveMsg && (
            <span className={`text-sm ${saveMsg.kind === "ok" ? "text-green-700" : "text-red-700"}`}>{saveMsg.text}</span>
          )}
          {view === "min" && (
            <>
              <button onClick={downloadPlanogramCsv} disabled={!rows.length}
                      className="px-4 py-1.5 rounded border border-[var(--nichi-blue)] text-[var(--nichi-blue)] text-sm font-semibold disabled:opacity-40 hover:bg-teal-50"
                      title="Download the planogram as CSV — shelf minimums, then on-hand per location">
                ⬇ Download planogram CSV
              </button>
              <button onClick={onSave} disabled={saving || dirty === 0}
                      className="px-4 py-1.5 rounded bg-[var(--nichi-blue)] text-white text-sm font-semibold disabled:opacity-40">
                {saving ? "Saving…" : dirty ? `Save ${dirty} change${dirty > 1 ? "s" : ""}` : "Save"}
              </button>
            </>
          )}
          {view === "refill" && (
            <button onClick={downloadRefillCsv} disabled={!rows.length}
                    className="px-4 py-1.5 rounded bg-[var(--nichi-blue)] text-white text-sm font-semibold disabled:opacity-40"
                    title="Download the refill plan as CSV — satisfied transfers, then shortfall">
              ⬇ Download refill CSV
            </button>
          )}
        </div>

        {loading && <div className="p-8 text-center text-gray-500">Loading…</div>}
        {error && <div className="p-4 rounded border border-red-300 bg-red-50 text-red-800 text-sm">{error}</div>}

        {!loading && !error && (
          <div className="border border-gray-200 rounded-lg overflow-auto bg-white" style={{ maxHeight: "72vh" }}>
            <table className="text-xs border-collapse">
              <thead className="sticky top-0 z-20">
                <tr className="bg-gray-100">
                  <th className="sticky left-0 z-30 bg-gray-100 px-2 py-2 border-r text-left">Item Code</th>
                  <th className="sticky left-[110px] z-30 bg-gray-100 px-2 py-2 border-r text-left">Item Name</th>
                  <th className="px-2 py-2 border-r border-gray-200 text-right whitespace-nowrap" title="Units on hand at the D1 main warehouse (refill source)">D1<br/>On-Hand</th>
                  <th className="px-2 py-2 border-r border-gray-200 text-right whitespace-nowrap" title="Total units on hand across the whole company">Company<br/>On-Hand</th>
                  {visibleLocs.map((l) => (
                    <th key={l.location} className="px-1 py-2 border-r border-gray-200 font-semibold align-bottom"
                        title={`${l.location} · primary ${l.primary_whs_code || "—"}`}
                        style={{ minWidth: "60px" }}>
                      <div className="flex flex-col items-center gap-0.5">
                        {l.grade && <span className="text-[10px] px-1 rounded bg-[var(--nichi-blue)] text-white">{gradeChip(l.grade)}</span>}
                        <span className="font-mono text-[10px] text-gray-600">{l.primary_whs_code || "—"}</span>
                        <span className="max-w-[70px] truncate text-[10px] text-gray-500" title={l.location}>{l.location}</span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              {gridBody}
            </table>
            {!rows.length && brand && (
              <div className="p-8 text-center text-gray-500">
                {brand === "__ALL__" ? "No planogram SKUs." : `No planogram SKUs for “${brand}”.`}
              </div>
            )}
            {rows.length > PAGE_SIZE && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 text-sm text-gray-600 bg-white sticky left-0">
                <span>
                  Showing {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, rows.length)} of {rows.length.toLocaleString()} SKUs
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
