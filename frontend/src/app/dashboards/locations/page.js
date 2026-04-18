"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
} from "recharts";
import api, { isAbortError } from "@/utils/api";
import SortableTable from "@/components/SortableTable";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBanner from "@/components/ErrorBanner";
import StatusBadge from "@/components/StatusBadge";
import AbcdeBadge from "@/components/AbcdeBadge";
import KpiCard from "@/components/KpiCard";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import { fmtThb, fmtQty, fmtPct, fmtRatio, fmtDays } from "@/utils/formatters";
import { downloadCsv, downloadCsvFromObjects } from "@/utils/csvExport";

function chartThb(v) {
  if (v == null) return "";
  if (Math.abs(v) >= 1e6) return `\u0E3F${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `\u0E3F${(v / 1e3).toFixed(0)}K`;
  return `\u0E3F${v.toFixed(0)}`;
}

const LOC_COLORS = [
  "#1a3a8f", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6",
  "#1abc9c", "#e67e22", "#3498db", "#c0392b", "#27ae60",
];
const STATUS_COLORS = { green: "#059669", yellow: "#d97706", red: "#dc2626" };
const INV_STATUS_COLORS = { overstocked: "#dc2626", optimal: "#059669", understocked: "#d97706" };
const INV_STATUS_BG = {
  overstocked: "bg-red-100 text-red-800",
  optimal: "bg-green-100 text-green-800",
  understocked: "bg-amber-100 text-amber-800",
};

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

const TABS = [
  { id: "performance", label: "Performance" },
  { id: "investment", label: "Investment Analysis" },
  { id: "trends", label: "Sales Trends" },
  { id: "product-mix", label: "Product Mix" },
];

function isOnlineLocation(name) {
  if (!name) return false;
  const lower = name.toLowerCase();
  return lower.includes("shopee") || lower.includes("lazada") || lower.includes("online");
}


// ============================================================
// PERFORMANCE TAB (merged from Locations list + Location Analytics Performance)
// ============================================================
function PerformanceTab({ selectedYears, toggleYear, onLocationClick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [trendData, setTrendData] = useState(null);

  const loadPerf = useCallback((years, signal) => {
    setLoading(true);
    setError(null);
    const qs = new URLSearchParams();
    years.forEach((y) => qs.append("year_list", String(y)));
    api.get(`/api/location_performance?${qs.toString()}`, { signal })
      .then((res) => {
        if (res.data?.message === "data not ready") { setError("Data is still loading."); return; }
        setData(res.data);
      })
      .catch((err) => { if (!isAbortError(err)) setError(err.response?.data?.error || err.message); })
      .finally(() => setLoading(false));
  }, []);

  const loadTrend = useCallback((years, signal) => {
    const qs = new URLSearchParams();
    qs.set("top_n", "10");
    years.forEach((y) => qs.append("year_list", String(y)));
    api.get(`/api/location_trends?${qs.toString()}`, { signal })
      .then((res) => { if (res.data?.message !== "data not ready") setTrendData(res.data); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    loadPerf(selectedYears, ctrl.signal);
    loadTrend(selectedYears, ctrl.signal);
    return () => ctrl.abort();
  }, [loadPerf, loadTrend, selectedYears]);

  const trendChartData = useMemo(() => {
    if (!trendData?.trends?.length) return [];
    const periods = trendData.periods || [];
    return periods.map((p) => {
      const point = { period: p };
      for (const t of trendData.trends) {
        const m = t.months.find((m) => m.period === p);
        point[t.location] = m ? m.sold_thb : 0;
      }
      return point;
    });
  }, [trendData]);

  if (loading) return <LoadingSpinner message="Loading location data..." />;
  if (error) return <ErrorBanner message={error} onRetry={() => loadPerf(selectedYears)} />;
  if (!data?.locations?.length) return <div className="text-gray-400 text-center py-8">No location data available</div>;

  const { locations, summary, company_avg } = data;

  // Health chart (top 15)
  const healthChartData = locations.slice(0, 15).map((loc) => ({
    name: loc.location.length > 18 ? loc.location.slice(0, 16) + ".." : loc.location,
    fullName: loc.location,
    value: loc.health_score ?? 0,
    status: loc.status,
  }));

  // Scatter
  const scatterData = locations.map((loc) => ({
    x: loc.onhand_thb, y: loc.sold_thb, name: loc.location,
    status: loc.status, efficiency: loc.revenue_per_thb_inventory,
  }));

  const columns = [
    {
      key: "location", label: "Location",
      render: (val, row) => (
        <span className="flex items-center gap-1.5">
          <button type="button" onClick={() => onLocationClick?.(val)}
            className="text-[var(--nichi-blue)] hover:underline font-medium text-left">
            {val}
          </button>
          {isOnlineLocation(val) && (
            <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-700 border border-purple-200">Online</span>
          )}
        </span>
      ),
    },
    { key: "abcde_class", label: "Tier", render: (v) => <AbcdeBadge tier={v} context="by company revenue" /> },
    { key: "health_score", label: "Health", render: (v) => {
      const score = v ?? 0;
      const color = score >= 70 ? "text-green-700 bg-green-50" : score >= 40 ? "text-amber-700 bg-amber-50" : "text-red-700 bg-red-50";
      return <span className={`inline-block px-2 py-0.5 rounded font-bold text-sm ${color}`}>{score.toFixed(1)}</span>;
    }},
    { key: "status", label: "Status", render: (v) => <StatusBadge severity={v} /> },
    { key: "sold_thb", label: "Revenue (THB, Actual Sales)", fmt: fmtThb },
    { key: "sold_master_thb", label: "Revenue (THB, Master)", fmt: fmtThb, tooltip: "Sold Qty \u00d7 Master (list) Price" },
    { key: "onhand_thb", label: "On-Hand (THB @ Master Price)", fmt: fmtThb },
    { key: "revenue_per_thb_inventory", label: "Rev / Inventory", fmt: (v) => fmtRatio(v, "x"), tooltip: "Revenue per THB of inventory. Higher = more efficient." },
    { key: "sold_qty", label: "Sold Qty", fmt: fmtQty },
    { key: "onhand_qty", label: "On-Hand Qty", fmt: fmtQty },
    { key: "sell_through_rate", label: "Sell-Through %", fmt: fmtPct },
    { key: "stock_turnover", label: "Turnover", fmt: (v) => fmtRatio(v, "x") },
    { key: "days_cover", label: "Days Cover", fmt: fmtDays },
    { key: "dead_stock_pct", label: "Dead Stock %", fmt: fmtPct },
  ];

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  const handleExport = () => {
    downloadCsvFromObjects(
      locations.map((r) => ({
        Location: r.location, Tier: r.abcde_class, Health: r.health_score, Status: r.status,
        "Revenue (THB, Actual)": r.sold_thb, "Revenue (THB, Master)": r.sold_master_thb,
        "On-Hand (THB @ Master)": r.onhand_thb, "Rev/Inventory": r.revenue_per_thb_inventory,
        "Sold Qty": r.sold_qty, "On-Hand Qty": r.onhand_qty,
        "Sell-Through %": r.sell_through_rate, Turnover: r.stock_turnover,
        "Days Cover": r.days_cover, "Dead Stock %": r.dead_stock_pct,
      })),
      `locations_${yearLabel.replace(/, /g, "_")}.csv`
    );
  };

  return (
    <div className="space-y-6">
      {/* Year filter */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-gray-500">Year:</span>
        {YEAR_OPTIONS.map((y) => (
          <button key={y} onClick={() => toggleYear(y)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${selectedYears.includes(y) ? "bg-[var(--nichi-blue)] text-white" : "border border-gray-200 hover:bg-gray-100"}`}>
            {y}
          </button>
        ))}
        {locations.length > 0 && (
          <>
            <div className="w-px h-6 bg-gray-200 mx-1" />
            <button onClick={handleExport}
              className="px-4 py-1.5 text-sm bg-[var(--nichi-blue)] text-white rounded-lg hover:bg-[var(--nichi-blue-dark)]">
              Export CSV
            </button>
          </>
        )}
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <KpiCard label="Locations" value={summary.total_locations} />
        <KpiCard label="Total Revenue" value={fmtThb(summary.total_sold_thb)} />
        <KpiCard label="Total On-Hand (@ Master)" value={fmtThb(summary.total_onhand_thb)} />
        <KpiCard label="Avg Efficiency" value={fmtRatio(company_avg.revenue_per_thb_inventory)} sub="Rev/THB Inv" />
        <KpiCard label="Avg Health" value={summary.avg_health_score ?? "\u2014"} sub={`${summary.min_health_score ?? 0} \u2013 ${summary.max_health_score ?? 0}`} />
        <KpiCard label="Healthy" value={summary.green_count} sub="green" />
        <KpiCard label="At Risk" value={summary.red_count} sub="red" />
      </div>

      {/* Monthly revenue trend */}
      {trendChartData.length > 0 && (
        <div className="bg-white rounded-lg shadow border p-4">
          <h2 className="text-base font-semibold text-gray-800 mb-3">Monthly Revenue by Top Locations — {yearLabel}</h2>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={chartThb} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Legend />
              {(trendData?.trends || []).map((t, i) => (
                <Line key={t.location} type="monotone" dataKey={t.location}
                  stroke={LOC_COLORS[i % LOC_COLORS.length]} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Charts row: Health + Scatter */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow border p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Health Score (0-100)</h3>
          <p className="text-xs text-gray-400 mb-2">Weighted: Efficiency 40%, Sell-Through 25%, Low Dead Stock 20%, Lean Inventory 15%</p>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={healthChartData} layout="vertical" margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" domain={[0, 100]} />
              <YAxis dataKey="name" type="category" width={130} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => [v.toFixed(1) + " / 100", "Health Score"]}
                labelFormatter={(_, payload) => payload?.[0]?.payload?.fullName || ""} />
              <Bar dataKey="value" name="Health Score">
                {healthChartData.map((entry, i) => (
                  <Cell key={i} fill={STATUS_COLORS[entry.status] || "#6b7280"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-lg shadow border p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-1">Inventory vs Revenue (above trend = efficient)</h3>
          <ResponsiveContainer width="100%" height={350}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="x" name="On-Hand (THB)" type="number" tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
              <YAxis dataKey="y" name="Revenue (THB)" type="number" tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
              <ZAxis dataKey="efficiency" range={[40, 400]} />
              <Tooltip content={({ payload }) => {
                if (!payload?.length) return null;
                const d = payload[0].payload;
                return (
                  <div className="bg-white border rounded shadow p-2 text-xs">
                    <p className="font-semibold">{d.name}</p>
                    <p>On-Hand: {fmtThb(d.x)}</p>
                    <p>Revenue: {fmtThb(d.y)}</p>
                    <p>Efficiency: {fmtRatio(d.efficiency)}</p>
                  </div>
                );
              }} />
              <Scatter data={scatterData}>
                {scatterData.map((entry, i) => (
                  <Cell key={i} fill={STATUS_COLORS[entry.status] || "#6b7280"} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Main table */}
      <div className="bg-white rounded-lg shadow border overflow-hidden">
        <SortableTable columns={columns} data={locations} defaultSort="revenue_per_thb_inventory" defaultDir="desc" pageSize={100} />
      </div>
    </div>
  );
}


// ============================================================
// INVESTMENT ANALYSIS TAB
// ============================================================
function InvestmentTab({ selectedYears, toggleYear }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [targetDays, setTargetDays] = useState("90");
  const [showAllRevChart, setShowAllRevChart] = useState(false);
  const [showAllInvChart, setShowAllInvChart] = useState(false);

  const fetchData = useCallback(async (signal) => {
    setLoading(true); setError(null);
    try {
      const qs = new URLSearchParams();
      selectedYears.forEach((y) => qs.append("year_list", String(y)));
      if (targetDays) qs.set("target_cover_days", targetDays);
      const res = await api.get(`/api/location_performance?${qs.toString()}`, { signal });
      setData(res.data);
    } catch (e) { if (!isAbortError(e)) setError(e.message); }
    finally { setLoading(false); }
  }, [selectedYears, targetDays]);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchData(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchData]);

  if (loading) return <LoadingSpinner message="Loading investment data..." />;
  if (error) return <ErrorBanner message={error} onRetry={() => fetchData()} />;
  if (!data?.locations?.length) return <div className="text-gray-400 text-center py-8">No data</div>;

  const { locations, summary } = data;
  const sortedByGap = [...locations].sort((a, b) => b.inventory_gap_thb - a.inventory_gap_thb);

  const allInvChartData = sortedByGap.map((loc) => ({
    name: loc.location.length > 18 ? loc.location.slice(0, 16) + ".." : loc.location,
    fullName: loc.location, actual: loc.onhand_thb, target: loc.target_onhand_thb,
    gap: loc.inventory_gap_thb, status: loc.inventory_status,
  }));
  const INV_DEFAULT = 20;
  const invChartData = showAllInvChart ? allInvChartData : allInvChartData.slice(0, INV_DEFAULT);

  const allRevData = [...locations].sort((a, b) => b.revenue_per_thb_inventory - a.revenue_per_thb_inventory)
    .map((loc) => ({
      name: loc.location.length > 18 ? loc.location.slice(0, 16) + ".." : loc.location,
      fullName: loc.location, revenue: loc.sold_thb, onhand: loc.onhand_thb,
      efficiency: loc.revenue_per_thb_inventory,
    }));
  const REV_DEFAULT = 15;
  const revChartData = showAllRevChart ? allRevData : allRevData.slice(0, REV_DEFAULT);

  const invColumns = [
    { key: "location", label: "Location", render: (v) => <span className="font-medium">{v}</span> },
    { key: "inventory_status", label: "Status", render: (v) => <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${INV_STATUS_BG[v] || "bg-gray-100 text-gray-700"}`}>{v}</span> },
    { key: "onhand_thb", label: "Actual On-Hand (THB @ Master)", render: (v) => fmtThb(v) },
    { key: "target_onhand_thb", label: "Target On-Hand (THB)", render: (v) => fmtThb(v) },
    { key: "inventory_gap_thb", label: "Gap (THB)", render: (v) => {
      if (v == null) return "\u2014";
      const c = v > 0 ? "text-red-600" : v < 0 ? "text-amber-600" : "text-green-600";
      return <span className={c}>{v > 0 ? "+" : ""}{fmtThb(v)}</span>;
    }},
    { key: "revenue_per_thb_inventory", label: "Rev/THB Inv", render: (v) => fmtRatio(v) },
    { key: "days_cover", label: "Days Cover", render: (v) => v != null ? fmtQty(v) : "\u221E" },
    { key: "sold_thb", label: "Revenue", render: (v) => fmtThb(v) },
  ];

  const handleExport = () => {
    downloadCsv(`location_investment_${selectedYears.join("_")}.csv`,
      invColumns.map((c) => c.label),
      sortedByGap.map((loc) => invColumns.map((c) => loc[c.key])));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-500">Year:</span>
          {YEAR_OPTIONS.map((y) => (
            <button key={y} onClick={() => toggleYear(y)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${selectedYears.includes(y) ? "bg-[var(--nichi-blue)] text-white" : "border border-gray-200 hover:bg-gray-100"}`}>{y}</button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-600">Target Days Cover:</span>
          {["30", "60", "90"].map((d) => (
            <button key={d} onClick={() => setTargetDays(d)}
              className={`px-3 py-1 rounded text-sm ${targetDays === d ? "bg-[var(--nichi-blue)] text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>{d}d</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard label="Overstocked" value={summary.overstocked_count} sub={`${fmtThb(summary.total_excess_thb)} excess`} />
        <KpiCard label="Optimal" value={summary.optimal_count} sub="within range" />
        <KpiCard label="Understocked" value={summary.understocked_count} sub={`${fmtThb(summary.total_shortfall_thb)} shortfall`} />
        <KpiCard label="Total On-Hand" value={fmtThb(summary.total_onhand_thb)} />
        <KpiCard label="Total Revenue" value={fmtThb(summary.total_sold_thb)} />
        <KpiCard label="Target Cover" value={`${summary.target_cover_days}d`} />
      </div>

      {/* Revenue vs On-Hand */}
      <div className="bg-white rounded-lg shadow border p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Revenue vs Inventory by Location</h3>
        <p className="text-xs text-gray-400 mb-3">Sorted by efficiency. Revenue bar &gt; on-hand bar = efficient.</p>
        <ResponsiveContainer width="100%" height={Math.max(400, revChartData.length * 32)}>
          <BarChart data={revChartData} layout="vertical" margin={{ left: 10, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
            <YAxis dataKey="name" type="category" width={130} tick={{ fontSize: 11 }} />
            <Tooltip content={({ payload }) => {
              if (!payload?.length) return null;
              const d = payload[0].payload;
              return (<div className="bg-white border rounded shadow p-2 text-xs">
                <p className="font-semibold">{d.fullName}</p>
                <p>Revenue: {fmtThb(d.revenue)}</p><p>On-Hand: {fmtThb(d.onhand)}</p>
                <p>Efficiency: {fmtRatio(d.efficiency)}</p>
              </div>);
            }} />
            <Legend />
            <Bar dataKey="revenue" name="Revenue (THB)" fill="#1a3a8f" />
            <Bar dataKey="onhand" name="On-Hand (THB)" fill="#FFD200" />
          </BarChart>
        </ResponsiveContainer>
        {allRevData.length > REV_DEFAULT && (
          <div className="mt-3 text-center">
            <button onClick={() => setShowAllRevChart(!showAllRevChart)}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 hover:bg-gray-100 text-gray-700">
              {showAllRevChart ? `Show Less (Top ${REV_DEFAULT})` : `Show More (${allRevData.length - REV_DEFAULT} more)`}
            </button>
          </div>
        )}
      </div>

      {/* Actual vs Target */}
      <div className="bg-white rounded-lg shadow border p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Actual vs Target Inventory ({summary.target_cover_days}-day cover)</h3>
        <ResponsiveContainer width="100%" height={Math.max(300, invChartData.length * 28)}>
          <BarChart data={invChartData} layout="vertical" margin={{ left: 10, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
            <YAxis dataKey="name" type="category" width={130} tick={{ fontSize: 11 }} />
            <Tooltip content={({ payload }) => {
              if (!payload?.length) return null;
              const d = payload[0].payload;
              return (<div className="bg-white border rounded shadow p-2 text-xs">
                <p className="font-semibold">{d.fullName}</p>
                <p>Actual: {fmtThb(d.actual)}</p><p>Target: {fmtThb(d.target)}</p>
                <p>Gap: {d.gap > 0 ? "+" : ""}{fmtThb(d.gap)}</p><p>Status: {d.status}</p>
              </div>);
            }} />
            <Legend />
            <Bar dataKey="actual" name="Actual On-Hand" fill="#1a3a8f">
              {invChartData.map((e, i) => <Cell key={i} fill={INV_STATUS_COLORS[e.status] || "#6b7280"} />)}
            </Bar>
            <Bar dataKey="target" name="Target On-Hand" fill="#94a3b8" />
          </BarChart>
        </ResponsiveContainer>
        {allInvChartData.length > INV_DEFAULT && (
          <div className="mt-3 text-center">
            <button onClick={() => setShowAllInvChart(!showAllInvChart)}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 hover:bg-gray-100 text-gray-700">
              {showAllInvChart ? `Show Less (Top ${INV_DEFAULT})` : `Show More (${allInvChartData.length - INV_DEFAULT} more)`}
            </button>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg shadow border p-4">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold text-gray-700">Inventory Status (sorted by gap)</h3>
          <button onClick={handleExport} className="px-3 py-1 rounded text-xs bg-[var(--nichi-blue)] text-white hover:bg-[var(--nichi-blue-dark)]">Download CSV</button>
        </div>
        <SortableTable columns={invColumns} data={sortedByGap} defaultSort="inventory_gap_thb" />
      </div>
    </div>
  );
}


// ============================================================
// SALES TRENDS TAB (merged from Location Analytics Trends + Store Scorecard)
// ============================================================
function TrendsTab({ selectedYears, toggleYear, locationNames }) {
  const [allData, setAllData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedLocs, setSelectedLocs] = useState([]);

  const fetchTrends = useCallback(async (years, signal) => {
    setLoading(true); setError(null);
    try {
      const qs = new URLSearchParams();
      qs.set("top_n", "50");
      years.forEach((y) => qs.append("year_list", String(y)));
      const res = await api.get(`/api/location_trends?${qs.toString()}`, { signal });
      setAllData(res.data);
    } catch (e) { if (!isAbortError(e)) setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchTrends(selectedYears, ctrl.signal);
    return () => ctrl.abort();
  }, [fetchTrends, selectedYears]);

  if (loading) return <LoadingSpinner message="Loading trends..." />;
  if (error) return <ErrorBanner message={error} onRetry={() => fetchTrends(selectedYears)} />;
  if (!allData?.trends?.length) return <div className="text-gray-400 text-center py-8">No trend data</div>;

  const filteredTrends = selectedLocs.length > 0
    ? allData.trends.filter((t) => selectedLocs.includes(t.location))
    : allData.trends.slice(0, 10);
  const periods = allData.periods;

  const toggleLoc = (loc) => {
    setSelectedLocs((prev) => {
      if (prev.includes(loc)) return prev.filter((l) => l !== loc);
      if (prev.length >= 5) return prev;
      return [...prev, loc];
    });
  };

  const chartData = periods.map((period) => {
    const row = { period };
    filteredTrends.forEach((t) => {
      const m = t.months.find((mo) => mo.period === period);
      row[t.location] = m ? m.sold_thb : 0;
    });
    return row;
  });

  const locNames = filteredTrends.map((t) => t.location);
  const allLocNames = allData.trends.map((t) => t.location);

  // Top 10 / Bottom 10 by total revenue
  const totalByLoc = allData.trends.map((t) => ({
    name: t.location.length > 20 ? t.location.slice(0, 18) + ".." : t.location,
    value: t.months.reduce((s, m) => s + m.sold_thb, 0),
  })).sort((a, b) => b.value - a.value);

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  return (
    <div className="space-y-6">
      {/* Year filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-gray-500">Year:</span>
        {YEAR_OPTIONS.map((y) => (
          <button key={y} onClick={() => toggleYear(y)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${selectedYears.includes(y) ? "bg-[var(--nichi-blue)] text-white" : "border border-gray-200 hover:bg-gray-100"}`}>{y}</button>
        ))}
      </div>

      {/* Location selector */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-gray-600">Compare locations:</span>
          <button onClick={() => setSelectedLocs([])}
            className={`px-3 py-1 rounded text-sm ${selectedLocs.length === 0 ? "bg-[var(--nichi-blue)] text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>
            Top 10 (default)
          </button>
          {selectedLocs.length > 0 && <span className="text-xs text-gray-500">{selectedLocs.length}/5 selected</span>}
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          {(locationNames.length > 0 ? locationNames : allLocNames).map((loc) => {
            const isSelected = selectedLocs.includes(loc);
            const isFull = selectedLocs.length >= 5 && !isSelected;
            return (
              <button key={loc} onClick={() => toggleLoc(loc)} disabled={isFull}
                className={`px-2.5 py-1 rounded text-xs transition-colors ${isSelected ? "bg-[var(--nichi-blue)] text-white" : isFull ? "bg-gray-50 text-gray-300 cursor-not-allowed" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>
                {loc.length > 20 ? loc.slice(0, 18) + ".." : loc}
              </button>
            );
          })}
        </div>
      </div>

      {/* Trend line chart */}
      <div className="bg-white rounded-lg shadow border p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Monthly Revenue Trends — {yearLabel}
          {selectedLocs.length > 0 && <span className="text-xs font-normal text-gray-400 ml-2">({selectedLocs.length} compared)</span>}
        </h3>
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 10 }} interval={Math.max(0, Math.floor(periods.length / 12))} />
            <YAxis tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Legend />
            {locNames.map((loc, i) => (
              <Line key={loc} type="monotone" dataKey={loc}
                stroke={LOC_COLORS[i % LOC_COLORS.length]} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Top 10 / Bottom 10 bar charts */}
      {totalByLoc.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-lg shadow border p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">Top 10 by Revenue — {yearLabel}</h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={[...totalByLoc.slice(0, 10)].reverse()} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={chartThb} />
                <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v) => fmtThb(v)} />
                <Bar dataKey="value" fill="#1a3a8f" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-white rounded-lg shadow border p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">Bottom 10 by Revenue — {yearLabel}</h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={totalByLoc.slice(-10).reverse()} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={chartThb} />
                <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v) => fmtThb(v)} />
                <Bar dataKey="value" fill="#d97706" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Revenue by Period table */}
      <div className="bg-white rounded-lg shadow border p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Revenue by Period</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="px-3 py-2 text-left font-semibold text-gray-700 sticky left-0 bg-gray-50">Location</th>
                {periods.map((p) => <th key={p} className="px-3 py-2 text-right font-semibold text-gray-700 whitespace-nowrap">{p}</th>)}
                <th className="px-3 py-2 text-right font-semibold text-gray-700">Total</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrends.map((t, i) => {
                const total = t.months.reduce((s, m) => s + m.sold_thb, 0);
                return (
                  <tr key={t.location} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                    <td className="px-3 py-2 font-medium sticky left-0 bg-inherit whitespace-nowrap">{t.location}</td>
                    {t.months.map((m) => <td key={m.period} className="px-3 py-2 text-right whitespace-nowrap">{fmtThb(m.sold_thb)}</td>)}
                    <td className="px-3 py-2 text-right font-semibold whitespace-nowrap">{fmtThb(total)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


// ============================================================
// PRODUCT MIX TAB
// ============================================================
function ProductMixTab({ locationNames, initialLocation }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedLoc, setSelectedLoc] = useState(initialLocation || "");

  const fetchData = useCallback(async (signal) => {
    if (!selectedLoc) { setData(null); setLoading(false); return; }
    setLoading(true); setError(null);
    try {
      const res = await api.get("/api/location_product_mix", { params: { location: selectedLoc }, signal });
      setData(res.data);
    } catch (e) { if (!isAbortError(e)) setError(e.message); }
    finally { setLoading(false); }
  }, [selectedLoc]);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchData(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchData]);

  useEffect(() => {
    if (initialLocation && initialLocation !== selectedLoc) setSelectedLoc(initialLocation);
  }, [initialLocation]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium text-gray-600">Select Location:</span>
        {(locationNames || []).map((loc) => (
          <button key={loc} onClick={() => setSelectedLoc(loc)}
            className={`px-3 py-1 rounded text-sm ${selectedLoc === loc ? "bg-[var(--nichi-blue)] text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}>
            {loc.length > 20 ? loc.slice(0, 18) + ".." : loc}
          </button>
        ))}
      </div>

      {!selectedLoc && <div className="text-gray-400 text-center py-8">Select a location to see its product mix</div>}
      {loading && selectedLoc && <LoadingSpinner message="Loading product mix..." />}
      {error && <ErrorBanner message={error} onRetry={() => fetchData()} />}

      {data && !loading && (
        <>
          {data.top_brands?.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Top Brands at {data.location}</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={data.top_brands.slice(0, 10)} layout="vertical" margin={{ left: 10, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tickFormatter={(v) => fmtThb(v)} />
                  <YAxis dataKey="brand" type="category" width={120} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => fmtThb(v)} />
                  <Bar dataKey="sold_thb" name="Revenue (THB)" fill="#1a3a8f" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {data.top_items?.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-sm font-semibold text-gray-700">Top Selling Items at {data.location}</h3>
                <button onClick={() => downloadCsv(`top_items_${data.location}.csv`,
                  ["Item Code", "Item Name", "Brand", "Revenue", "Sold Qty"],
                  data.top_items.map((it) => [it.item_code, it.item_name, it.brand, it.sold_thb, it.sold_qty]))}
                  className="px-3 py-1 rounded text-xs bg-[var(--nichi-blue)] text-white hover:bg-[var(--nichi-blue-dark)]">CSV</button>
              </div>
              <SortableTable columns={[
                { key: "item_code", label: "Item Code", render: (v) => v ? <Link href={`/dashboards/item-detail/${encodeURIComponent(v)}`} className="text-[var(--nichi-blue)] hover:underline font-medium">{v}</Link> : "—" },
                { key: "item_name", label: "Item Name" },
                { key: "brand", label: "Brand" },
                { key: "sold_thb", label: "Revenue (THB)", render: (v) => fmtThb(v) },
                { key: "sold_qty", label: "Sold Qty", render: (v) => fmtQty(v) },
              ]} data={data.top_items} defaultSort="sold_thb" />
            </div>
          )}

          {data.non_movers?.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">
                Non-Moving Items <span className="ml-2 text-red-600 text-xs">{fmtThb(data.non_mover_total_thb)} at risk</span>
              </h3>
              <SortableTable columns={[
                { key: "item_code", label: "Item Code", render: (v) => v ? <Link href={`/dashboards/item-detail/${encodeURIComponent(v)}`} className="text-[var(--nichi-blue)] hover:underline font-medium">{v}</Link> : "—" },
                { key: "brand", label: "Brand" },
                { key: "onhand_qty", label: "On-Hand Qty", render: (v) => fmtQty(v) },
                { key: "onhand_thb", label: "On-Hand (THB @ Master)", render: (v) => fmtThb(v) },
              ]} data={data.non_movers} defaultSort="onhand_thb" />
            </div>
          )}

          {data.brand_heatmap?.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Brand Performance at {data.location} vs Company</h3>
              <SortableTable columns={[
                { key: "brand", label: "Brand" },
                { key: "loc_sold_thb", label: "Location Revenue", render: (v) => fmtThb(v) },
                { key: "company_sold_thb", label: "Company Revenue", render: (v) => fmtThb(v) },
                { key: "loc_share_pct", label: "Location Share %", render: (v) => fmtPct(v) },
                { key: "loc_onhand_thb", label: "On-Hand (THB @ Master)", render: (v) => fmtThb(v) },
                { key: "sell_through", label: "Sell-Through", render: (v) => fmtRatio(v) },
              ]} data={data.brand_heatmap} defaultSort="loc_sold_thb" />
            </div>
          )}
        </>
      )}
    </div>
  );
}


// ============================================================
// MAIN PAGE
// ============================================================
export default function LocationsListPage() {
  const [activeTab, setActiveTab] = useState("performance");
  const [selectedYears, setSelectedYears] = useState([CY]);
  const [locationNames, setLocationNames] = useState([]);
  const [drillLocation, setDrillLocation] = useState("");

  const toggleYear = (y) => {
    setSelectedYears((prev) => {
      if (prev.includes(y)) {
        if (prev.length === 1) return prev;
        return prev.filter((v) => v !== y);
      }
      return [...prev, y].sort((a, b) => b - a);
    });
  };

  const handleLocationDrill = (locName) => {
    // Navigate to the location detail page
    window.location.href = `/dashboards/locations/${encodeURIComponent(locName)}`;
  };

  // Fetch location names for filter buttons
  useEffect(() => {
    const ctrl = new AbortController();
    api.get("/api/location_performance", { signal: ctrl.signal })
      .then((res) => {
        if (res.data?.locations) setLocationNames(res.data.locations.map((l) => l.location));
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, []);

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  return (
    <div className="max-w-[1400px] mx-auto px-4 py-6">
      <nav className="text-sm text-gray-500 mb-4">
        <Link href="/" className="hover:underline">Home</Link>
        <span className="mx-1">/</span>
        <span className="text-gray-800 font-medium">Locations</span>
      </nav>

      <div className="mb-4">
        <h1 className="text-2xl font-bold text-[var(--nichi-blue)]">Locations</h1>
        <p className="text-sm text-gray-500 mt-1">
          Performance rankings, investment analysis, trends, and product mix for {yearLabel}.
          Revenue uses actual sales prices; on-hand valued at Master Price.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {TABS.map(({ id, label }) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === id
                ? "bg-white text-[var(--nichi-blue)] border-b-2 border-[var(--nichi-blue)]"
                : "text-gray-500 hover:text-gray-700 hover:bg-gray-100"
            }`}>
            {label}
          </button>
        ))}
      </div>

      {activeTab === "performance" && <PerformanceTab selectedYears={selectedYears} toggleYear={toggleYear} onLocationClick={handleLocationDrill} />}
      {activeTab === "investment" && <InvestmentTab selectedYears={selectedYears} toggleYear={toggleYear} />}
      {activeTab === "trends" && <TrendsTab selectedYears={selectedYears} toggleYear={toggleYear} locationNames={locationNames} />}
      {activeTab === "product-mix" && <ProductMixTab locationNames={locationNames} initialLocation={drillLocation} />}
    </div>
  );
}
