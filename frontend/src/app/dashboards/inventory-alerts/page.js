"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import api, { isAbortError } from "@/utils/api";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSpinner from "@/components/LoadingSpinner";
import SortableTable from "@/components/SortableTable";
import StatusBadge from "@/components/StatusBadge";
import ItemLink from "@/components/ItemLink";
import { fmtThb, fmtQty } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csvExport";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  PieChart,
  Pie,
} from "recharts";
const TABS = [
  { id: "stockout", label: "Stockout Risk" },
  { id: "deadstock", label: "Dead Stock" },
  { id: "reorder", label: "Reorder Analysis" },
];

const SEVERITY_COLORS = {
  critical: "#dc2626",
  warning: "#d97706",
  watch: "#2563eb",
  urgent: "#d97706",
  reorder: "#059669",
};

const SEVERITY_BG = {
  critical: "bg-red-100 text-red-800",
  warning: "bg-amber-100 text-amber-800",
  watch: "bg-blue-100 text-blue-800",
  urgent: "bg-amber-100 text-amber-800",
  reorder: "bg-green-100 text-green-800",
};

function SeverityBadge({ level }) {
  return <StatusBadge status={level} colors={SEVERITY_BG} />;
}

/* =========================================================================
   STOCKOUT RISK TAB
   ========================================================================= */

function StockoutTab({ brand }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sevFilter, setSevFilter] = useState("all");

  const loadData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    const params = { threshold_days: 30, top_n: 100 };
    if (brand) params.brand = brand;
    api.get("/api/stockout_risk", { params, signal })
      .then((r) => setData(r.data))
      .catch((e) => { if (!isAbortError(e)) setError(e.message); })
      .finally(() => setLoading(false));
  }, [brand]);

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  if (loading) return <LoadingSpinner message="Loading stockout risk data…" />;
  if (error) return <ErrorBanner message={error} onRetry={() => loadData()} className="m-8" />;
  if (!data || !data.rows) return <p className="text-center py-8 text-gray-400">No data available</p>;

  const { rows: allRows, summary } = data;

  // Apply severity filter
  const rows = sevFilter === "all" ? allRows : allRows.filter((r) => r.severity === sevFilter);

  const severityData = [
    { name: "Critical (<7d)", value: summary.critical_count, color: SEVERITY_COLORS.critical, key: "critical" },
    { name: "Warning (<14d)", value: summary.warning_count, color: SEVERITY_COLORS.warning, key: "warning" },
    { name: "Watch (<30d)", value: allRows.length - summary.critical_count - summary.warning_count, color: SEVERITY_COLORS.watch, key: "watch" },
  ].filter((d) => d.value > 0);

  const columns = [
    { key: "severity", label: "Severity", tooltip: METRIC_TOOLTIPS.inventory.severity, render: (v) => <SeverityBadge level={v} /> },
    { key: "item_code", label: "Item Code", render: (v) => <ItemLink code={v} /> },
    { key: "brand", label: "Brand" },
    { key: "description", label: "Description", render: (v) => <span className="max-w-[200px] truncate block">{v}</span> },
    { key: "onhand_qty", label: "On Hand", render: (v) => fmtQty(v) },
    { key: "avg_daily_qty", label: "Avg/Day", tooltip: METRIC_TOOLTIPS.inventory.avg_per_day, render: (v) => v?.toFixed(1) },
    { key: "weekly_rate", label: "Avg/Week", tooltip: METRIC_TOOLTIPS.inventory.avg_per_week, render: (v) => v?.toFixed(1) },
    { key: "days_cover", label: "Days Cover", tooltip: METRIC_TOOLTIPS.inventory.days_of_cover, render: (v) => <span className={v < 7 ? "text-red-600 font-bold" : v < 14 ? "text-amber-600 font-semibold" : ""}>{v?.toFixed(1)}</span> },
    { key: "projected_stockout", label: "Stockout Date", tooltip: METRIC_TOOLTIPS.inventory.projected_stockout },
    { key: "suggested_reorder_qty", label: "Reorder Qty", tooltip: METRIC_TOOLTIPS.inventory.suggested_reorder_qty, render: (v) => fmtQty(v) },
  ];

  const handleExport = () => {
    downloadCsv("stockout_risk.csv",
      ["Severity", "Item Code", "Brand", "Description", "On Hand", "Avg/Day", "Weekly Rate", "Days Cover", "Projected Stockout", "Reorder Qty"],
      rows.map((r) => [r.severity, r.item_code, r.brand, r.description, r.onhand_qty, r.avg_daily_qty, r.weekly_rate, r.days_cover, r.projected_stockout, r.suggested_reorder_qty])
    );
  };

  return (
    <div className="space-y-6">
      {/* Summary Cards — clickable to filter by severity */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <button
          onClick={() => setSevFilter(sevFilter === "critical" ? "all" : "critical")}
          className={`bg-white rounded-lg shadow p-4 border-l-4 border-red-500 text-left transition-all cursor-pointer ${sevFilter === "critical" ? "ring-2 ring-red-400 shadow-md" : "hover:shadow-md"}`}
        >
          <div className="text-sm text-gray-500">Critical (&lt;7 days)</div>
          <div className="text-2xl font-bold text-red-600">{summary.critical_count}</div>
        </button>
        <button
          onClick={() => setSevFilter(sevFilter === "warning" ? "all" : "warning")}
          className={`bg-white rounded-lg shadow p-4 border-l-4 border-amber-500 text-left transition-all cursor-pointer ${sevFilter === "warning" ? "ring-2 ring-amber-400 shadow-md" : "hover:shadow-md"}`}
        >
          <div className="text-sm text-gray-500">Warning (&lt;14 days)</div>
          <div className="text-2xl font-bold text-amber-600">{summary.warning_count}</div>
        </button>
        <button
          onClick={() => setSevFilter("all")}
          className={`bg-white rounded-lg shadow p-4 border-l-4 border-blue-500 text-left transition-all cursor-pointer ${sevFilter === "all" ? "ring-2 ring-blue-400 shadow-md" : "hover:shadow-md"}`}
        >
          <div className="text-sm text-gray-500">Total At Risk</div>
          <div className="text-2xl font-bold text-blue-700">{summary.total_at_risk_items}</div>
        </button>
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-gray-400">
          <div className="text-sm text-gray-500">At-Risk Value (@ Master Price)</div>
          <div className="text-2xl font-bold">{fmtThb(summary.total_at_risk_thb)}</div>
        </div>
      </div>
      {sevFilter !== "all" && (
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <span>Filtered: <strong>{sevFilter}</strong> ({rows.length} items)</span>
          <button onClick={() => setSevFilter("all")} className="text-xs text-gray-500 underline">Clear</button>
        </div>
      )}

      {/* Chart + Table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {severityData.length > 0 && (
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">Severity Distribution</h3>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={severityData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, value }) => `${name}: ${value}`}>
                  {severityData.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className={`bg-white rounded-lg shadow p-4 ${severityData.length > 0 ? "lg:col-span-2" : "lg:col-span-3"}`}>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Top At-Risk Items by Days Cover</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={rows.slice(0, 15)} layout="vertical" margin={{ left: 80 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" label={{ value: "Days Cover", position: "bottom", offset: -5 }} />
              <YAxis type="category" dataKey="item_code" width={75} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => v?.toFixed(1)} />
              <Bar dataKey="days_cover" name="Days Cover">
                {rows.slice(0, 15).map((r, i) => <Cell key={i} fill={SEVERITY_COLORS[r.severity]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-700">Stockout Risk Items ({rows.length})</h3>
          <button onClick={handleExport} className="px-3 py-1.5 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)] transition">
            Export CSV
          </button>
        </div>
        <SortableTable columns={columns} data={rows} defaultSort="days_cover" defaultDir="asc" />
      </div>
    </div>
  );
}

/* =========================================================================
   DEAD STOCK TAB
   ========================================================================= */

function DeadStockTab({ brand }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    const params = { window_days: 180, top_n: 100 };
    if (brand) params.brand = brand;
    api.get("/api/dead_stock", { params, signal })
      .then((r) => setData(r.data))
      .catch((e) => { if (!isAbortError(e)) setError(e.message); })
      .finally(() => setLoading(false));
  }, [brand]);

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  if (loading) return <LoadingSpinner message="Loading dead stock data…" />;
  if (error) return <ErrorBanner message={error} onRetry={() => loadData()} className="m-8" />;
  if (!data || !data.rows) return <p className="text-center py-8 text-gray-400">No data available</p>;

  const { rows, summary } = data;

  const brandData = (summary.brands || []).slice(0, 10);

  const columns = [
    { key: "category", label: "Category", render: (v) => (
      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${v === "dead" ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800"}`}>
        {v === "dead" ? "Dead" : "Slow Moving"}
      </span>
    )},
    { key: "item_code", label: "Item Code", render: (v) => <ItemLink code={v} /> },
    { key: "brand", label: "Brand" },
    { key: "description", label: "Description", render: (v) => <span className="max-w-[200px] truncate block">{v}</span> },
    { key: "onhand_qty", label: "On Hand", render: (v) => fmtQty(v) },
    { key: "onhand_thb", label: "Value (THB @ Master Price)", tooltip: METRIC_TOOLTIPS.inventory.dead_stock_value, render: (v) => fmtThb(v) },
    { key: "sold_qty_window", label: "Sold (180d)", render: (v) => fmtQty(v) },
    { key: "days_cover", label: "Days Cover", tooltip: METRIC_TOOLTIPS.inventory.days_of_cover, render: (v) => v == null ? "No sales" : v.toFixed(0) },
    { key: "still_purchasing", label: "Still Buying?", render: (v) => v ? <span className="text-red-600 font-semibold">Yes</span> : "No" },
    { key: "recommended_action", label: "Action", render: (v) => <span className="text-xs">{v}</span> },
  ];

  const handleExport = () => {
    downloadCsv("dead_stock.csv",
      ["Category", "Item Code", "Brand", "Description", "On Hand", "Value THB", "Sold 180d", "Days Cover", "Still Purchasing", "Action"],
      rows.map((r) => [r.category, r.item_code, r.brand, r.description, r.onhand_qty, r.onhand_thb, r.sold_qty_window, r.days_cover, r.still_purchasing, r.recommended_action])
    );
  };

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-red-500">
          <div className="text-sm text-gray-500">Dead Stock Items</div>
          <div className="text-2xl font-bold text-red-600">{summary.dead_stock_items}</div>
          <div className="text-xs text-gray-400 mt-1">{fmtThb(summary.dead_stock_thb)} locked (@ Master Price)</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-amber-500">
          <div className="text-sm text-gray-500">Slow Moving Items</div>
          <div className="text-2xl font-bold text-amber-600">{summary.slow_moving_items}</div>
          <div className="text-xs text-gray-400 mt-1">{fmtThb(summary.slow_moving_thb)} at risk (@ Master Price)</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-purple-500">
          <div className="text-sm text-gray-500">Total Capital at Risk (@ Master Price)</div>
          <div className="text-2xl font-bold text-purple-700">{fmtThb(summary.total_capital_at_risk)}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-orange-500">
          <div className="text-sm text-gray-500">Still Being Purchased</div>
          <div className="text-2xl font-bold text-orange-600">{summary.still_purchasing_count}</div>
          <div className="text-xs text-red-500 mt-1">Stop buying these!</div>
        </div>
      </div>

      {/* Brand chart */}
      {brandData.length > 0 && (
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Capital at Risk by Brand (Top 10)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={brandData} margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="brand" tick={{ fontSize: 11 }} angle={-30} textAnchor="end" height={60} />
              <YAxis tickFormatter={(v) => (v / 1000).toFixed(0) + "K"} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Bar dataKey="total_onhand_thb" name="On-Hand Value (@ Master Price)" fill="#dc2626" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-700">Dead & Slow-Moving Stock ({rows.length} items)</h3>
          <button onClick={handleExport} className="px-3 py-1.5 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)] transition">
            Export CSV
          </button>
        </div>
        <SortableTable columns={columns} data={rows} defaultSort="onhand_thb" defaultDir="desc" />
      </div>
    </div>
  );
}

/* =========================================================================
   REORDER ANALYSIS TAB
   ========================================================================= */

function ReorderTab({ brand }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    const params = { window_days: 90, lead_time_days: 28, target_cover_days: 56, top_n: 100 };
    if (brand) params.brand = brand;
    api.get("/api/reorder_analysis", { params, signal })
      .then((r) => setData(r.data))
      .catch((e) => { if (!isAbortError(e)) setError(e.message); })
      .finally(() => setLoading(false));
  }, [brand]);

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  if (loading) return <LoadingSpinner message="Loading reorder analysis…" />;
  if (error) return <ErrorBanner message={error} onRetry={() => loadData()} className="m-8" />;
  if (!data || !data.rows) return <p className="text-center py-8 text-gray-400">No data available</p>;

  const { rows, summary } = data;

  const columns = [
    { key: "urgency", label: "Urgency", render: (v) => <SeverityBadge level={v} /> },
    { key: "item_code", label: "Item Code", render: (v) => <ItemLink code={v} /> },
    { key: "brand", label: "Brand" },
    { key: "description", label: "Description", render: (v) => <span className="max-w-[200px] truncate block">{v}</span> },
    { key: "onhand_qty", label: "On Hand", render: (v) => fmtQty(v) },
    { key: "avg_daily_qty", label: "Avg/Day", tooltip: METRIC_TOOLTIPS.inventory.avg_per_day, render: (v) => v?.toFixed(1) },
    { key: "days_cover", label: "Days Cover", tooltip: METRIC_TOOLTIPS.inventory.days_of_cover, render: (v) => <span className={v < 7 ? "text-red-600 font-bold" : v < 14 ? "text-amber-600 font-semibold" : ""}>{v?.toFixed(1)}</span> },
    { key: "reorder_point", label: "Reorder Point", tooltip: METRIC_TOOLTIPS.inventory.reorder_point, render: (v) => fmtQty(v) },
    { key: "suggested_order_qty", label: "Order Qty", tooltip: METRIC_TOOLTIPS.inventory.suggested_reorder_qty, render: (v) => <span className="font-semibold text-green-700">{fmtQty(v)}</span> },
    { key: "suggested_order_thb", label: "Order Value (FOB)", render: (v) => fmtThb(v) },
    { key: "last_purchase_date", label: "Last Purchase", render: (v) => v || "\u2014" },
    { key: "last_fob_thb_unit", label: "Last FOB/Unit", tooltip: METRIC_TOOLTIPS.purchase.fob_cost, render: (v) => v != null ? fmtThb(v) : "\u2014" },
  ];

  const handleExport = () => {
    downloadCsv("reorder_analysis.csv",
      ["Urgency", "Item Code", "Brand", "Description", "On Hand", "Avg/Day", "Days Cover", "Reorder Point", "Order Qty", "Order Value THB", "Last Purchase", "Last FOB/Unit"],
      rows.map((r) => [r.urgency, r.item_code, r.brand, r.description, r.onhand_qty, r.avg_daily_qty, r.days_cover, r.reorder_point, r.suggested_order_qty, r.suggested_order_thb, r.last_purchase_date, r.last_fob_thb_unit])
    );
  };

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-red-500">
          <div className="text-sm text-gray-500">Critical (&lt;7 days)</div>
          <div className="text-2xl font-bold text-red-600">{summary.critical_count}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-amber-500">
          <div className="text-sm text-gray-500">Urgent (&lt;14 days)</div>
          <div className="text-2xl font-bold text-amber-600">{summary.urgent_count}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-blue-500">
          <div className="text-sm text-gray-500">Items Need Reorder</div>
          <div className="text-2xl font-bold text-blue-700">{summary.total_items_need_reorder}</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4 border-l-4 border-green-500">
          <div className="text-sm text-gray-500">Total Order Budget (FOB)</div>
          <div className="text-2xl font-bold text-green-700">{fmtThb(summary.total_suggested_order_thb)}</div>
        </div>
      </div>

      {/* Top items chart */}
      {rows.length > 0 && (
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Top Items to Reorder (by suggested order value)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={[...rows].sort((a, b) => b.suggested_order_thb - a.suggested_order_thb).slice(0, 15)} margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="item_code" tick={{ fontSize: 11 }} angle={-30} textAnchor="end" height={60} />
              <YAxis tickFormatter={(v) => (v / 1000).toFixed(0) + "K"} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Bar dataKey="suggested_order_thb" name="Order Value (THB)" radius={[4, 4, 0, 0]}>
                {[...rows].sort((a, b) => b.suggested_order_thb - a.suggested_order_thb).slice(0, 15).map((r, i) => (
                  <Cell key={i} fill={SEVERITY_COLORS[r.urgency] || "#059669"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-700">Reorder List ({rows.length} items)</h3>
          <button onClick={handleExport} className="px-3 py-1.5 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)] transition">
            Export CSV
          </button>
        </div>
        <SortableTable columns={columns} data={rows} defaultSort="days_cover" defaultDir="asc" />
      </div>
    </div>
  );
}

/* =========================================================================
   MAIN PAGE
   ========================================================================= */

export default function InventoryAlertsPage() {
  const searchParams = useSearchParams();
  const urlTab = searchParams.get("tab");
  const urlBrand = searchParams.get("brand");

  const [activeTab, setActiveTab] = useState(
    ["stockout", "deadstock", "reorder"].includes(urlTab) ? urlTab : "stockout"
  );
  const [brandInput, setBrandInput] = useState(urlBrand || "");
  const [brandFilter, setBrandFilter] = useState(urlBrand || "");

  const applyBrand = () => setBrandFilter(brandInput);
  const clearBrand = () => { setBrandInput(""); setBrandFilter(""); };

  return (
    <main className="min-h-screen bg-[var(--nichi-gray-50)] p-4 sm:p-6">
        <div className="max-w-[1600px] mx-auto">
          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-[var(--nichi-blue-dark)]">Inventory Action Alerts</h1>
            <p className="text-sm text-gray-500 mt-1">
              Stockout risk, dead stock identification, and reorder recommendations
            </p>
          </div>

          {/* Brand filter */}
          <div className="flex items-center gap-2 mb-4">
            <input
              type="text"
              placeholder="Filter by brand name..."
              value={brandInput}
              onChange={(e) => setBrandInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyBrand()}
              className={`border rounded px-3 py-1.5 text-sm w-64 ${brandFilter ? "bg-yellow-50 border-yellow-400" : ""}`}
            />
            <button
              onClick={applyBrand}
              className="bg-[var(--nichi-blue)] text-white text-sm px-4 py-1.5 rounded hover:bg-[var(--nichi-blue-dark)] transition"
            >
              Apply
            </button>
            {brandFilter && (
              <button onClick={clearBrand} className="text-sm text-gray-500 underline">
                Clear
              </button>
            )}
            {brandFilter && (
              <span className="text-sm text-gray-600">
                Showing results for: <strong>{brandFilter}</strong>
              </span>
            )}
          </div>

          {/* Tab bar */}
          <div className="flex gap-1 bg-white rounded-lg shadow p-1 mb-6">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  activeTab === tab.id
                    ? "bg-[var(--nichi-blue)] text-white shadow-sm"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === "stockout" && <StockoutTab brand={brandFilter} />}
          {activeTab === "deadstock" && <DeadStockTab brand={brandFilter} />}
          {activeTab === "reorder" && <ReorderTab brand={brandFilter} />}
        </div>
      </main>
  );
}
