"use client";

import { useCallback, useEffect, useState } from "react";
import api, { isAbortError } from "@/utils/api";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSpinner from "@/components/LoadingSpinner";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import KpiCard from "@/components/KpiCard";
import SortableTable from "@/components/SortableTable";
import { fmtThb, fmtQty, fmtPct } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csvExport";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
  ComposedChart,
  Area,
} from "recharts";

const TABS = [
  { id: "seasonality", label: "Seasonality" },
  { id: "margin_mix", label: "Margin Mix" },
];

const YEAR_COLORS = [
  "#1a3a8f", "#FFD200", "#059669", "#dc2626", "#7c3aed",
  "#d97706", "#0891b2", "#be185d", "#4f46e5", "#65a30d",
];

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];


/* ================================================================== */
/*  TAB 1 — Seasonality Analysis                                       */
/* ================================================================== */
function SeasonalityTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dimension, setDimension] = useState("overall");
  const [filterValue, setFilterValue] = useState("");
  const [brandList, setBrandList] = useState([]);
  const [channelList, setChannelList] = useState([]);
  const [listError, setListError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    api.get("/api/get_brand_list", { signal: controller.signal })
      .then((r) => setBrandList(r.data?.brands || []))
      .catch((e) => { if (!isAbortError(e)) setListError("Could not load brand list"); });
    api.get("/api/get_channel_list", { signal: controller.signal })
      .then((r) => setChannelList(r.data?.channels || []))
      .catch((e) => { if (!isAbortError(e)) setListError("Could not load channel list"); });
    return () => controller.abort();
  }, []);

  const fetchData = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const params = { dimension };
      if ((dimension === "brand" || dimension === "channel") && filterValue) {
        params.filter_value = filterValue;
      }
      const res = await api.get("/api/seasonality_analysis", { params, signal });
      setData(res.data);
    } catch (e) {
      if (!isAbortError(e)) setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [dimension, filterValue]);

  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
    return () => controller.abort();
  }, [fetchData]);

  if (loading) return <LoadingSpinner message="Loading seasonality data..." />;
  if (error) return <ErrorBanner message={error} onRetry={() => fetchData()} className="m-6" />;
  if (!data || !data.monthly_patterns?.length) return <p className="p-6 text-gray-500">No seasonality data available.</p>;

  const { monthly_patterns, seasonal_index, current_vs_pattern, yoy_growth, summary } = data;

  // Collect all unique years
  const allYears = [];
  monthly_patterns.forEach((mp) => mp.years_data.forEach((yd) => {
    if (!allYears.includes(yd.year)) allYears.push(yd.year);
  }));
  allYears.sort();

  // Build chart data: month x year
  const monthlyChartData = monthly_patterns.map((mp) => {
    const row = { month: mp.month_name, avg: mp.avg_revenue };
    mp.years_data.forEach((yd) => { row[`y${yd.year}`] = yd.revenue; });
    return row;
  });

  // Seasonal index chart data
  const indexChartData = seasonal_index.map((si) => ({
    month: si.month_name,
    index: si.index,
  }));

  // Current vs pattern chart
  const patternChartData = current_vs_pattern.map((cv) => ({
    month: cv.month_name,
    historical: cv.historical_avg,
    current: cv.current_year,
  }));

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <label className="text-sm font-medium">Dimension:</label>
        <select
          value={dimension}
          onChange={(e) => { setDimension(e.target.value); setFilterValue(""); }}
          className="border rounded px-3 py-1.5 text-sm bg-white"
        >
          <option value="overall">Overall</option>
          <option value="brand">By Brand</option>
          <option value="channel">By Channel</option>
        </select>
        {dimension === "brand" && (
          <select value={filterValue} onChange={(e) => setFilterValue(e.target.value)} className="border rounded px-3 py-1.5 text-sm bg-white">
            <option value="">All Brands</option>
            {brandList.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        )}
        {dimension === "channel" && (
          <select value={filterValue} onChange={(e) => setFilterValue(e.target.value)} className="border rounded px-3 py-1.5 text-sm bg-white">
            <option value="">All Channels</option>
            {channelList.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
        {listError && <span className="text-amber-600 text-xs ml-2">{listError} — try refreshing</span>}
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Peak Month" value={summary.peak_month || "\u2014"} sub="Highest avg revenue" />
        <KpiCard label="Trough Month" value={summary.trough_month || "\u2014"} sub="Lowest avg revenue" />
        <KpiCard label="Seasonality Strength" value={summary.seasonality_strength + " pts"} sub="Peak\u2013trough spread" tooltip={METRIC_TOOLTIPS.seasonality.seasonality_strength} />
        <KpiCard label="Years Analyzed" value={summary.years_analyzed} sub={summary.current_year ? `Current: ${summary.current_year}` : ""} />
      </div>

      {/* Monthly revenue by year — grouped bar chart */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Monthly Revenue by Year</h3>
        <ResponsiveContainer width="100%" height={350}>
          <BarChart data={monthlyChartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Legend />
            {allYears.map((y, i) => (
              <Bar key={y} dataKey={`y${y}`} name={String(y)} fill={YEAR_COLORS[i % YEAR_COLORS.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Seasonal Index */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Seasonal Index (100 = Average Month)</h3>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={indexChartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} domain={[0, "auto"]} />
            <Tooltip formatter={(v) => v.toFixed(1)} />
            <Bar dataKey="index" name="Seasonal Index" fill="#1a3a8f">
              {indexChartData.map((d, i) => (
                <Cell key={i} fill={d.index >= 100 ? "#059669" : "#dc2626"} />
              ))}
            </Bar>
            <Line type="monotone" dataKey={() => 100} stroke="#999" strokeDasharray="5 5" dot={false} name="Average (100)" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Current Year vs Historical */}
      {patternChartData.some((d) => d.current != null) && (
        <div className="rounded-lg border p-4 bg-white">
          <h3 className="text-sm font-semibold mb-3">
            {summary.current_year} vs. Historical Average
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={patternChartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Legend />
              <Area type="monotone" dataKey="historical" name="Historical Avg" fill="#e0e7ff" stroke="#6366f1" strokeWidth={2} />
              <Line type="monotone" dataKey="current" name={String(summary.current_year)} stroke="#dc2626" strokeWidth={2} dot={{ r: 4 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* YoY Growth Table */}
      <div className="rounded-lg border p-4 bg-white">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold">Year-over-Year Growth</h3>
          <button
            onClick={() => downloadCsv(
              "yoy_growth.csv",
              ["Year", "Revenue (THB)", "Growth %"],
              yoy_growth.map((r) => [r.year, r.revenue, r.growth_pct])
            )}
            className="text-xs px-3 py-1 border rounded hover:bg-gray-50"
          >
            Export CSV
          </button>
        </div>
        <SortableTable
          columns={[
            { key: "year", label: "Year" },
            { key: "revenue", label: "Revenue (THB)", fmt: fmtThb },
            { key: "growth_pct", label: "Growth %", fmt: (v) => v != null ? (
              <span className={v >= 0 ? "text-green-600" : "text-red-600"}>{fmtPct(v)}</span>
            ) : "\u2014" },
          ]}
          data={yoy_growth}
          defaultSort="year"
          defaultDir="desc"
        />
      </div>

      {/* Monthly Patterns Table */}
      <div className="rounded-lg border p-4 bg-white">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold">Monthly Average Revenue</h3>
          <button
            onClick={() => downloadCsv(
              "monthly_patterns.csv",
              ["Month", "Avg Revenue (THB)", "Avg Quantity", "Seasonal Index"],
              monthly_patterns.map((r, i) => [r.month_name, r.avg_revenue, r.avg_qty, seasonal_index[i]?.index])
            )}
            className="text-xs px-3 py-1 border rounded hover:bg-gray-50"
          >
            Export CSV
          </button>
        </div>
        <SortableTable
          columns={[
            { key: "month_name", label: "Month" },
            { key: "avg_revenue", label: "Avg Revenue (THB)", fmt: fmtThb },
            { key: "avg_qty", label: "Avg Quantity", fmt: fmtQty },
            { key: "index", label: "Seasonal Index", tooltip: METRIC_TOOLTIPS.seasonality.seasonal_index, fmt: (v) => v != null ? (
              <span className={v >= 100 ? "text-green-600 font-medium" : "text-red-600 font-medium"}>{v.toFixed(1)}</span>
            ) : "\u2014" },
          ]}
          data={monthly_patterns.map((mp, i) => ({ ...mp, index: seasonal_index[i]?.index }))}
          defaultSort="month"
          defaultDir="asc"
        />
      </div>
    </div>
  );
}

/* ================================================================== */
/*  TAB 2 — Margin Mix Analysis                                        */
/* ================================================================== */
function MarginMixTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedYears, setSelectedYears] = useState([CY]);

  const toggleYear = (y) => {
    setSelectedYears((prev) => {
      if (prev.includes(y)) {
        if (prev.length === 1) return prev;
        return prev.filter((v) => v !== y);
      }
      return [...prev, y].sort((a, b) => b - a);
    });
  };

  const fetchData = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      selectedYears.forEach((y) => qs.append("year_list", String(y)));
      const res = await api.get(`/api/margin_mix_analysis?${qs.toString()}`, { signal });
      setData(res.data);
    } catch (e) {
      if (!isAbortError(e)) setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedYears]);

  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
    return () => controller.abort();
  }, [fetchData]);

  if (loading) return <LoadingSpinner message="Loading margin analysis..." />;
  if (error) return <ErrorBanner message={error} onRetry={() => fetchData()} className="m-6" />;
  if (!data || !data.margin_trend?.length) return <p className="p-6 text-gray-500">No GRPO data available for margin analysis.</p>;

  const { margin_trend, brand_contributions, waterfall, margin_drivers, summary } = data;

  const trendChartData = margin_trend.map((t) => ({
    period: t.period?.substring(0, 7),
    revenue: t.revenue,
    fob_cost: t.fob_cost,
    margin: t.gross_margin,
    margin_pct: t.margin_pct,
  }));

  return (
    <div className="space-y-6">
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
          >{y}</button>
        ))}
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Blended Margin" value={fmtPct(summary.blended_margin_pct)} sub="Gross margin %" tooltip={METRIC_TOOLTIPS.seasonality.blended_margin} />
        <KpiCard label="Total Revenue (THB)" value={fmtThb(summary.total_revenue)} />
        <KpiCard label="Total FOB Cost (THB)" value={fmtThb(summary.total_fob_cost)} />
        <KpiCard label="Gross Margin (THB)" value={fmtThb(summary.total_gross_margin)} sub={`Revenue − FOB Cost · ${summary.brand_count} brands`} />
      </div>

      {/* Margin trend chart */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Gross Margin % Over Time</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trendChartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} unit="%" domain={[0, "auto"]} />
            <Tooltip formatter={(v, name) => name === "margin_pct" ? fmtPct(v) : fmtThb(v)} />
            <Legend />
            <Line type="monotone" dataKey="margin_pct" name="Margin %" stroke="#059669" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Revenue vs FOB Cost */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Revenue vs. FOB Cost by Month</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={trendChartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Legend />
            <Bar dataKey="revenue" name="Revenue (actual sales)" fill="#1a3a8f" />
            <Bar dataKey="fob_cost" name="FOB Cost (import)" fill="#dc2626" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Waterfall Chart */}
      {waterfall.length > 0 && (
        <div className="rounded-lg border p-4 bg-white">
          <h3 className="text-sm font-semibold mb-3">Margin Waterfall by Brand</h3>
          <ResponsiveContainer width="100%" height={350}>
            <BarChart data={waterfall} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => (v / 1e6).toFixed(1) + "M"} />
              <YAxis type="category" dataKey="brand" tick={{ fontSize: 10 }} width={120} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Bar dataKey="margin_contribution_thb" name="Margin Contribution">
                {waterfall.map((w, i) => (
                  <Cell key={i} fill={w.margin_contribution_thb >= 0 ? "#059669" : "#dc2626"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Brand Contributions Table */}
      <div className="rounded-lg border p-4 bg-white">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold">Brand Margin Contributions</h3>
          <button
            onClick={() => downloadCsv(
              `brand_margin_contributions_${selectedYears.join("_")}.csv`,
              ["Brand", "Revenue", "FOB Cost", "Gross Margin", "Margin %", "Revenue Share %", "Margin Contribution %"],
              brand_contributions.map((r) => [r.brand, r.revenue, r.fob_cost, r.gross_margin, r.margin_pct, r.revenue_share_pct, r.margin_contribution_pct])
            )}
            className="text-xs px-3 py-1 border rounded hover:bg-gray-50"
          >
            Export CSV
          </button>
        </div>
        <SortableTable
          columns={[
            { key: "brand", label: "Brand" },
            { key: "revenue", label: "Revenue (THB)", fmt: fmtThb },
            { key: "fob_cost", label: "FOB Cost (THB)", tooltip: METRIC_TOOLTIPS.purchase.fob_cost, fmt: fmtThb },
            { key: "gross_margin", label: "Gross Margin", fmt: (v) => (
              <span className={v >= 0 ? "text-green-600" : "text-red-600"}>{fmtThb(v)}</span>
            )},
            { key: "margin_pct", label: "Margin %", fmt: (v) => (
              <span className={v >= 0 ? "text-green-600" : "text-red-600"}>{fmtPct(v)}</span>
            )},
            { key: "revenue_share_pct", label: "Rev Share %", fmt: fmtPct },
            { key: "margin_contribution_pct", label: "Margin Contrib %", tooltip: METRIC_TOOLTIPS.seasonality.margin_contribution, fmt: fmtPct },
          ]}
          data={brand_contributions}
          defaultSort="gross_margin"
        />
      </div>

      {/* Margin Drivers */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-lg border p-4 bg-white">
          <h3 className="text-sm font-semibold mb-3 text-green-700">Top Margin Contributors</h3>
          {margin_drivers.positive.length ? (
            <ul className="space-y-1 text-sm">
              {margin_drivers.positive.map((d) => (
                <li key={d.brand} className="flex justify-between">
                  <span>{d.brand}</span>
                  <span className="text-green-600 font-medium">{fmtThb(d.impact)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-gray-400">No positive contributors</p>}
        </div>
        <div className="rounded-lg border p-4 bg-white">
          <h3 className="text-sm font-semibold mb-3 text-red-700">Margin Drags</h3>
          {margin_drivers.negative.length ? (
            <ul className="space-y-1 text-sm">
              {margin_drivers.negative.map((d) => (
                <li key={d.brand} className="flex justify-between">
                  <span>{d.brand}</span>
                  <span className="text-red-600 font-medium">{fmtThb(d.impact)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-gray-400">No negative contributors</p>}
        </div>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  MAIN PAGE                                                          */
/* ================================================================== */
export default function SeasonalityMarginPage() {
  const [tab, setTab] = useState("seasonality");

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)]">
      <div className="max-w-[1400px] mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--nichi-blue)" }}>
          Seasonality & Margin Analysis
        </h1>
        <p className="text-sm text-gray-500 mb-4">
          Monthly sales patterns, seasonal trends, and brand-level margin contributions.
        </p>

        {/* Tab bar */}
        <div className="flex gap-1 mb-6 border-b">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
                tab === t.id
                  ? "border-[var(--nichi-blue)] text-[var(--nichi-blue)]"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "seasonality" && <SeasonalityTab />}
        {tab === "margin_mix" && <MarginMixTab />}
      </div>
    </div>
  );
}
