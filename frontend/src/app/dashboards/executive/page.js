"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import api, { isAbortError } from "@/utils/api";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import KpiCard from "@/components/KpiCard";
import ErrorBanner from "@/components/ErrorBanner";
import { fmtThb, fmtQty, fmtPct } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csvExport";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  Cell,
  Legend,
} from "recharts";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "trends", label: "Trends" },
  { id: "concentration", label: "Concentration" },
  { id: "channels", label: "Channels" },
  { id: "more", label: "More" },
];

const CHANNEL_COLORS = [
  "#7c3aed", "#0d9488", "#d97706", "#2563eb", "#dc2626",
  "#059669", "#7c2d12", "#6366f1", "#0891b2", "#be185d",
];


function useSortable(rows, defaultCol = null) {
  const [sortCol, setSortCol] = useState(defaultCol);
  const [sortDir, setSortDir] = useState("asc");
  const toggle = (col) => {
    if (sortCol === col) {
      if (sortDir === "asc") setSortDir("desc");
      else { setSortCol(null); setSortDir("asc"); }
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  };
  const sorted = useMemo(() => {
    if (!sortCol || !Array.isArray(rows)) return rows || [];
    return [...rows].sort((a, b) => {
      let va = a[sortCol], vb = b[sortCol];
      if (va == null) va = "";
      if (vb == null) vb = "";
      if (typeof va === "number" && typeof vb === "number")
        return sortDir === "asc" ? va - vb : vb - va;
      const sa = String(va).toLowerCase(), sb = String(vb).toLowerCase();
      return sortDir === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
  }, [rows, sortCol, sortDir]);
  const indicator = (col) => sortCol !== col ? " ↕" : sortDir === "asc" ? " ↑" : " ↓";
  return { sorted, toggle, indicator };
}


export default function ExecutiveDashboardPage() {
  const [tab, setTab] = useState("overview");
  const [summary, setSummary] = useState(null);
  const [trend, setTrend] = useState(null);
  const cy = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = useState(cy);
  const [margin, setMargin] = useState(null);
  const [inventoryRisk, setInventoryRisk] = useState(null);
  const [riskWindowDays, setRiskWindowDays] = useState(90);
  const [channelPerf, setChannelPerf] = useState(null);
  const [concBrand, setConcBrand] = useState(null);
  const [concChannel, setConcChannel] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  const trendSort = useSortable(trend?.series || []);
  const channelSort = useSortable(channelPerf?.rows || []);
  const marginSort = useSortable(margin?.rows || []);
  const riskSort = useSortable(inventoryRisk?.rows || []);

  const loadSummary = useCallback(async (signal) => {
    const res = await api.get("/api/executive_summary", { signal, responseType: "json" });
    if (res.data?.message === "data not ready") {
      setSummary(null);
      return;
    }
    setSummary(res.data);
  }, []);

  const loadTrend = useCallback(async (years, signal) => {
    const qs = new URLSearchParams();
    qs.set("granularity", "monthly");
    (years || []).forEach((y) => qs.append("year_list", String(y)));
    const res = await api.get(`/api/sales_trend_executive?${qs.toString()}`, {
      signal,
      responseType: "json",
    });
    if (res.data?.message === "data not ready") {
      setTrend(null);
      return;
    }
    setTrend(res.data);
  }, []);

  const fetchConcentration = useCallback(async (year, signal) => {
    const y = year;
    const [b, c] = await Promise.all([
      api.get(`/api/concentration_summary?dimension=brand&year=${y}&top_n=10`, { signal }),
      api.get(`/api/concentration_summary?dimension=channel&year=${y}&top_n=10`, { signal }),
    ]);
    if (b.data?.message !== "data not ready") setConcBrand(b.data);
    else setConcBrand(null);
    if (c.data?.message !== "data not ready") setConcChannel(c.data);
    else setConcChannel(null);
  }, []);

  const loadMargin = useCallback(async (years, signal) => {
    const qs = new URLSearchParams();
    (years || []).forEach((y) => qs.append("year_list", String(y)));
    const res = await api.get(`/api/margin_by_brand?${qs.toString()}`, {
      signal,
      responseType: "json",
    });
    if (res.data?.message === "data not ready") {
      setMargin(null);
      return;
    }
    setMargin(res.data);
  }, []);

  const loadInventoryRisk = useCallback(async (windowDays = 90, topN = 20, signal) => {
    const res = await api.get(
      `/api/inventory_risk_summary?window_days=${encodeURIComponent(String(windowDays))}&top_n=${encodeURIComponent(String(topN))}`,
      { signal, responseType: "json" }
    );
    if (res.data?.message === "data not ready") {
      setInventoryRisk(null);
      return;
    }
    setInventoryRisk(res.data);
  }, []);

  const loadChannelPerformance = useCallback(async (years, periodType = "monthly", signal) => {
    const qs = new URLSearchParams();
    (years || []).forEach((y) => qs.append("year_list", String(y)));
    qs.set("period_type", periodType);
    const res = await api.get(`/api/channel_performance_executive?${qs.toString()}`, {
      signal,
      responseType: "json",
    });
    if (res.data?.message === "data not ready") {
      setChannelPerf(null);
      return;
    }
    setChannelPerf(res.data);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    (async () => {
      setLoading(true);
      setErr(null);
      const years = [selectedYear, selectedYear - 1];
      try {
        // Fire all API calls in parallel to avoid sequential timeout
        const results = await Promise.allSettled([
          loadSummary(signal),
          loadTrend(years, signal),
          fetchConcentration(selectedYear, signal),
          loadMargin(years, signal),
          loadInventoryRisk(riskWindowDays, 20, signal),
          loadChannelPerformance(years, "monthly", signal),
        ]);
        // Report the first non-abort error if any call failed
        const firstError = results.find(
          (r) => r.status === "rejected" && !isAbortError(r.reason)
        );
        if (firstError) setErr(firstError.reason?.message || "Failed to load");
      } catch (e) {
        if (!isAbortError(e)) setErr(e?.message || "Failed to load");
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    })();
    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedYear, riskWindowDays, loadSummary, loadTrend, fetchConcentration, loadMargin, loadInventoryRisk, loadChannelPerformance]);

  const asOf =
    summary?.as_of ||
    summary?.filename ||
    trend?.as_of ||
    (summary?.totals ? "" : null);

  const trendChartData = useMemo(() => {
    const s = trend?.series;
    if (!Array.isArray(s)) return [];
    return s.map((row) => ({
      ...row,
      // Swap partial-month values for running-rate projections so the
      // chart is a fair comparison to prior full months.
      revenue_thb: row.is_partial ? (row.running_rate_revenue_thb ?? row.revenue_thb) : row.revenue_thb,
      revenue_master_thb: row.is_partial ? (row.running_rate_revenue_master_thb ?? row.revenue_master_thb) : row.revenue_master_thb,
      qty: row.is_partial ? (row.running_rate_qty ?? row.qty) : row.qty,
      label: row.period?.slice(0, 7) ?? row.period,
    }));
  }, [trend]);

  const trendPartialNote = useMemo(() => {
    const s = trend?.series;
    if (!Array.isArray(s) || s.length === 0) return null;
    const last = s[s.length - 1];
    if (!last?.is_partial) return null;
    return `Latest month (${last.period?.slice(0, 7)}) projected from ${last.days_elapsed}/${last.days_in_month} days`;
  }, [trend]);

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)] text-slate-800 pb-16">
      <header className="border-b border-slate-200 bg-white backdrop-blur no-print">
        <div className="mx-auto max-w-6xl px-4 py-4 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Executive dashboard</h1>
            {asOf && (
              <p className="text-sm text-slate-500 mt-1">
                As of snapshot: {asOf}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-sm text-slate-500">Year:</span>
            {[cy, cy - 1, cy - 2, cy - 3].map((y) => (
              <button
                key={`yr-${y}`}
                type="button"
                onClick={() => setSelectedYear(y)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  selectedYear === y
                    ? "bg-[var(--nichi-blue)] text-white"
                    : "border border-slate-200 hover:bg-slate-100"
                }`}
              >
                {y}
              </button>
            ))}
            <div className="w-px h-6 bg-slate-200 mx-1" />
            <button
              type="button"
              onClick={() => window.print()}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-100"
            >
              Print / PDF
            </button>
          </div>
        </div>
        <nav className="mx-auto max-w-6xl px-4 flex gap-1 border-t border-slate-100 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-3 py-2 text-sm border-b-2 -mb-px whitespace-nowrap ${
                tab === t.id
                  ? "border-[var(--nichi-blue)] text-[var(--nichi-blue)] font-medium"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 space-y-8">
        {loading && <p className="text-slate-500">Loading…</p>}
        {err && <ErrorBanner message={err} onRetry={() => loadSummary()} />}

        {tab === "overview" && (
          <section className="space-y-6">
            <h2 className="text-lg font-medium print:text-base">Organisation totals</h2>
            {!summary?.totals && !loading && (
              <p className="text-sm text-slate-500">Data not ready. Check the status bar above.</p>
            )}
            {summary?.totals && (
              <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <KpiCard title="Lifetime Revenue (THB, Invoiced)" value={fmtThb(summary.totals.sold_thb)} tooltip="SAP LineTotal — gross invoiced amount. For consignment this equals Master (GP still inside). For what Nichi actually keeps, see Revenue (Actual)." />
                <KpiCard title="Lifetime Revenue (THB, Master)" value={fmtThb(summary.totals.sold_master_thb)} tooltip="Top-line revenue at master (list) price. = Revenue (Actual) + Retailer Cut." />
                <KpiCard title="Lifetime Sold (qty)" value={fmtQty(summary.totals.sold_qty)} tooltip={METRIC_TOOLTIPS.executive.lifetime_sold_qty} />
                <KpiCard
                  title="On-Hand (THB @ Master Price)"
                  value={fmtThb(summary.totals.onhand_thb_master)}
                  tooltip={METRIC_TOOLTIPS.executive.onhand_thb}
                />
                <KpiCard title="On-Hand (qty)" value={fmtQty(summary.totals.onhand_qty)} tooltip={METRIC_TOOLTIPS.executive.onhand_qty} />
              </div>
              {/* Cost of Channel row — unified GP + credit-channel discount */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mt-4">
                <KpiCard
                  title="GP Commission (THB)"
                  value={fmtThb(summary.totals.gp_commission_thb)}
                  tooltip="Commission paid to retailers on consignment sales only."
                />
                <KpiCard
                  title="Discount (Credit Channels)"
                  value={fmtThb(summary.totals.discount_thb)}
                  tooltip="Implicit discount on credit/outright sales: Revenue (Master) − Revenue (Actual). Economic equivalent of GP commission — the retailer's cut on credit sales."
                />
                <KpiCard
                  title="Retailer Cut (Unified)"
                  value={fmtThb(summary.totals.retailer_cut_thb)}
                  tooltip="GP Commission + Discount. Apples-to-apples cost-of-channel across consignment and credit sales."
                />
                <KpiCard
                  title="Retailer Cut %"
                  value={summary.totals.retailer_cut_pct != null ? `${summary.totals.retailer_cut_pct}%` : "—"}
                  tooltip="Retailer Cut ÷ Revenue (Master)."
                />
                <KpiCard
                  title="Revenue (Actual, to Nichi)"
                  value={fmtThb(
                    summary.totals.net_revenue_thb != null
                      ? summary.totals.net_revenue_thb
                      : (summary.totals.sold_master_thb ?? 0) - (summary.totals.retailer_cut_thb ?? 0)
                  )}
                  tooltip="What ToyVault actually keeps after the retailer's cut. Revenue (Master) − Retailer Cut. Identity: Master = Actual + Retailer Cut."
                />
              </div>
              </>
            )}
            {summary?.comparison && (
              <div className="rounded-xl border border-slate-200 p-4 bg-white text-sm">
                <p className="font-medium">Latest full month vs prior</p>
                <p className="mt-2 text-slate-600">
                  {summary.comparison.last_period}: {fmtThb(summary.comparison.last_revenue_thb)} revenue
                  {summary.comparison.revenue_mom_pct != null && (
                    <>
                      {" "}
                      (
                      {summary.comparison.revenue_mom_pct >= 0 ? "+" : ""}
                      {summary.comparison.revenue_mom_pct.toFixed(1)}% vs {summary.comparison.prior_period})
                    </>
                  )}
                </p>
              </div>
            )}
            <p className="text-xs text-slate-500 max-w-3xl">
              Sold figures use the same line deduplication as the channel monthly matrix (DocEntry × Item ×
              period × channel). On-hand matches the organisation total on that report.
            </p>
          </section>
        )}

        {tab === "trends" && (
          <section className="space-y-4">
            <h2 className="text-lg font-medium">Revenue by month ({selectedYear} vs {selectedYear - 1})</h2>
            <p className="text-sm text-slate-500">
              Series matches executive totals aggregation; TTM = trailing twelve months of revenue.
            </p>
            {trendPartialNote && (
              <p className="text-xs text-amber-700">
                ⓘ {trendPartialNote} — shown as full-month running-rate projection
              </p>
            )}
            <div className="h-80 w-full rounded-xl border border-slate-200 p-4 bg-white">
              <h4 className="text-sm font-medium text-slate-700 mb-2">Monthly Revenue Trend</h4>
              {trendChartData.length === 0 && !loading ? (
                <p className="text-sm text-slate-500">No trend data.</p>
              ) : (
                <ResponsiveContainer width="100%" height="90%">
                  <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                    <YAxis
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : String(v))}
                      label={{ value: "Revenue (THB)", angle: -90, position: "insideLeft", style: { fontSize: 11, fill: "#64748b" } }}
                    />
                    <Tooltip
                      formatter={(value, name) => [fmtThb(value), name]}
                      labelFormatter={(l) => `Period ${l}`}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="revenue_thb" name="Revenue (Actual)" stroke="#1a3a8f" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="revenue_master_thb" name="Revenue (Master)" stroke="#2d4ea3" strokeWidth={2} strokeDasharray="5 3" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="h-64 rounded-xl border border-slate-200 p-4 bg-white">
                <h4 className="text-sm font-medium text-slate-700 mb-2">Trailing 12-Month Revenue<InfoTooltip text={METRIC_TOOLTIPS.executive.ttm_revenue} /></h4>
                {trendChartData.length === 0 && !loading ? (
                  <p className="text-sm text-slate-500">No data.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="85%">
                    <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : String(v))} />
                      <Tooltip formatter={(value) => [fmtThb(value), "TTM"]} />
                      <Line type="monotone" dataKey="ttm_revenue_thb" stroke="#059669" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
              <div className="h-64 rounded-xl border border-slate-200 p-4 bg-white">
                <h4 className="text-sm font-medium text-slate-700 mb-2">YoY Revenue Change %<InfoTooltip text={METRIC_TOOLTIPS.executive.yoy_pct} /></h4>
                {trendChartData.length === 0 && !loading ? (
                  <p className="text-sm text-slate-500">No data.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="85%">
                    <BarChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                      <Tooltip formatter={(value) => [value == null ? "—" : `${value.toFixed(1)}%`, "YoY %"]} />
                      <Bar dataKey="yoy_revenue_pct" radius={[3, 3, 0, 0]}>
                        {trendChartData.map((entry, i) => (
                          <Cell key={i} fill={entry.yoy_revenue_pct >= 0 ? "#059669" : "#dc2626"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
            <div className="flex justify-end no-print">
              <button
                type="button"
                onClick={() => {
                  downloadCsv(
                    "trend_data.csv",
                    ["Period", "Revenue (THB, Actual)", "Revenue (THB, Master)", "Qty", "YoY Revenue %", "TTM Revenue THB"],
                    trendChartData.map((r) => [r.period, r.revenue_thb, r.revenue_master_thb, r.qty, r.yoy_revenue_pct, r.ttm_revenue_thb])
                  );
                }}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-100"
              >
                Download CSV
              </button>
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-slate-50">
                    {[["period", "Period", "left", null], ["revenue_thb", "Revenue (THB)", "right", null], ["qty", "Qty", "right", null], ["yoy_revenue_pct", "YoY %", "right", METRIC_TOOLTIPS.executive.yoy_pct], ["ttm_revenue_thb", "TTM Revenue", "right", METRIC_TOOLTIPS.executive.ttm_revenue]].map(([k, label, align, tip]) => (
                      <th key={k} className={`text-${align} px-3 py-2 cursor-pointer select-none hover:bg-slate-100`} onClick={() => trendSort.toggle(k)}>
                        {label}{tip && <InfoTooltip text={tip} />}{trendSort.indicator(k)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trendSort.sorted.slice().reverse().slice(0, 24).map((r) => (
                    <tr key={r.period} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">{r.label}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmtThb(r.revenue_thb)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmtQty(r.qty)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmtPct(r.yoy_revenue_pct)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmtThb(r.ttm_revenue_thb)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {tab === "concentration" && (
          <section className="space-y-6">
            <div className="flex flex-wrap items-center gap-4">
              <h2 className="text-lg font-medium">Revenue concentration ({selectedYear})</h2>
              <button
                type="button"
                onClick={() => {
                  const allRows = [...(concBrand?.rows || []).map((r) => ({ ...r, dimension: "Brand" })), ...(concChannel?.rows || []).map((r) => ({ ...r, dimension: "Channel" }))];
                  downloadCsv(
                    `concentration_${selectedYear}.csv`,
                    ["Dimension", "Name", "Revenue THB", "Share %", "Cumulative %"],
                    allRows.map((r) => [r.dimension, r.name, r.revenue_thb, r.share_pct, r.cumulative_pct])
                  );
                }}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-100 no-print"
              >
                Download CSV
              </button>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="rounded-xl border border-slate-200 p-4 bg-white">
                <h4 className="text-sm font-medium text-slate-700 mb-2">
                  Top Brands by Revenue ({concBrand?.top_k_share_pct ?? "—"}% of {fmtThb(concBrand?.total_revenue_thb)})
                </h4>
                <div className="h-72">
                  {concBrand?.rows?.length ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={[...concBrand.rows].reverse()}
                        layout="vertical"
                        margin={{ left: 8, right: 16 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                        <XAxis type="number" tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} />
                        <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} />
                        <Tooltip formatter={(v) => [fmtThb(v), "Revenue"]} />
                        <Bar dataKey="revenue_thb" fill="#7c3aed" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-sm text-slate-500">No data for this year.</p>
                  )}
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 p-4 bg-white">
                <h4 className="text-sm font-medium text-slate-700 mb-2">
                  Top Channels by Revenue ({concChannel?.top_k_share_pct ?? "—"}% of {fmtThb(concChannel?.total_revenue_thb)})
                </h4>
                <div className="h-72">
                  {concChannel?.rows?.length ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={[...concChannel.rows].reverse()}
                        layout="vertical"
                        margin={{ left: 8, right: 16 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                        <XAxis type="number" tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} />
                        <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} />
                        <Tooltip formatter={(v) => [fmtThb(v), "Revenue"]} />
                        <Bar dataKey="revenue_thb" fill="#0d9488" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-sm text-slate-500">No data for this year.</p>
                  )}
                </div>
              </div>
            </div>
          </section>
        )}

        {tab === "channels" && (
          <section className="space-y-4">
            <h2 className="text-lg font-medium">Channel performance ({selectedYear} vs {selectedYear - 1})</h2>
            {channelPerf?.latest_period && (
              <p className="text-sm text-slate-600">
                Latest period: {channelPerf.latest_period}
                {channelPerf.prior_period ? ` (vs ${channelPerf.prior_period})` : ""}
              </p>
            )}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="h-72 rounded-xl border border-slate-200 p-4 bg-white">
                <h4 className="text-sm font-medium text-slate-700 mb-2">Revenue Mix by Channel</h4>
                {(channelPerf?.rows || []).length === 0 && !loading ? (
                  <p className="text-sm text-slate-500">No data.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="90%">
                    <BarChart
                      data={[...(channelPerf?.rows || [])].sort((a, b) => (b.latest_revenue_thb || 0) - (a.latest_revenue_thb || 0))}
                      layout="vertical"
                      margin={{ left: 8, right: 16 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                      <XAxis type="number" tickFormatter={(v) => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : String(v)} />
                      <YAxis type="category" dataKey="channel" width={110} tick={{ fontSize: 10 }} />
                      <Tooltip formatter={(v) => [fmtThb(v), "Revenue"]} />
                      <Bar dataKey="latest_revenue_thb" radius={[0, 4, 4, 0]}>
                        {(channelPerf?.rows || []).map((_, i) => (
                          <Cell key={i} fill={CHANNEL_COLORS[i % CHANNEL_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
              <div className="h-72 rounded-xl border border-slate-200 p-4 bg-white">
                <h4 className="text-sm font-medium text-slate-700 mb-2">MoM Growth % by Channel</h4>
                {(channelPerf?.rows || []).length === 0 && !loading ? (
                  <p className="text-sm text-slate-500">No data.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="90%">
                    <BarChart
                      data={[...(channelPerf?.rows || [])].filter((r) => r.mom_revenue_pct != null)}
                      layout="vertical"
                      margin={{ left: 8, right: 16 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                      <XAxis type="number" tickFormatter={(v) => `${v}%`} />
                      <YAxis type="category" dataKey="channel" width={110} tick={{ fontSize: 10 }} />
                      <Tooltip formatter={(v) => [`${v?.toFixed(1)}%`, "MoM %"]} />
                      <Bar dataKey="mom_revenue_pct" radius={[0, 4, 4, 0]}>
                        {(channelPerf?.rows || []).filter((r) => r.mom_revenue_pct != null).map((r, i) => (
                          <Cell key={i} fill={r.mom_revenue_pct >= 0 ? "#059669" : "#dc2626"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
            <div className="flex justify-end no-print">
              <button
                type="button"
                onClick={() => {
                  downloadCsv(
                    "channel_performance.csv",
                    ["Channel", "Latest Revenue", "Prior Revenue", "MoM %", "Mix %"],
                    (channelPerf?.rows || []).map((r) => [r.channel, r.latest_revenue_thb, r.prior_revenue_thb, r.mom_revenue_pct, r.mix_pct])
                  );
                }}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm hover:bg-slate-100"
              >
                Download CSV
              </button>
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="bg-slate-50">
                    {[["channel", "Channel", "left"], ["latest_revenue_thb", "Latest Revenue", "right"], ["prior_revenue_thb", "Prior Revenue", "right"], ["mom_revenue_pct", "MoM %", "right"], ["mix_pct", "Mix %", "right"]].map(([k, label, align]) => (
                      <th key={k} className={`text-${align} px-3 py-2 cursor-pointer select-none hover:bg-slate-100`} onClick={() => channelSort.toggle(k)}>
                        {label}{channelSort.indicator(k)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {channelSort.sorted.map((r) => (
                    <tr key={r.channel} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">{r.channel}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmtThb(r.latest_revenue_thb)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{fmtThb(r.prior_revenue_thb)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">
                        {r.mom_revenue_pct == null ? "—" : `${r.mom_revenue_pct.toFixed(1)}%`}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{r.mix_pct != null ? r.mix_pct.toFixed(1) : "—"}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-500">
              This executive view uses canonical channel aggregation. For full drilldown tables and exports, use Operations.
            </p>
            <Link href="/task2" className="inline-block text-sm text-violet-600">
              Open Operations tables
            </Link>
          </section>
        )}

        {tab === "more" && (
          <section className="space-y-6 text-sm text-slate-600">
            <div className="rounded-xl border border-slate-200 p-4 bg-white">
              <h3 className="font-medium text-slate-800">Margin and profitability ({selectedYear} vs {selectedYear - 1})</h3>
              {margin?.totals && (
                <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                  <KpiCard title="Revenue (THB)" value={fmtThb(margin.totals.revenue_thb)} tooltip={METRIC_TOOLTIPS.executive.revenue_thb} />
                  <KpiCard title="COGS (THB)" value={fmtThb(margin.totals.cogs_thb)} tooltip={METRIC_TOOLTIPS.executive.cogs_thb} />
                  <KpiCard
                    title="Gross Margin"
                    value={`${fmtThb(margin.totals.gross_margin_thb)} ${
                      margin.totals.gross_margin_pct == null ? "" : `(${margin.totals.gross_margin_pct.toFixed(1)}%)`
                    }`}
                    tooltip={METRIC_TOOLTIPS.executive.gross_margin_pct}
                  />
                </div>
              )}
              <div className="mt-4 h-72 rounded-lg border border-slate-200 p-4">
                <h4 className="text-sm font-medium text-slate-700 mb-2">Revenue vs COGS by Brand (Top 10)</h4>
                {(margin?.rows || []).length === 0 ? (
                  <p className="text-xs text-slate-500">No data.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="90%">
                    <BarChart
                      data={(margin?.rows || []).slice(0, 10)}
                      margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                      <XAxis dataKey="brand" tick={{ fontSize: 9 }} interval={0} angle={-30} textAnchor="end" height={50} />
                      <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : String(v)} />
                      <Tooltip formatter={(v) => [fmtThb(v)]} />
                      <Bar dataKey="revenue_thb" fill="#7c3aed" name="Revenue" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="cogs_thb" fill="#dc2626" name="COGS" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
              <div className="mt-3 flex justify-end no-print">
                <button
                  type="button"
                  onClick={() => {
                    downloadCsv(
                      "margin_by_brand.csv",
                      ["Brand", "Revenue THB", "COGS THB", "Gross Margin THB", "Margin %"],
                      (margin?.rows || []).map((r) => [r.brand, r.revenue_thb, r.cogs_thb, r.gross_margin_thb, r.gross_margin_pct])
                    );
                  }}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs hover:bg-slate-100"
                >
                  Download CSV
                </button>
              </div>
              <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50">
                      {[["brand", "Brand", "left", null], ["revenue_thb", "Revenue", "right", null], ["cogs_thb", "COGS", "right", METRIC_TOOLTIPS.executive.cogs_thb], ["gross_margin_thb", "Gross Margin", "right", null], ["gross_margin_pct", "Margin %", "right", METRIC_TOOLTIPS.executive.gross_margin_pct]].map(([k, label, align, tip]) => (
                        <th key={k} className={`text-${align} px-2 py-2 cursor-pointer select-none hover:bg-slate-100`} onClick={() => marginSort.toggle(k)}>
                          {label}{tip && <InfoTooltip text={tip} />}{marginSort.indicator(k)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {marginSort.sorted.slice(0, 15).map((r) => (
                      <tr key={r.brand} className="border-t border-slate-100">
                        <td className="px-2 py-1.5">{r.brand}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{fmtThb(r.revenue_thb)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{fmtThb(r.cogs_thb)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{fmtThb(r.gross_margin_thb)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">
                          {r.gross_margin_pct == null ? "—" : `${r.gross_margin_pct.toFixed(1)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="rounded-xl border border-slate-200 p-4 bg-white">
              <h3 className="font-medium text-slate-800">Inventory risk (EX-04)</h3>
              <div className="mt-3 no-print flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-500">Window days:</span>
                {[30, 60, 90, 120].map((d) => (
                  <button
                    key={`w-${d}`}
                    type="button"
                    onClick={() => setRiskWindowDays(d)}
                    className={`px-2 py-1 rounded border text-xs ${
                      riskWindowDays === d
                        ? "bg-teal-600 text-white border-teal-600"
                        : "border-slate-200 hover:bg-slate-100"
                    }`}
                  >
                    {d}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => loadInventoryRisk(riskWindowDays, 20)}
                  className="rounded-lg bg-teal-600 text-white px-3 py-1.5 text-sm hover:bg-teal-700"
                >
                  Reload risk
                </button>
              </div>
              {inventoryRisk?.summary && (
                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                  <KpiCard title="Total On-Hand (THB @ Master Price)" value={fmtThb(inventoryRisk.summary.total_onhand_thb)} tooltip={METRIC_TOOLTIPS.executive.onhand_thb} />
                  <KpiCard title={`Sold qty (${inventoryRisk.window_days}d)`} value={fmtQty(inventoryRisk.summary.total_sold_qty_90d)} />
                </div>
              )}
              <div className="mt-4 h-64 rounded-lg border border-slate-200 p-4">
                <p className="text-xs font-medium mb-2 text-slate-800">Top items by on-hand value (THB)</p>
                {(inventoryRisk?.rows || []).length === 0 ? (
                  <p className="text-xs text-slate-500">No data.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="90%">
                    <BarChart
                      data={(inventoryRisk?.rows || []).slice(0, 10).reverse()}
                      layout="vertical"
                      margin={{ left: 8, right: 16 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                      <XAxis type="number" tickFormatter={(v) => v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v)} />
                      <YAxis type="category" dataKey="item_code" width={100} tick={{ fontSize: 9 }} />
                      <Tooltip formatter={(v) => [fmtThb(v), "On-Hand (THB @ Master Price)"]} />
                      <Bar dataKey="onhand_thb" fill="#d97706" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
              <div className="mt-3 flex justify-end no-print">
                <button
                  type="button"
                  onClick={() => {
                    downloadCsv(
                      "inventory_risk.csv",
                      ["Item Code", "Brand", "On-Hand (THB @ Master Price)", "Sold Qty", "Days Cover"],
                      (inventoryRisk?.rows || []).map((r) => [r.item_code, r.brand, r.onhand_thb, r.sold_qty_90d, r.days_cover_label])
                    );
                  }}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs hover:bg-slate-100"
                >
                  Download CSV
                </button>
              </div>
              <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50">
                      {[["item_code", "Item", "left", null], ["brand", "Brand", "left", null], ["onhand_thb", "On-Hand (THB @ Master Price)", "right", null], ["sold_qty_90d", "Sold Qty", "right", null], ["days_cover", "Days Cover", "right", METRIC_TOOLTIPS.inventory.days_of_cover]].map(([k, label, align, tip]) => (
                        <th key={k} className={`text-${align} px-2 py-2 cursor-pointer select-none hover:bg-slate-100`} onClick={() => riskSort.toggle(k)}>
                          {label}{tip && <InfoTooltip text={tip} />}{riskSort.indicator(k)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {riskSort.sorted.slice(0, 20).map((r) => (
                      <tr key={r.item_code} className="border-t border-slate-100">
                        <td className="px-2 py-1.5"><Link href={`/dashboards/item-detail/${encodeURIComponent(r.item_code)}`} className="text-[var(--nichi-blue)] hover:underline font-medium">{r.item_code}</Link></td>
                        <td className="px-2 py-1.5">{r.brand}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{fmtThb(r.onhand_thb)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{fmtQty(r.sold_qty_90d)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{r.days_cover_label}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Snapshot on-hand is as of file date; sales are historical. Days-cover is indicative.
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 p-4 bg-white">
              <h3 className="font-medium text-slate-800">Budget vs actual (EX-09)</h3>
              <p className="mt-2">Budget source not connected.</p>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
