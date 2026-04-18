"use client";

import { useCallback, useEffect, useState } from "react";
import api, { isAbortError } from "@/utils/api";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSpinner from "@/components/LoadingSpinner";
import SortableTable from "@/components/SortableTable";
import { fmtThb, fmtQty, fmtPct } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csvExport";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

const PERIOD_COLORS = ["#1a3a8f", "#FFD200", "#e74c3c", "#2ecc71"];
const PERIOD_BORDER_COLORS = ["#1a3a8f", "#b8960a", "#c0392b", "#27ae60"];
const PERIOD_LABELS = ["Period A", "Period B", "Period C", "Period D"];

function ChangeIndicator({ change }) {
  if (!change) return null;
  const { absolute, pct, direction } = change;
  const color = direction === "up" ? "text-green-600" : direction === "down" ? "text-red-600" : "text-gray-500";
  const arrow = direction === "up" ? "\u25B2" : direction === "down" ? "\u25BC" : "\u2014";
  return (
    <span className={`${color} text-sm font-medium`}>
      {arrow} {pct != null ? `${pct > 0 ? "+" : ""}${pct}%` : ""} ({fmtThb(absolute)})
    </span>
  );
}

function ChangeIndicatorQty({ change }) {
  if (!change) return null;
  const { absolute, pct, direction } = change;
  const color = direction === "up" ? "text-green-600" : direction === "down" ? "text-red-600" : "text-gray-500";
  const arrow = direction === "up" ? "\u25B2" : direction === "down" ? "\u25BC" : "\u2014";
  return (
    <span className={`${color} text-sm font-medium`}>
      {arrow} {pct != null ? `${pct > 0 ? "+" : ""}${pct}%` : ""} ({fmtQty(absolute)})
    </span>
  );
}

const currentYear = new Date().getFullYear();
const YEARS = Array.from({ length: 6 }, (_, i) => currentYear - i);
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function makePeriod(year, granularity, quarter, month) {
  const p = { year };
  if (granularity === "quarter") p.quarter = quarter;
  if (granularity === "month") p.month = month;
  return p;
}

function PeriodSelector({ index, period, onChange, onRemove, canRemove }) {
  const { year, granularity, quarter, month } = period;
  const borderColor = PERIOD_BORDER_COLORS[index] || "#999";
  const label = PERIOD_LABELS[index] || `Period ${index + 1}`;

  return (
    <div className="bg-white rounded-xl shadow p-4 border-l-4 relative" style={{ borderLeftColor: borderColor }}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-sm" style={{ color: borderColor }}>{label}</h3>
        {canRemove && (
          <button onClick={onRemove} className="text-gray-400 hover:text-red-500 text-lg leading-none" title="Remove period">&times;</button>
        )}
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <select value={year} onChange={(e) => onChange({ ...period, year: +e.target.value })} className="border rounded px-3 py-1.5 text-sm bg-white">
          {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <select value={granularity} onChange={(e) => onChange({ ...period, granularity: e.target.value })} className="border rounded px-3 py-1.5 text-sm bg-white">
          <option value="year">Full Year</option>
          <option value="quarter">Quarter</option>
          <option value="month">Month</option>
        </select>
        {granularity === "quarter" && (
          <select value={quarter} onChange={(e) => onChange({ ...period, quarter: +e.target.value })} className="border rounded px-3 py-1.5 text-sm bg-white">
            {[1, 2, 3, 4].map((q) => <option key={q} value={q}>Q{q}</option>)}
          </select>
        )}
        {granularity === "month" && (
          <select value={month} onChange={(e) => onChange({ ...period, month: +e.target.value })} className="border rounded px-3 py-1.5 text-sm bg-white">
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>{new Date(2000, m - 1).toLocaleString("default", { month: "short" })}</option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}

export default function PeriodComparisonPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");

  const [periods, setPeriods] = useState([
    { year: currentYear, granularity: "year", quarter: 1, month: 1 },
    { year: currentYear - 1, granularity: "year", quarter: 1, month: 1 },
  ]);

  const updatePeriod = (index, newVal) => {
    setPeriods((prev) => prev.map((p, i) => (i === index ? newVal : p)));
  };

  const addPeriod = () => {
    if (periods.length >= 4) return;
    const lastYear = periods[periods.length - 1]?.year || currentYear;
    setPeriods((prev) => [...prev, { year: lastYear - 1, granularity: prev[0].granularity, quarter: prev[0].quarter, month: prev[0].month }]);
  };

  const removePeriod = (index) => {
    if (periods.length <= 2) return;
    setPeriods((prev) => prev.filter((_, i) => i !== index));
  };

  const fetchData = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const body = {
        periods: periods.map((p) => makePeriod(p.year, p.granularity, p.quarter, p.month)),
      };
      const res = await api.post("/api/period_comparison_multi", body, { signal });
      setData(res.data);
    } catch (err) {
      if (isAbortError(err)) return;
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  }, [periods]);

  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
    return () => controller.abort();
  }, [fetchData]);

  const TABS = [
    { id: "overview", label: "Overview" },
    { id: "brands", label: "Brand Comparison" },
    { id: "channels", label: "Channel Comparison" },
  ];

  return (
    <main className="max-w-[1400px] mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold text-[var(--nichi-blue)] mb-4">Period Comparison</h1>

      {/* Period Selectors */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {periods.map((p, i) => (
          <PeriodSelector
            key={i}
            index={i}
            period={p}
            onChange={(v) => updatePeriod(i, v)}
            onRemove={() => removePeriod(i)}
            canRemove={periods.length > 2}
          />
        ))}
      </div>

      {periods.length < 4 ? (
        <button
          onClick={addPeriod}
          className="mb-6 px-4 py-2 text-sm font-medium border-2 border-dashed border-gray-300 text-gray-500 rounded-xl hover:border-[var(--nichi-blue)] hover:text-[var(--nichi-blue)] transition"
        >
          + Add Period (up to 4)
        </button>
      ) : (
        <p className="mb-6 text-xs text-gray-400">Maximum 4 periods reached</p>
      )}

      {loading && <LoadingSpinner message="Loading comparison..." />}
      {error && <ErrorBanner message={error} onRetry={() => fetchData()} />}

      {data && !loading && (
        <>
          {/* Tabs */}
          <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition ${
                  activeTab === t.id
                    ? "bg-[var(--nichi-blue)] text-white shadow"
                    : "text-gray-600 hover:bg-gray-200"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {activeTab === "overview" && <OverviewTab data={data} />}
          {activeTab === "brands" && <BrandTab data={data} />}
          {activeTab === "channels" && <ChannelTab data={data} />}
        </>
      )}
    </main>
  );
}

/* ---------- KPI Card for N periods ---------- */
function KpiCard({ label, values, labels, change, formatter = fmtThb, tooltip }) {
  return (
    <div className="bg-white rounded-xl shadow p-4">
      <div className="text-xs text-gray-500 font-medium mb-2">{label}{tooltip && <InfoTooltip text={tooltip} size="md" />}</div>
      <div className={`grid gap-2 mb-2`} style={{ gridTemplateColumns: `repeat(${values.length}, 1fr)` }}>
        {values.map((v, i) => (
          <div key={i}>
            <div className="text-[10px] font-semibold uppercase" style={{ color: PERIOD_BORDER_COLORS[i] }}>{labels[i]}</div>
            <div className="text-base font-bold text-gray-900">{formatter(v)}</div>
          </div>
        ))}
      </div>
      <div className="border-t pt-2">
        <span className="text-xs text-gray-400 mr-1">First vs Last:</span>
        {formatter === fmtThb ? <ChangeIndicator change={change} /> : <ChangeIndicatorQty change={change} />}
      </div>
    </div>
  );
}

/* ---------- Overview Tab ---------- */
function OverviewTab({ data }) {
  const { periods: kpis, labels, changes } = data;

  const kpiDefs = [
    { key: "revenue_thb", label: "Revenue (THB)", fmt: fmtThb, changeKey: "revenue_thb" },
    { key: "sold_qty", label: "Units Sold", fmt: fmtQty, changeKey: "sold_qty" },
    { key: "purchased_thb", label: "Purchases (FOB)", fmt: fmtThb, changeKey: "purchased_thb" },
    { key: "gross_margin_thb", label: "Gross Margin (THB)", fmt: fmtThb, changeKey: "gross_margin_thb", tooltip: METRIC_TOOLTIPS.period?.gross_margin_pct },
    { key: "transaction_count", label: "Transactions", fmt: fmtQty, changeKey: "transaction_count" },
    { key: "unique_items_sold", label: "Unique Items Sold", fmt: fmtQty, changeKey: "unique_items_sold" },
  ];

  // Monthly chart data
  const chartData = [];
  const maxMonths = Math.max(...kpis.map((k) => (k.monthly || []).length));
  for (let i = 0; i < maxMonths; i++) {
    const point = { month: MONTH_NAMES[i] || `M${i + 1}` };
    kpis.forEach((k, pi) => {
      point[labels[pi]] = (k.monthly || [])[i]?.revenue_thb || 0;
    });
    chartData.push(point);
  }

  return (
    <div>
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
        {kpiDefs.map((d) => (
          <KpiCard
            key={d.key}
            label={d.label}
            values={kpis.map((k) => k[d.key])}
            labels={labels}
            change={changes[d.changeKey]}
            formatter={d.fmt}
            tooltip={d.tooltip}
          />
        ))}
      </div>

      {/* Margin % side by side */}
      <div className="grid gap-4 mb-6" style={{ gridTemplateColumns: `repeat(${kpis.length}, 1fr)` }}>
        {kpis.map((k, i) => (
          <div key={i} className="bg-white rounded-xl shadow p-4 text-center">
            <div className="text-xs text-gray-500 mb-1">Gross Margin % ({labels[i]})</div>
            <div className="text-2xl font-bold" style={{ color: PERIOD_BORDER_COLORS[i] }}>{fmtPct(k.gross_margin_pct)}</div>
          </div>
        ))}
      </div>

      {/* Overview CSV Export */}
      <div className="flex justify-end mb-4">
        <button
          className="px-3 py-1 text-xs font-medium bg-gray-100 hover:bg-gray-200 text-gray-700 rounded transition"
          onClick={() => {
            const headers = ["Metric", ...labels];
            const rows = kpiDefs.map((d) => [d.label, ...kpis.map((k) => k[d.key] ?? "")]);
            rows.push(["Gross Margin %", ...kpis.map((k) => k.gross_margin_pct ?? "")]);
            downloadCsv("overview_comparison.csv", headers, rows);
          }}
        >
          Download CSV
        </button>
      </div>

      {/* Monthly Revenue Chart */}
      {chartData.length > 0 && (
        <div className="bg-white rounded-xl shadow p-4 mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Monthly Revenue Comparison</h3>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Legend />
              {labels.map((lbl, i) => (
                <Bar key={lbl} dataKey={lbl} fill={PERIOD_COLORS[i]} radius={[3, 3, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

/* ---------- Brand Tab ---------- */
function BrandTab({ data }) {
  const { brand_comparison, labels } = data;

  const columns = [
    { key: "brand", label: "Brand" },
    ...labels.map((lbl, i) => ({
      key: `rev_${i}`,
      label: `Revenue (${lbl})`,
      fmt: fmtThb,
    })),
    { key: "change_abs", label: "Change (First vs Last)", fmt: fmtThb },
    {
      key: "change_pct",
      label: "Change %",
      tooltip: METRIC_TOOLTIPS.period?.change_pct,
      render: (v, row) => {
        const dir = row._change?.direction;
        const color = dir === "up" ? "text-green-600" : dir === "down" ? "text-red-600" : "text-gray-500";
        return <span className={color}>{v != null ? `${v > 0 ? "+" : ""}${v}%` : "\u2014"}</span>;
      },
    },
  ];

  const tableData = (brand_comparison || []).map((b) => {
    const row = {
      brand: b.brand,
      change_abs: b.change?.absolute || 0,
      change_pct: b.change?.pct,
      _change: b.change,
    };
    (b.revenues || []).forEach((r, i) => { row[`rev_${i}`] = r; });
    return row;
  });

  // Chart: top 10 by absolute change
  const chartData = [...tableData]
    .sort((a, b) => Math.abs(b.change_abs) - Math.abs(a.change_abs))
    .slice(0, 10)
    .map((b) => {
      const point = { brand: b.brand.length > 15 ? b.brand.slice(0, 15) + "..." : b.brand };
      labels.forEach((lbl, i) => { point[lbl] = b[`rev_${i}`] || 0; });
      return point;
    });

  return (
    <div>
      <div className="bg-white rounded-xl shadow p-4 mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Top Brands by Revenue Change</h3>
        <ResponsiveContainer width="100%" height={350}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 100 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} tick={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="brand" tick={{ fontSize: 11 }} width={100} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Legend />
            {labels.map((lbl, i) => (
              <Bar key={lbl} dataKey={lbl} fill={PERIOD_COLORS[i]} radius={[0, 3, 3, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white rounded-xl shadow p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700">All Brands</h3>
          <button
            onClick={() =>
              downloadCsv(
                "brand_comparison.csv",
                ["Brand", ...labels.map((l) => `Revenue ${l}`), "Change THB", "Change %"],
                tableData.map((r) => [r.brand, ...labels.map((_, i) => r[`rev_${i}`]), r.change_abs, r.change_pct])
              )
            }
            className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded"
          >
            Download CSV
          </button>
        </div>
        <SortableTable columns={columns} data={tableData} defaultSort="change_abs" />
      </div>
    </div>
  );
}

/* ---------- Channel Tab ---------- */
function ChannelTab({ data }) {
  const { channel_comparison, labels } = data;

  const columns = [
    { key: "channel", label: "Channel" },
    ...labels.map((lbl, i) => ({
      key: `rev_${i}`,
      label: `Revenue (${lbl})`,
      fmt: fmtThb,
    })),
    { key: "change_abs", label: "Change (First vs Last)", fmt: fmtThb },
    {
      key: "change_pct",
      label: "Change %",
      render: (v, row) => {
        const dir = row._change?.direction;
        const color = dir === "up" ? "text-green-600" : dir === "down" ? "text-red-600" : "text-gray-500";
        return <span className={color}>{v != null ? `${v > 0 ? "+" : ""}${v}%` : "\u2014"}</span>;
      },
    },
    ...labels.map((lbl, i) => ({
      key: `qty_${i}`,
      label: `Qty (${lbl})`,
      fmt: fmtQty,
    })),
  ];

  const tableData = (channel_comparison || []).map((c) => {
    const row = {
      channel: c.channel,
      change_abs: c.change?.absolute || 0,
      change_pct: c.change?.pct,
      _change: c.change,
    };
    (c.revenues || []).forEach((r, i) => { row[`rev_${i}`] = r; });
    (c.qtys || []).forEach((q, i) => { row[`qty_${i}`] = q; });
    return row;
  });

  const chartData = tableData.map((c) => {
    const point = { channel: c.channel.length > 20 ? c.channel.slice(0, 20) + "..." : c.channel };
    labels.forEach((lbl, i) => { point[lbl] = c[`rev_${i}`] || 0; });
    return point;
  });

  return (
    <div>
      <div className="bg-white rounded-xl shadow p-4 mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Channel Revenue Comparison</h3>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="channel" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
            <YAxis tickFormatter={(v) => `${(v / 1e6).toFixed(1)}M`} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Legend />
            {labels.map((lbl, i) => (
              <Bar key={lbl} dataKey={lbl} fill={PERIOD_COLORS[i]} radius={[3, 3, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white rounded-xl shadow p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700">All Channels</h3>
          <button
            onClick={() =>
              downloadCsv(
                "channel_comparison.csv",
                ["Channel", ...labels.map((l) => `Revenue ${l}`), "Change THB", "Change %", ...labels.map((l) => `Qty ${l}`)],
                tableData.map((r) => [r.channel, ...labels.map((_, i) => r[`rev_${i}`]), r.change_abs, r.change_pct, ...labels.map((_, i) => r[`qty_${i}`])])
              )
            }
            className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded"
          >
            Download CSV
          </button>
        </div>
        <SortableTable columns={columns} data={tableData} defaultSort="change_abs" />
      </div>
    </div>
  );
}
