"use client";

import { useParams } from "next/navigation";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Link from "next/link";
import ErrorBanner from "@/components/ErrorBanner";
import InfoTooltip from "@/components/InfoTooltip";
import ChartDownloadToolbar from "@/components/ChartDownloadToolbar";
import api, { isAbortError } from "@/utils/api";
import { fmtQty, fmtThb } from "@/utils/formatters";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, BarChart, Bar,
} from "recharts";

function chartThb(v) {
  if (v == null) return "";
  if (Math.abs(v) >= 1e6) return `฿${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `฿${(v / 1e3).toFixed(0)}K`;
  return `฿${v.toFixed(0)}`;
}

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

// Tooltip that spells out the inventory balance for the hovered month, so
// "on-hand < sold" reads clearly as "started X, +received, −sold, = end".
function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload || {};
  const num = (v) => (v == null ? "—" : Number(v).toLocaleString());
  const thb = (v) => (v == null ? "—" : `฿${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
  const start = d.onhand_start, recv = d["Received"] || 0, out = d.tr_out_qty || 0;
  const sold = d["Sold Qty"], end = d.onhand_end, avail = d["On-Hand Qty"];
  return (
    <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 6, padding: "8px 10px", fontSize: 12, boxShadow: "0 2px 8px rgba(0,0,0,.08)" }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      {avail != null ? (
        <div style={{ marginBottom: 4 }}>
          <div style={{ color: "#15803d" }}>
            On-hand: {num(start)} start + {num(recv)} received{out ? ` − ${num(out)} out` : ""} = <b>{num(avail)}</b>
          </div>
          <div style={{ color: "#6b7280", fontSize: 11 }}>
            sold {num(sold)} · {num(end)} left at month-end
          </div>
        </div>
      ) : (
        <div style={{ color: "#9ca3af", marginBottom: 4 }}>On-hand: start of month unknown (first recorded month)</div>
      )}
      <div style={{ color: "#1a3a8f" }}>Revenue (Actual): {thb(d["Revenue (Actual)"])}</div>
      <div style={{ color: "#2d4ea3" }}>Revenue (Master): {thb(d["Revenue (Master)"])}</div>
      <div style={{ color: "#b59a00" }}>Sold Qty: {num(sold)}</div>
    </div>
  );
}

export default function ItemAtLocationPage() {
  const { itemCode, whsCode } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedYears, setSelectedYears] = useState([CY]);
  const monthlyTrendRef = useRef(null);

  const toggleYear = (y) => {
    setSelectedYears((prev) => {
      if (prev.includes(y)) {
        if (prev.length === 1) return prev;
        return prev.filter((v) => v !== y);
      }
      return [...prev, y].sort((a, b) => b - a);
    });
  };

  const loadData = useCallback(
    async (years, signal) => {
      if (!itemCode || !whsCode) return;
      setLoading(true);
      setError(null);
      try {
        const qs = new URLSearchParams();
        qs.set("item_code", decodeURIComponent(itemCode));
        qs.set("whs_code", decodeURIComponent(whsCode));
        years.forEach((y) => qs.append("year_list", String(y)));
        const res = await api.get(`/api/item_at_location_trend?${qs.toString()}`, { signal });
        setData(res.data);
      } catch (e) {
        if (!isAbortError(e)) setError(e.message);
      } finally {
        setLoading(false);
      }
    },
    [itemCode, whsCode]
  );

  useEffect(() => {
    const controller = new AbortController();
    loadData(selectedYears, controller.signal);
    return () => controller.abort();
  }, [loadData, selectedYears]);

  const trendChartData = useMemo(() => {
    if (!data?.months?.length) return [];
    return data.months.map((m) => {
      const start = m.onhand_start;
      const recv = m.received_qty ?? 0;               // TR IN + GRPO into this location
      const out = m.tr_out_qty ?? 0;                  // transfers out
      // The plotted On-Hand is the stock AVAILABLE at the location this month:
      //   start-of-month + received − transfers out   (per the business definition)
      const onhand = (start == null) ? null : start + recv - out;
      return {
        period: m.period,
        "Sold Qty": m.is_partial ? m.running_rate_sold_qty ?? m.sold_qty : m.sold_qty,
        "Revenue (Actual)": m.is_partial ? m.running_rate_sold_thb ?? m.sold_thb : m.sold_thb,
        "Revenue (Master)": m.is_partial ? m.running_rate_sold_master_thb ?? m.sold_master_thb : m.sold_master_thb,
        "On-Hand Qty": onhand,
        "Received": recv,
        onhand_start: start,
        onhand_end: m.onhand_qty ?? null,             // end-of-month remaining (tooltip context)
        tr_out_qty: out,
        is_partial: !!m.is_partial,
        days_elapsed: m.days_elapsed,
        days_in_month: m.days_in_month,
      };
    });
  }, [data]);

  const hasOnhandTrend = useMemo(
    () => trendChartData.some((d) => d["On-Hand Qty"] != null && d["On-Hand Qty"] > 0),
    [trendChartData]
  );
  const onhandCaveat = useMemo(() => {
    const negs = data?.item_info?.onhand_negative_months;
    if (!negs || !negs.length) return null;
    return `On-hand is reconstructed from recorded stock movements and shown exactly as it comes out. ${negs.length} month${negs.length > 1 ? "s go" : " goes"} below zero — that means the records don't balance for ${negs.length > 1 ? "those months" : "that month"} (e.g. stock left with no transfer-out logged, or sales predate our data). Analytics floor on-hand at units sold, so these impossible values don't distort demand or planogram figures.`;
  }, [data]);

  const partialNote = useMemo(() => {
    if (!trendChartData.length) return null;
    const last = trendChartData[trendChartData.length - 1];
    if (!last?.is_partial) return null;
    return `Latest month (${last.period}) projected from ${last.days_elapsed}/${last.days_in_month} days`;
  }, [trendChartData]);

  // Per-year breakdown from monthly data
  const yearlyBreakdown = useMemo(() => {
    if (!data?.months?.length) return [];
    const byYear = {};
    data.months.forEach((m) => {
      const year = parseInt(m.period.split("-")[0], 10);
      if (!byYear[year]) {
        byYear[year] = { year, sold_qty: 0, sold_thb: 0, sold_master_thb: 0, months_active: 0 };
      }
      byYear[year].sold_qty += m.sold_qty;
      byYear[year].sold_thb += m.sold_thb;
      byYear[year].sold_master_thb += m.sold_master_thb;
      if (m.sold_qty > 0) byYear[year].months_active += 1;
    });
    return Object.values(byYear).sort((a, b) => a.year - b.year);
  }, [data]);

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");
  const info = data?.item_info || {};
  const summary = data?.summary || {};

  return (
    <main className="min-h-screen bg-gray-50 p-4 md:p-8">
      <div className="max-w-[1400px] mx-auto space-y-6">
        {/* Breadcrumb — goes Locations → location → item when consolidated */}
        <nav className="text-sm text-gray-500">
          <Link href="/" className="hover:underline">Home</Link>
          <span className="mx-1">/</span>
          {info.is_consolidated_location ? (
            <>
              <Link href="/dashboards/locations" className="hover:underline">Locations</Link>
              <span className="mx-1">/</span>
              <Link
                href={`/dashboards/locations/${encodeURIComponent(info.whs_name || decodeURIComponent(whsCode))}`}
                className="hover:underline"
              >
                {info.whs_name || decodeURIComponent(whsCode)}
              </Link>
            </>
          ) : (
            <>
              <Link href="/dashboards/brands" className="hover:underline">Brands</Link>
              {info.brand && (
                <>
                  <span className="mx-1">/</span>
                  <Link href={`/dashboards/brands/${encodeURIComponent(info.brand)}`} className="hover:underline">
                    {info.brand}
                  </Link>
                </>
              )}
            </>
          )}
          <span className="mx-1">/</span>
          <Link href={`/dashboards/item-detail/${encodeURIComponent(decodeURIComponent(itemCode))}`} className="hover:underline">
            {decodeURIComponent(itemCode)}
          </Link>
          {!info.is_consolidated_location && (
            <>
              <span className="mx-1">/</span>
              <span className="text-gray-800 font-medium">{info.whs_name || decodeURIComponent(whsCode)}</span>
            </>
          )}
        </nav>

        {/* Year filter */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-500">Year:</span>
          {YEAR_OPTIONS.map((y) => (
            <button
              key={y}
              onClick={() => toggleYear(y)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                selectedYears.includes(y)
                  ? "bg-[var(--nichi-blue)] text-white"
                  : "border border-gray-200 hover:bg-gray-100"
              }`}
            >
              {y}
            </button>
          ))}
        </div>

        {/* Loading / Error */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-10 w-10 border-4 border-[var(--nichi-blue)] border-t-transparent" />
            <span className="ml-3 text-gray-500">Loading...</span>
          </div>
        )}
        {error && <ErrorBanner message={`Failed to load: ${error}`} onRetry={() => loadData(selectedYears)} />}

        {!loading && !error && data && !data.found && (
          <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-3 rounded-lg">
            No data found for <strong>{decodeURIComponent(itemCode)}</strong> at <strong>{decodeURIComponent(whsCode)}</strong>.
          </div>
        )}

        {!loading && !error && data?.found && (
          <>
            {/* Header card */}
            <div className="bg-white rounded-xl shadow-md p-6">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                <div>
                  <h1 className="text-2xl font-bold text-gray-900">{info.item_code}</h1>
                  <p className="text-gray-600 text-lg mt-1">{info.item_name}</p>
                  <div className="flex items-center gap-3 mt-2 flex-wrap">
                    <Link
                      href={`/dashboards/brands/${encodeURIComponent(info.brand)}`}
                      className="inline-block px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition"
                    >
                      {info.brand}
                    </Link>
                    <span className="text-sm text-gray-500">at</span>
                    <Link
                      href={`/dashboards/locations/${encodeURIComponent(info.is_consolidated_location ? info.whs_name : info.whs_code)}`}
                      className="inline-block px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800 hover:bg-green-200 transition"
                    >
                      {info.whs_name}
                    </Link>
                    {info.is_consolidated_location ? (
                      info.whs_codes && info.whs_codes.length > 1 && (
                        <span className="text-xs text-gray-400" title={info.whs_codes.join(", ")}>
                          (consolidated: {info.whs_codes.length} sub-codes)
                        </span>
                      )
                    ) : (
                      info.whs_name !== info.whs_code && (
                        <span className="text-xs text-gray-400">({info.whs_code})</span>
                      )
                    )}
                  </div>
                </div>
                <div className="text-right text-sm text-gray-500">
                  Master Price: <span className="font-semibold text-gray-800">{fmtThb(info.master_price)}</span>
                </div>
              </div>
            </div>

            {/* KPI cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              <div className="bg-blue-50 rounded-xl shadow-sm p-4 text-center">
                <div className="text-xs text-blue-600 uppercase font-semibold">On-Hand Qty (Current)</div>
                <div className="text-xl font-bold text-blue-900">{fmtQty(summary.current_onhand_qty)}</div>
              </div>
              <div className="bg-blue-50 rounded-xl shadow-sm p-4 text-center">
                <div className="text-xs text-blue-600 uppercase font-semibold">On-Hand Value (@ Master)</div>
                <div className="text-xl font-bold text-blue-900">{fmtThb(summary.current_onhand_thb)}</div>
              </div>
              <div className="bg-yellow-50 rounded-xl shadow-sm p-4 text-center">
                <div className="text-xs text-yellow-700 uppercase font-semibold">Sold Qty ({yearLabel})</div>
                <div className="text-xl font-bold text-yellow-900">{fmtQty(summary.total_sold_qty)}</div>
              </div>
              <div className="bg-yellow-50 rounded-xl shadow-sm p-4 text-center">
                <div className="text-xs text-yellow-700 uppercase font-semibold">Revenue ({yearLabel}, Actual)</div>
                <div className="text-xl font-bold text-yellow-900">{fmtThb(summary.total_sold_thb)}</div>
              </div>
              <div className="bg-yellow-50 rounded-xl shadow-sm p-4 text-center">
                <div className="text-xs text-yellow-700 uppercase font-semibold">Revenue ({yearLabel}, Master)</div>
                <div className="text-xl font-bold text-yellow-900">{fmtThb(summary.total_sold_master_thb)}</div>
              </div>
            </div>

            {/* Profit cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white rounded-xl shadow-md p-4 text-center">
                <div className="text-xs text-gray-500 uppercase font-semibold mb-1">
                  COGS (FOB) ({yearLabel})
                  <InfoTooltip text="Cost of goods sold from GRPO purchase receipts at this location" size="sm" />
                </div>
                <div className="text-xl font-bold text-red-700">{fmtThb(summary.total_cogs_thb)}</div>
              </div>
              <div className="bg-white rounded-xl shadow-md p-4 text-center">
                <div className="text-xs text-gray-500 uppercase font-semibold mb-1">
                  GP Commission ({yearLabel})
                  <InfoTooltip text="Commission paid to retailer on consignment sales at this location" size="sm" />
                </div>
                <div className="text-xl font-bold text-orange-600">{fmtThb(summary.total_gp_commission)}</div>
              </div>
              <div className="bg-white rounded-xl shadow-md p-4 text-center">
                <div className="text-xs text-gray-500 uppercase font-semibold mb-1">
                  Gross Profit ({yearLabel})
                  <InfoTooltip text="Revenue (Actual) - COGS (FOB) - GP Commission" size="sm" />
                </div>
                <div className={`text-xl font-bold ${(summary.gross_profit_thb ?? 0) >= 0 ? "text-green-700" : "text-red-700"}`}>
                  {fmtThb(summary.gross_profit_thb)}
                </div>
              </div>
              <div className="bg-white rounded-xl shadow-md p-4 text-center">
                <div className="text-xs text-gray-500 uppercase font-semibold mb-1">
                  Margin % ({yearLabel})
                  <InfoTooltip text="Gross Profit / Revenue (Actual) x 100" size="sm" />
                </div>
                <div className={`text-xl font-bold ${(summary.margin_pct ?? 0) >= 0 ? "text-green-700" : "text-red-700"}`}>
                  {summary.margin_pct != null ? `${summary.margin_pct.toFixed(1)}%` : "N/A"}
                </div>
              </div>
            </div>

            {/* Per-year breakdown table (when multiple years selected) */}
            {yearlyBreakdown.length > 1 && (
              <div className="bg-white rounded-xl shadow-md p-6">
                <h2 className="text-lg font-semibold text-gray-800 mb-4">
                  Sales by Year
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b">
                        <th className="px-4 py-2 text-left font-semibold text-gray-600">Year</th>
                        <th className="px-4 py-2 text-right font-semibold text-gray-600">Sold Qty</th>
                        <th className="px-4 py-2 text-right font-semibold text-gray-600">Revenue (Actual Sales)</th>
                        <th className="px-4 py-2 text-right font-semibold text-gray-600">Revenue (Master)</th>
                        <th className="px-4 py-2 text-right font-semibold text-gray-600">Active Months</th>
                        <th className="px-4 py-2 text-right font-semibold text-gray-600">Avg Qty / Month</th>
                      </tr>
                    </thead>
                    <tbody>
                      {yearlyBreakdown.map((yr, idx) => (
                        <tr key={yr.year} className={`border-b ${idx % 2 === 0 ? "bg-white" : "bg-gray-50/50"}`}>
                          <td className="px-4 py-2 font-medium">{yr.year}</td>
                          <td className="px-4 py-2 text-right font-mono">{fmtQty(yr.sold_qty)}</td>
                          <td className="px-4 py-2 text-right font-mono">{fmtThb(yr.sold_thb)}</td>
                          <td className="px-4 py-2 text-right font-mono">{fmtThb(yr.sold_master_thb)}</td>
                          <td className="px-4 py-2 text-right font-mono">{yr.months_active}</td>
                          <td className="px-4 py-2 text-right font-mono">
                            {yr.months_active > 0 ? fmtQty(Math.round(yr.sold_qty / yr.months_active)) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="bg-blue-50 font-bold border-t-2 border-blue-200">
                        <td className="px-4 py-2">Total</td>
                        <td className="px-4 py-2 text-right font-mono">{fmtQty(summary.total_sold_qty)}</td>
                        <td className="px-4 py-2 text-right font-mono">{fmtThb(summary.total_sold_thb)}</td>
                        <td className="px-4 py-2 text-right font-mono">{fmtThb(summary.total_sold_master_thb)}</td>
                        <td className="px-4 py-2 text-right font-mono">
                          {yearlyBreakdown.reduce((s, y) => s + y.months_active, 0)}
                        </td>
                        <td className="px-4 py-2 text-right font-mono"></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            )}

            {/* Monthly trend chart — always rendered when we have months,
                even if sales are all zero. Shows on-hand level + any transfer
                activity so the user sees the story at a glance. */}
            {trendChartData.length > 0 && (
              <div className="bg-white rounded-xl shadow-md p-6">
                <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                  <h2 className="text-lg font-semibold text-gray-800">
                    Monthly Trend — {info.item_code} at {info.whs_name} ({yearLabel})
                  </h2>
                  <ChartDownloadToolbar
                    data={trendChartData}
                    filenameBase={`item_${info.item_code}_at_${info.whs_name}_monthly_${yearLabel.replace(/, /g, "_")}`}
                    chartRef={monthlyTrendRef}
                  />
                </div>
                {partialNote && (
                  <p className="text-xs text-amber-700 mb-3">
                    ⓘ {partialNote} — shown as full-month running-rate projection
                  </p>
                )}
                <div ref={monthlyTrendRef}>
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="left" tickFormatter={chartThb} tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                    <Tooltip content={<TrendTooltip />} />
                    <Legend />
                    <Line yAxisId="left" type="monotone" dataKey="Revenue (Actual)" stroke="#1a3a8f" strokeWidth={2} dot={false} />
                    <Line yAxisId="left" type="monotone" dataKey="Revenue (Master)" stroke="#2d4ea3" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                    <Line yAxisId="right" type="monotone" dataKey="Sold Qty" stroke="#FFD200" strokeWidth={2} dot={{ r: 3 }} />
                    {hasOnhandTrend && (
                      <Line yAxisId="right" type="monotone" dataKey="On-Hand Qty" stroke="#16a34a" strokeWidth={2} dot={{ r: 2 }} strokeDasharray="4 2" connectNulls={false} />
                    )}
                  </LineChart>
                </ResponsiveContainer>
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  <b>On-Hand Qty</b> (green) is the stock <b>available at this location</b> each month =
                  <b> start-of-month + received (TR IN + GRPO) − transfers out</b>. Hover any point for the full
                  breakdown — start, received, transfers out, sold, and what&apos;s left at month-end.
                </p>
                {onhandCaveat && (
                  <p className="text-xs text-amber-700 mt-1">ⓘ {onhandCaveat}</p>
                )}
              </div>
            )}

            {/* Stock Movement History — TR IN / TR OUT / GRPO events at this location */}
            <div className="bg-white rounded-xl shadow-md p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-2">
                Stock Movement History at {info.whs_name} ({yearLabel})
              </h2>
              <p className="text-xs text-gray-500 mb-4">
                Every Goods Receipt (GRPO), Transfer In, and Transfer Out for this item at any of
                the {info.whs_codes?.length || 1} sub-code{(info.whs_codes?.length || 1) === 1 ? "" : "s"} that roll up to this location.
              </p>
              {(!data.transfers || data.transfers.length === 0) ? (
                <p className="text-sm text-gray-500 italic">
                  No transfer or purchase records found for this item at this location in the selected period.
                  {summary.current_onhand_qty > 0 && (
                    <> (Current on-hand of {summary.current_onhand_qty} units has no paper trail — possibly pre-existing or transferred through a WhsCode not mapped to this location.)</>
                  )}
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b">
                        <th className="px-3 py-2 text-left font-semibold text-gray-600">Date</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-600">Type</th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-600">Qty</th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-600">Sub-WhsCode</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.transfers.map((t, i) => {
                        const badge = t.type === "GRPO"
                          ? "bg-purple-100 text-purple-800"
                          : t.type === "TR IN"
                          ? "bg-green-100 text-green-800"
                          : "bg-orange-100 text-orange-800";
                        return (
                          <tr key={`${t.date}-${t.type}-${i}`} className={`border-b ${i % 2 === 0 ? "bg-white" : "bg-gray-50/50"}`}>
                            <td className="px-3 py-2 font-mono">{t.date}</td>
                            <td className="px-3 py-2">
                              <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${badge}`}>
                                {t.type}
                              </span>
                            </td>
                            <td className={`px-3 py-2 text-right font-mono ${t.qty < 0 ? "text-red-600" : "text-gray-800"}`}>
                              {t.qty > 0 ? "+" : ""}{fmtQty(t.qty)}
                            </td>
                            <td className="px-3 py-2 font-mono text-xs text-gray-500">{t.whs_code}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot>
                      <tr className="bg-blue-50 font-bold border-t-2 border-blue-200">
                        <td className="px-3 py-2" colSpan={2}>Net movement ({data.transfers.length} events)</td>
                        <td className="px-3 py-2 text-right font-mono">
                          {(() => {
                            const net = data.transfers.reduce((s, t) => s + (t.qty || 0), 0);
                            return (net > 0 ? "+" : "") + fmtQty(net);
                          })()}
                        </td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </div>

            {/* Company-wide Purchase History (GRPO) — age of stock */}
            <div className="bg-white rounded-xl shadow-md p-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-2">
                Purchase History — {info.item_code} (company-wide, {yearLabel})
              </h2>
              <p className="text-xs text-gray-500 mb-4">
                Every import receipt (GRPO) for this item across all warehouses — useful for
                understanding how old the current on-hand stock is, even when it wasn't received
                directly at this location.
              </p>
              {(!data.purchases || data.purchases.length === 0) ? (
                <p className="text-sm text-gray-500 italic">
                  No GRPO records found for this item in the selected period.
                </p>
              ) : (
                <>
                  {(() => {
                    const ps = data.purchases;
                    const totalQty = ps.reduce((s, p) => s + (p.qty || 0), 0);
                    const totalThb = ps.reduce((s, p) => s + (p.fob_thb_total || 0), 0);
                    const earliest = ps[0]?.date;
                    const latest = ps[ps.length - 1]?.date;
                    const ageDays = latest ? Math.floor((new Date() - new Date(latest)) / (1000 * 60 * 60 * 24)) : null;
                    return (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                        <div className="bg-purple-50 rounded-lg p-3 text-center">
                          <div className="text-xs text-purple-600 uppercase font-semibold">Total Received</div>
                          <div className="text-lg font-bold text-purple-900">{fmtQty(totalQty)} units</div>
                        </div>
                        <div className="bg-purple-50 rounded-lg p-3 text-center">
                          <div className="text-xs text-purple-600 uppercase font-semibold">Total FOB Cost</div>
                          <div className="text-lg font-bold text-purple-900">{fmtThb(totalThb)}</div>
                        </div>
                        <div className="bg-purple-50 rounded-lg p-3 text-center">
                          <div className="text-xs text-purple-600 uppercase font-semibold">First Received</div>
                          <div className="text-lg font-bold text-purple-900">{earliest || "—"}</div>
                        </div>
                        <div className="bg-purple-50 rounded-lg p-3 text-center">
                          <div className="text-xs text-purple-600 uppercase font-semibold">Last Received</div>
                          <div className="text-lg font-bold text-purple-900">
                            {latest || "—"}
                            {ageDays != null && <span className="text-xs text-purple-600 block">({ageDays} days ago)</span>}
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-gray-50 border-b">
                          <th className="px-3 py-2 text-left font-semibold text-gray-600">Date</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">Qty</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-600">Vendor</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">Unit FOB</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-600">Currency</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">FX Rate</th>
                          <th className="px-3 py-2 text-right font-semibold text-gray-600">FOB Total (THB)</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-600">Received At</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.purchases.map((p, i) => (
                          <tr
                            key={`${p.date}-${i}`}
                            className={`border-b ${i % 2 === 0 ? "bg-white" : "bg-gray-50/50"} ${p.at_this_location ? "ring-1 ring-green-200" : ""}`}
                            title={p.at_this_location ? "Received directly at this location" : ""}
                          >
                            <td className="px-3 py-2 font-mono">{p.date}</td>
                            <td className="px-3 py-2 text-right font-mono">+{fmtQty(p.qty)}</td>
                            <td className="px-3 py-2 text-gray-700">{p.vendor || "—"}</td>
                            <td className="px-3 py-2 text-right font-mono">{p.unit_price_fob?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                            <td className="px-3 py-2 font-mono text-xs">{p.currency || "—"}</td>
                            <td className="px-3 py-2 text-right font-mono">{p.fx_rate}</td>
                            <td className="px-3 py-2 text-right font-mono">{fmtThb(p.fob_thb_total)}</td>
                            <td className="px-3 py-2 text-xs text-gray-500">
                              {p.whs_name}
                              {p.at_this_location && (
                                <span className="ml-1 inline-block px-1.5 py-0.5 rounded bg-green-100 text-green-700 text-[10px] font-medium">this location</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>

            {/* Monthly data table */}
            {data.months?.length > 0 && (
              <div className="bg-white rounded-xl shadow-md p-6">
                <h2 className="text-lg font-semibold text-gray-800 mb-4">
                  Monthly Detail ({data.months.length} months)
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b">
                        <th className="px-3 py-2 text-left font-semibold text-gray-600">Month</th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-600">Sold Qty</th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-600">Revenue (Actual Sales)</th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-600">Revenue (Master)</th>
                        <th className="px-3 py-2 text-right font-semibold text-gray-600">On-Hand Qty (End of Month)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.months.map((m, idx) => (
                        <tr key={m.period} className={`border-b ${idx % 2 === 0 ? "bg-white" : "bg-gray-50/50"}`}>
                          <td className="px-3 py-2 font-medium">{m.period}</td>
                          <td className="px-3 py-2 text-right font-mono">{fmtQty(m.sold_qty)}</td>
                          <td className="px-3 py-2 text-right font-mono">{fmtThb(m.sold_thb)}</td>
                          <td className="px-3 py-2 text-right font-mono">{fmtThb(m.sold_master_thb)}</td>
                          <td className="px-3 py-2 text-right font-mono">{fmtQty(m.onhand_qty)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="bg-blue-50 font-bold border-t-2 border-blue-200">
                        <td className="px-3 py-2">Total</td>
                        <td className="px-3 py-2 text-right font-mono">{fmtQty(summary.total_sold_qty)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmtThb(summary.total_sold_thb)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmtThb(summary.total_sold_master_thb)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmtQty(summary.current_onhand_qty)}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            )}

            {/* Empty state — only shown when truly nothing (backend also returns
                an empty months array in that case) */}
            {(!data.months || data.months.length === 0) && (!data.transfers || data.transfers.length === 0) && (
              <div className="bg-white rounded-xl shadow-md p-6 text-center text-gray-500">
                No activity found for this item at this location in the selected period ({yearLabel}).
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
