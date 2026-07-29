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
    return data.months.map((m) => ({
      period: m.period,
      "Sold Qty": m.sold_qty,
      "Revenue (Actual)": m.sold_thb,
      "Revenue (Master)": m.sold_master_thb,
      "On-Hand Qty": m.onhand_qty ?? null,
    }));
  }, [data]);

  const hasOnhandTrend = useMemo(
    () => trendChartData.some((d) => d["On-Hand Qty"] != null && d["On-Hand Qty"] > 0),
    [trendChartData]
  );

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
        {/* Breadcrumb */}
        <nav className="text-sm text-gray-500">
          <Link href="/" className="hover:underline">Home</Link>
          <span className="mx-1">/</span>
          <Link href="/dashboards/brands" className="hover:underline">Brands</Link>
          {info.brand && (
            <>
              <span className="mx-1">/</span>
              <Link href={`/dashboards/brands/${encodeURIComponent(info.brand)}`} className="hover:underline">
                {info.brand}
              </Link>
            </>
          )}
          <span className="mx-1">/</span>
          <Link href={`/dashboards/item-detail/${encodeURIComponent(decodeURIComponent(itemCode))}`} className="hover:underline">
            {decodeURIComponent(itemCode)}
          </Link>
          <span className="mx-1">/</span>
          <span className="text-gray-800 font-medium">{info.whs_name || decodeURIComponent(whsCode)}</span>
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
                      href={`/dashboards/locations/${encodeURIComponent(info.whs_code)}`}
                      className="inline-block px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800 hover:bg-green-200 transition"
                    >
                      {info.whs_name}
                    </Link>
                    <span className="text-xs text-gray-400">({info.whs_code})</span>
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

            {/* Monthly trend chart */}
            {trendChartData.length > 0 && (
              <div className="bg-white rounded-xl shadow-md p-6">
                <div className="flex flex-wrap items-start justify-between gap-2 mb-4">
                  <h2 className="text-lg font-semibold text-gray-800">
                    Monthly Trend — {info.item_code} at {info.whs_name} ({yearLabel})
                  </h2>
                  <ChartDownloadToolbar
                    data={trendChartData}
                    filenameBase={`item_${info.item_code}_at_${info.whs_name}_monthly_${yearLabel.replace(/, /g, "_")}`}
                    chartRef={monthlyTrendRef}
                  />
                </div>
                <div ref={monthlyTrendRef}>
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="left" tickFormatter={chartThb} tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v, name) => name.includes("Qty") ? [fmtQty(v), name] : [fmtThb(v), name]} />
                    <Legend />
                    <Line yAxisId="left" type="monotone" dataKey="Revenue (Actual)" stroke="#1a3a8f" strokeWidth={2} dot={false} />
                    <Line yAxisId="left" type="monotone" dataKey="Revenue (Master)" stroke="#2d4ea3" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                    <Line yAxisId="right" type="monotone" dataKey="Sold Qty" stroke="#FFD200" strokeWidth={2} dot={{ r: 3 }} />
                    {hasOnhandTrend && (
                      <Line yAxisId="right" type="monotone" dataKey="On-Hand Qty" stroke="#16a34a" strokeWidth={2} dot={{ r: 2 }} strokeDasharray="4 2" />
                    )}
                  </LineChart>
                </ResponsiveContainer>
                </div>
                {hasOnhandTrend && (
                  <p className="text-xs text-gray-400 mt-2">
                    On-Hand Qty (green dashed) is reconstructed backwards from current stock at this location using sales, purchases, and transfers.
                  </p>
                )}
              </div>
            )}

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

            {/* Empty state */}
            {(!data.months || data.months.length === 0) && (
              <div className="bg-white rounded-xl shadow-md p-6 text-center text-gray-500">
                No sales data found for this item at this location in the selected period ({yearLabel}).
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
