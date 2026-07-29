"use client";

import { useParams, useRouter } from "next/navigation";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Link from "next/link";
import ErrorBanner from "@/components/ErrorBanner";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import AbcdeBadge from "@/components/AbcdeBadge";
import ChartDownloadToolbar from "@/components/ChartDownloadToolbar";
import RecommendationPanel from "@/components/RecommendationCard";
import api, { isAbortError } from "@/utils/api";
import { downloadCsvFromObjects } from "@/utils/csvExport";
import { fmtQty, fmtThb } from "@/utils/formatters";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts";

function chartThb(v) {
  if (v == null) return "";
  if (Math.abs(v) >= 1e6) return `฿${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `฿${(v / 1e3).toFixed(0)}K`;
  return `฿${v.toFixed(0)}`;
}

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];
const BAR_CHART_DEFAULT = 20;

export default function ItemDetailPage() {
  const { itemCode } = useParams();
  const router = useRouter();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortCol, setSortCol] = useState("onhand_qty");
  const [sortAsc, setSortAsc] = useState(false);
  const [selectedYears, setSelectedYears] = useState([CY]);
  const [trendData, setTrendData] = useState(null);
  const [showAllBars, setShowAllBars] = useState(false);
  const monthlyTrendRef = useRef(null);
  const stockDistRef = useRef(null);

  const toggleYear = (y) => {
    setSelectedYears((prev) => {
      if (prev.includes(y)) {
        if (prev.length === 1) return prev;
        return prev.filter((v) => v !== y);
      }
      return [...prev, y].sort((a, b) => b - a);
    });
  };

  const loadData = useCallback(async (years, signal) => {
    if (!itemCode) return;
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      qs.set("item_code", itemCode);
      years.forEach((y) => qs.append("year_list", String(y)));
      const res = await api.get(`/api/item_location_detail?${qs.toString()}`, { signal });
      setData(res.data);
    } catch (e) {
      if (!isAbortError(e)) setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [itemCode]);

  const loadTrend = useCallback(
    async (years, signal) => {
      if (!itemCode) return;
      try {
        const qs = new URLSearchParams();
        qs.set("item_code", itemCode);
        years.forEach((y) => qs.append("year_list", String(y)));
        const res = await api.get(`/api/item_monthly_trend?${qs.toString()}`, { signal });
        if (res.data?.message !== "data not ready") setTrendData(res.data);
      } catch {
        // trend is supplementary — don't block the page on failure
      }
    },
    [itemCode]
  );

  useEffect(() => {
    const controller = new AbortController();
    loadData(selectedYears, controller.signal);
    loadTrend(selectedYears, controller.signal);
    return () => controller.abort();
  }, [loadData, loadTrend, selectedYears]);

  const trendChartData = useMemo(() => {
    if (!trendData?.months?.length) return [];
    return trendData.months.map((m) => ({
      period: m.period,
      // Swap to running rate for partial latest month so comparisons are fair
      "Sold Qty": m.is_partial ? m.running_rate_sold_qty ?? m.sold_qty : m.sold_qty,
      "Revenue (Actual)": m.is_partial ? m.running_rate_sold_thb ?? m.sold_thb : m.sold_thb,
      "Revenue (Master)": m.is_partial ? m.running_rate_sold_master_thb ?? m.sold_master_thb : m.sold_master_thb,
      "On-Hand Qty": m.onhand_qty ?? null,
      is_partial: !!m.is_partial,
      days_elapsed: m.days_elapsed,
      days_in_month: m.days_in_month,
    }));
  }, [trendData]);

  const itemTrendPartialNote = useMemo(() => {
    if (!trendChartData.length) return null;
    const last = trendChartData[trendChartData.length - 1];
    if (!last?.is_partial) return null;
    return `Latest month (${last.period}) projected from ${last.days_elapsed}/${last.days_in_month} days`;
  }, [trendChartData]);

  // Check if on-hand data is available in trend
  const hasOnhandTrend = useMemo(
    () => trendChartData.some((d) => d["On-Hand Qty"] != null && d["On-Hand Qty"] > 0),
    [trendChartData]
  );

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(false);
    }
  };

  const sortedLocations = data?.locations
    ? [...data.locations].sort((a, b) => {
        const va = a[sortCol] ?? 0;
        const vb = b[sortCol] ?? 0;
        return sortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
      })
    : [];

  // Chart data — show locations with either on-hand or sold
  const allChartData = sortedLocations
    .filter((l) => l.onhand_qty > 0 || l.lifetime_sold_qty > 0)
    .map((l) => ({
      name: l.whs_name.length > 30 ? l.whs_name.substring(0, 28) + "..." : l.whs_name,
      fullName: l.whs_name,
      whs_code: l.whs_code,
      "On-Hand Qty": l.onhand_qty,
      "Sold Qty": l.lifetime_sold_qty,
    }));

  const chartData = showAllBars ? allChartData : allChartData.slice(0, BAR_CHART_DEFAULT);
  const hasMoreBars = allChartData.length > BAR_CHART_DEFAULT;

  // Lookup: chart-axis-label → whs_code for clickable Y-axis labels
  const codeByName = useMemo(
    () => Object.fromEntries(chartData.map((d) => [d.name, d.whs_code])),
    [chartData]
  );

  const SortIcon = ({ col }) => (
    <span className="ml-1 text-xs opacity-50">
      {sortCol === col ? (sortAsc ? " ↑" : " ↓") : " ↕"}
    </span>
  );

  const columns = [
    { key: "whs_name", label: "Location", isText: true },
    { key: "whs_code", label: "Code", isText: true },
    { key: "onhand_qty", label: "On-Hand Qty" },
    { key: "onhand_thb", label: "On-Hand Value (THB)", isTHB: true },
    { key: "lifetime_sold_qty", label: "Sold Qty" },
    { key: "lifetime_sold_thb", label: "Revenue (THB, Actual Sales)", isTHB: true },
    { key: "lifetime_sold_master_thb", label: "Revenue (THB, Master)", isTHB: true },
  ];

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  return (
    <>
      <main className="min-h-screen bg-gray-50 p-4 md:p-8">
        <div className="max-w-[1400px] mx-auto space-y-6">
          {/* Breadcrumb */}
          <nav className="text-sm text-gray-500">
            <Link href="/" className="hover:underline">Home</Link>
            <span className="mx-1">/</span>
            <Link href="/dashboards/brands" className="hover:underline">Brands</Link>
            {data?.item_info?.brand && (
              <>
                <span className="mx-1">/</span>
                <Link href={`/dashboards/brands/${encodeURIComponent(data.item_info.brand)}`} className="hover:underline">
                  {data.item_info.brand}
                </Link>
              </>
            )}
            <span className="mx-1">/</span>
            <span className="text-gray-800 font-medium">{decodeURIComponent(itemCode)}</span>
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

          {/* Loading / Error states */}
          {loading && (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin rounded-full h-10 w-10 border-4 border-[var(--nichi-blue)] border-t-transparent" />
              <span className="ml-3 text-gray-500">Loading item details...</span>
            </div>
          )}

          {error && (
            <ErrorBanner message={`Failed to load item details: ${error}`} onRetry={() => loadData()} />
          )}

          {!loading && !error && data && !data.found && (
            <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-3 rounded-lg">
              Item <strong>{itemCode}</strong> not found in the system.
            </div>
          )}

          {!loading && !error && data?.found && (
            <>
              {/* Item header card */}
              <div className="bg-white rounded-xl shadow-md p-6">
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                  <div>
                    <h1 className="text-2xl font-bold text-gray-900">
                      {data.item_info.item_code}
                    </h1>
                    <p className="text-gray-600 text-lg mt-1">{data.item_info.item_name}</p>
                    <div className="flex items-center gap-2 mt-2 flex-wrap">
                      <Link
                        href={`/dashboards/brands/${encodeURIComponent(data.item_info.brand)}`}
                        className="inline-block px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition"
                      >
                        {data.item_info.brand}
                      </Link>
                      {data.item_info.abcde_class_in_brand && (
                        <AbcdeBadge tier={data.item_info.abcde_class_in_brand} context={`within ${data.item_info.brand}`} />
                      )}
                      {data.item_info.abcde_class_overall && (
                        <AbcdeBadge tier={data.item_info.abcde_class_overall} context="company-wide" />
                      )}
                    </div>
                    {data.item_info.master_price != null && data.item_info.master_price > 0 && (
                      <div className="mt-3 text-sm text-gray-500">
                        Master Price: <span className="font-semibold text-gray-800">{fmtThb(data.item_info.master_price)}</span>
                        <span className="text-xs text-gray-400 ml-1">(unit list price from Item Master)</span>
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                    <div className="bg-blue-50 rounded-lg p-3 text-center">
                      <div className="text-xs text-blue-600 uppercase font-semibold">On-Hand Qty</div>
                      <div className="text-xl font-bold text-blue-900">{fmtQty(data.item_info.total_onhand_qty)}</div>
                    </div>
                    <div className="bg-blue-50 rounded-lg p-3 text-center">
                      <div className="text-xs text-blue-600 uppercase font-semibold">On-Hand Value (@ Master Price)</div>
                      <div className="text-xl font-bold text-blue-900">{fmtThb(data.item_info.total_onhand_thb)}</div>
                    </div>
                    <div className="bg-yellow-50 rounded-lg p-3 text-center">
                      <div className="text-xs text-yellow-700 uppercase font-semibold">Sold Qty ({yearLabel})</div>
                      <div className="text-xl font-bold text-yellow-900">{fmtQty(data.item_info.total_sold_qty)}</div>
                    </div>
                    <div className="bg-yellow-50 rounded-lg p-3 text-center">
                      <div className="text-xs text-yellow-700 uppercase font-semibold">Revenue ({yearLabel}, Actual Sales)</div>
                      <div className="text-xl font-bold text-yellow-900">{fmtThb(data.item_info.total_sold_thb)}</div>
                    </div>
                    <div className="bg-yellow-50 rounded-lg p-3 text-center">
                      <div className="text-xs text-yellow-700 uppercase font-semibold">Revenue ({yearLabel}, Master)</div>
                      <div className="text-xl font-bold text-yellow-900">{fmtThb(data.item_info.total_sold_master_thb)}</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Profit & GP Commission KPI cards */}
              {(data.total_cogs_thb != null || data.total_gp_commission != null) && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-white rounded-xl shadow-md p-4 text-center">
                    <div className="text-xs text-gray-500 uppercase font-semibold mb-1">
                      COGS (FOB) ({yearLabel})
                      <InfoTooltip text="Cost of goods sold based on import cost (Price x Exchange Rate x Quantity) from GRPO purchase receipts" size="sm" />
                    </div>
                    <div className="text-xl font-bold text-red-700">{fmtThb(data.total_cogs_thb ?? 0)}</div>
                  </div>
                  <div className="bg-white rounded-xl shadow-md p-4 text-center">
                    <div className="text-xs text-gray-500 uppercase font-semibold mb-1">
                      GP Commission ({yearLabel})
                      <InfoTooltip text="Commission paid to retailers on consignment sales (LineTotal x U_ACT_GP / 100). Only applies to consignment sales, not credit sales." size="sm" />
                    </div>
                    <div className="text-xl font-bold text-orange-600">{fmtThb(data.total_gp_commission ?? 0)}</div>
                  </div>
                  <div className="bg-white rounded-xl shadow-md p-4 text-center">
                    <div className="text-xs text-gray-500 uppercase font-semibold mb-1">
                      Gross Profit ({yearLabel})
                      <InfoTooltip text="Revenue (Actual Sales) minus COGS (FOB) minus GP Commission. The true profit after all costs." size="sm" />
                    </div>
                    <div className={`text-xl font-bold ${(data.gross_profit_thb ?? 0) >= 0 ? "text-green-700" : "text-red-700"}`}>
                      {fmtThb(data.gross_profit_thb ?? 0)}
                    </div>
                  </div>
                  <div className="bg-white rounded-xl shadow-md p-4 text-center">
                    <div className="text-xs text-gray-500 uppercase font-semibold mb-1">
                      Margin % ({yearLabel})
                      <InfoTooltip text="Gross Profit / Revenue (Actual Sales) x 100. Percentage of revenue retained after COGS and GP Commission." size="sm" />
                    </div>
                    <div className={`text-xl font-bold ${(data.margin_pct ?? 0) >= 0 ? "text-green-700" : "text-red-700"}`}>
                      {data.margin_pct != null ? `${data.margin_pct.toFixed(1)}%` : "N/A"}
                    </div>
                  </div>
                </div>
              )}

              {/* Recommendations */}
              <RecommendationPanel context="item" name={data.item_info.item_code} years={selectedYears} />

              {/* Monthly Sales & On-Hand Trend */}
              {trendChartData.length > 0 && (
                <div className="bg-white rounded-xl shadow-md p-6">
                  <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                    <h2 className="text-lg font-semibold text-gray-800">
                      Monthly Sales{hasOnhandTrend ? " & On-Hand" : ""} — {data.item_info.item_code} ({yearLabel})
                    </h2>
                    <ChartDownloadToolbar
                      data={trendChartData}
                      filenameBase={`item_${data.item_info.item_code}_monthly_${yearLabel.replace(/, /g, "_")}`}
                      chartRef={monthlyTrendRef}
                    />
                  </div>
                  {itemTrendPartialNote && (
                    <p className="text-xs text-amber-700 mb-3">
                      ⓘ {itemTrendPartialNote} — shown as full-month running-rate projection for fair comparison
                    </p>
                  )}
                  <div ref={monthlyTrendRef}>
                  <ResponsiveContainer width="100%" height={320}>
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
                      On-Hand Qty (green dashed) is reconstructed backwards from current stock using sales, purchases, and transfers.
                    </p>
                  )}
                </div>
              )}

              {/* Bar chart — On-Hand vs. Lifetime Sold by Location */}
              {allChartData.length > 0 && (
                <div className="bg-white rounded-xl shadow-md p-6">
                  <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                    <h2 className="text-lg font-semibold text-gray-800">
                      Stock Distribution vs. Sales by Location ({yearLabel})
                      <InfoTooltip text={METRIC_TOOLTIPS.item.onhand_vs_sold} size="md" />
                    </h2>
                    <ChartDownloadToolbar
                      data={allChartData}
                      filenameBase={`item_${data.item_info.item_code}_stock_vs_sales_by_location_${yearLabel.replace(/, /g, "_")}`}
                      chartRef={stockDistRef}
                      csvColumns={["fullName", "On-Hand Qty", "Sold Qty"]}
                    />
                  </div>
                  <p className="text-sm text-gray-500 mb-4">
                    Compare where stock is currently held (blue) against where it has historically sold (yellow).
                    Locations with high stock but low sales are transfer-out candidates.
                  </p>
                  <div ref={stockDistRef}>
                  <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 40)}>
                    <BarChart
                      data={chartData}
                      layout="vertical"
                      margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" tickFormatter={(v) => v.toLocaleString()} />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={220}
                        tick={(tickProps) => {
                          const { x, y, payload } = tickProps;
                          const code = codeByName[payload.value];
                          const baseProps = {
                            x, y, dy: 4,
                            textAnchor: "end",
                            fontSize: 12,
                          };
                          if (!code) {
                            return (
                              <text {...baseProps} fill="#374151">
                                {payload.value}
                              </text>
                            );
                          }
                          const href = `/dashboards/item-detail/${encodeURIComponent(data.item_info.item_code)}/${encodeURIComponent(code)}`;
                          return (
                            <text
                              {...baseProps}
                              fill="var(--nichi-blue)"
                              style={{ cursor: "pointer", textDecoration: "underline" }}
                              onClick={() => router.push(href)}
                            >
                              <title>{`Open ${data.item_info.item_code} at ${payload.value}`}</title>
                              {payload.value}
                            </text>
                          );
                        }}
                      />
                      <Tooltip
                        formatter={(value, name) => [value.toLocaleString(), name]}
                        labelFormatter={(label, payload) =>
                          payload?.[0]?.payload?.fullName || label
                        }
                      />
                      <Legend />
                      <Bar dataKey="On-Hand Qty" fill="var(--nichi-blue)" radius={[0, 4, 4, 0]} />
                      <Bar dataKey="Sold Qty" fill="var(--nichi-yellow)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                  </div>
                  {hasMoreBars && (
                    <div className="mt-3 text-center">
                      <button
                        onClick={() => setShowAllBars(!showAllBars)}
                        className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 hover:bg-gray-100 transition-colors text-gray-700"
                      >
                        {showAllBars
                          ? `Show Less (Top ${BAR_CHART_DEFAULT})`
                          : `Show More (${allChartData.length - BAR_CHART_DEFAULT} more locations)`}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Detail table */}
              <div className="bg-white rounded-xl shadow-md p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-800">
                    Location Detail ({sortedLocations.length} locations)
                  </h2>
                  <button
                    onClick={() =>
                      downloadCsvFromObjects(
                        sortedLocations.map((l) => ({
                          ...l,
                          item_code: data.item_info.item_code,
                          item_name: data.item_info.item_name,
                          brand: data.item_info.brand,
                        })),
                        `item_${data.item_info.item_code}_locations_${selectedYears.sort((a, b) => a - b).join("_")}.csv`
                      )
                    }
                    className="px-4 py-2 text-sm bg-[var(--nichi-blue)] text-white rounded-lg hover:bg-[var(--nichi-blue-dark)] transition"
                  >
                    Export CSV
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b">
                        {columns.map((col) => (
                          <th
                            key={col.key}
                            onClick={() => handleSort(col.key)}
                            className="px-3 py-2 text-left font-semibold text-gray-600 cursor-pointer hover:bg-gray-100 select-none whitespace-nowrap"
                          >
                            {col.label}
                            <SortIcon col={col.key} />
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedLocations.map((loc, idx) => (
                        <tr
                          key={loc.whs_code}
                          onClick={() => router.push(`/dashboards/item-detail/${encodeURIComponent(data.item_info.item_code)}/${encodeURIComponent(loc.whs_code)}`)}
                          className={`border-b hover:bg-blue-50 transition cursor-pointer ${
                            idx % 2 === 0 ? "bg-white" : "bg-gray-50/50"
                          }`}
                          title={`View ${data.item_info.item_code} at ${loc.whs_name}`}
                        >
                          {columns.map((col) => (
                            <td
                              key={col.key}
                              className={`px-3 py-2 ${col.isText ? "" : "text-right font-mono"}`}
                            >
                              {col.isTHB ? fmtThb(loc[col.key]) : col.isText ? loc[col.key] : fmtQty(loc[col.key])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                    {/* Totals row */}
                    <tfoot>
                      <tr className="bg-blue-50 font-bold border-t-2 border-blue-200">
                        <td className="px-3 py-2">Total</td>
                        <td className="px-3 py-2"></td>
                        <td className="px-3 py-2 text-right font-mono">{fmtQty(data.item_info.total_onhand_qty)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmtThb(data.item_info.total_onhand_thb)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmtQty(data.item_info.total_sold_qty)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmtThb(data.item_info.total_sold_thb)}</td>
                        <td className="px-3 py-2 text-right font-mono">{fmtThb(data.item_info.total_sold_master_thb)}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>

              {/* Purchase History (GRPO) — company-wide, for stock-age context */}
              <div className="bg-white rounded-xl shadow-md p-6">
                <h2 className="text-lg font-semibold text-gray-800 mb-2">
                  Purchase History — {data.item_info.item_code} ({yearLabel})
                </h2>
                <p className="text-xs text-gray-500 mb-4">
                  Every import receipt (GRPO) for this item. Useful for understanding how old the current on-hand stock is and tracking FX / unit-cost trends across shipments.
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
                            <tr key={`${p.date}-${i}`} className={`border-b ${i % 2 === 0 ? "bg-white" : "bg-gray-50/50"}`}>
                              <td className="px-3 py-2 font-mono">{p.date}</td>
                              <td className="px-3 py-2 text-right font-mono">+{fmtQty(p.qty)}</td>
                              <td className="px-3 py-2 text-gray-700">{p.vendor || "—"}</td>
                              <td className="px-3 py-2 text-right font-mono">{p.unit_price_fob?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                              <td className="px-3 py-2 font-mono text-xs">{p.currency || "—"}</td>
                              <td className="px-3 py-2 text-right font-mono">{p.fx_rate}</td>
                              <td className="px-3 py-2 text-right font-mono">{fmtThb(p.fob_thb_total)}</td>
                              <td className="px-3 py-2 text-xs text-gray-500">{p.whs_name}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </main>
    </>
  );
}
