"use client";

import { useCallback, useEffect, useState } from "react";
import api, { isAbortError } from "@/utils/api";
import ErrorBanner from "@/components/ErrorBanner";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import KpiCard from "@/components/KpiCard";
import SortableTable from "@/components/SortableTable";
import { fmtThb, fmtThbShort, fmtQty, fmtPct, fmtRatio as _fmtRatio } from "@/utils/formatters";
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
  PieChart,
  Pie,
} from "recharts";

const TABS = [
  { id: "cost_trends", label: "Cost Trends" },
  { id: "purchase_vs_sold", label: "Purchase vs. Sold" },
  { id: "working_capital", label: "Working Capital" },
];

const BRAND_COLORS = [
  "#1a3a8f", "#FFD200", "#059669", "#dc2626", "#7c3aed",
  "#d97706", "#0891b2", "#be185d", "#4f46e5", "#65a30d",
  "#9333ea", "#e11d48", "#0d9488", "#ca8a04", "#6366f1",
];

const fmtRatio = (n) => _fmtRatio(n, "x");

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

/* ================================================================== */
/*  TAB 1 — Cost Trends                                                */
/* ================================================================== */
function CostTrendsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedBrand, setSelectedBrand] = useState(null);
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

  const fetchCostTrends = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      selectedYears.forEach((y) => qs.append("year_list", String(y)));
      const res = await api.get(`/api/purchase_cost_trends?${qs.toString()}`, { signal });
      setData(res.data);
    } catch (e) {
      if (isAbortError(e)) return;
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedYears]);

  useEffect(() => {
    const controller = new AbortController();
    fetchCostTrends(controller.signal);
    return () => controller.abort();
  }, [fetchCostTrends]);

  const yearLabel = selectedYears.join(", ");

  if (loading) return <p className="p-6 text-gray-500">Loading cost trends...</p>;
  if (error) return <ErrorBanner message={error} onRetry={() => fetchCostTrends()} className="m-6" />;
  if (!data || !data.overall_trend?.length) return <p className="p-6 text-gray-500">No GRPO purchase data available.</p>;

  const { overall_trend, brand_trends, currency_impact, summary } = data;

  const chartData = overall_trend.map((p) => ({
    period: p.period.substring(0, 7),
    avg_fob: p.avg_fob_thb,
    total_thb: p.total_fob_thb,
    qty: p.total_qty,
  }));

  const brandChartData = selectedBrand
    ? (brand_trends.find((b) => b.brand === selectedBrand)?.periods || []).map((p) => ({
        period: p.period.substring(0, 7),
        avg_fob: p.avg_fob_thb,
        total_thb: p.total_fob_thb,
      }))
    : [];

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
        <KpiCard label="Total Purchased" value={fmtThb(summary.total_purchased_thb)} sub="FOB cost (THB)" />
        <KpiCard label="Brands" value={summary.unique_brands} sub="with purchase records" />
        <KpiCard label="Items" value={fmtQty(summary.unique_items)} sub="unique items purchased" />
        <KpiCard label="Periods" value={summary.period_count} sub="months of data" />
      </div>

      {/* Overall FOB trend chart */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Average FOB Cost per Unit (THB) — All Brands</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Line type="monotone" dataKey="avg_fob" stroke="#1a3a8f" strokeWidth={2} dot={{ r: 3 }} name="Avg FOB/unit" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Monthly purchase volume chart */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Monthly Purchase Volume (THB)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Bar dataKey="total_thb" fill="#1a3a8f" name="Total FOB (THB)" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Brand filter + brand-specific trend */}
      <div className="rounded-lg border p-4 bg-white">
        <div className="flex items-center gap-3 mb-3">
          <h3 className="text-sm font-semibold">{selectedBrand ? `Cost Trend: ${selectedBrand}` : "Brand Cost Trend"}</h3>
          <select
            className="border rounded px-3 py-1.5 text-sm bg-white"
            value={selectedBrand || ""}
            onChange={(e) => setSelectedBrand(e.target.value || null)}
          >
            <option value="">Select a brand...</option>
            {brand_trends.map((b) => (
              <option key={b.brand} value={b.brand}>{b.brand} ({fmtThbShort(b.total_spend_thb)})</option>
            ))}
          </select>
        </div>
        {selectedBrand && brandChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={brandChartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Line type="monotone" dataKey="avg_fob" stroke="#059669" strokeWidth={2} dot={{ r: 3 }} name="Avg FOB/unit" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-gray-400 text-sm">Select a brand to view its cost trend.</p>
        )}
      </div>

      {/* Currency impact */}
      {currency_impact.length > 0 && (
        <div className="rounded-lg border p-4 bg-white">
          <h3 className="text-sm font-semibold mb-3">Currency Mix</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={currency_impact}
                  dataKey="total_fob_thb"
                  nameKey="currency"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={({ currency, share_pct }) => `${currency} ${share_pct}%`}
                >
                  {currency_impact.map((_, i) => (
                    <Cell key={i} fill={BRAND_COLORS[i % BRAND_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => fmtThb(v)} />
              </PieChart>
            </ResponsiveContainer>
            <SortableTable
              columns={[
                { key: "currency", label: "Currency", fmt: String },
                { key: "total_qty", label: "Qty", fmt: fmtQty },
                { key: "avg_rate", label: "Avg Rate", fmt: (v) => v?.toFixed(2) },
                { key: "total_fob_thb", label: "Total (THB)", fmt: fmtThb },
                { key: "share_pct", label: "Share", fmt: fmtPct },
              ]}
              data={currency_impact}
              defaultSort="total_fob_thb"
            />
          </div>
        </div>
      )}

      {/* Brand spend table with CSV */}
      <div className="rounded-lg border p-4 bg-white">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Top Brands by Purchase Spend</h3>
          <button
            className="text-xs px-3 py-1 rounded border hover:bg-gray-50"
            onClick={() => downloadCsv(
              `purchase_cost_brands_${selectedYears.join("_")}.csv`,
              ["Brand", "Total Spend FOB (THB)"],
              brand_trends.map((b) => [b.brand, b.total_spend_thb]),
            )}
          >
            CSV
          </button>
        </div>
        <SortableTable
          columns={[
            { key: "brand", label: "Brand", fmt: String },
            { key: "total_spend_thb", label: "Total Spend FOB (THB)", fmt: fmtThb },
            { key: "periods_count", label: "Active Months", fmt: fmtQty },
          ]}
          data={brand_trends.map((b) => ({ ...b, periods_count: b.periods.length }))}
          defaultSort="total_spend_thb"
        />
      </div>
    </div>
  );
}

/* ================================================================== */
/*  TAB 2 — Purchase vs. Sold                                          */
/* ================================================================== */
function PurchaseVsSoldTab() {
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

  const fetchPvs = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      selectedYears.forEach((y) => qs.append("year_list", String(y)));
      const res = await api.get(`/api/purchase_vs_sold?${qs.toString()}`, { signal });
      setData(res.data);
    } catch (e) {
      if (isAbortError(e)) return;
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [selectedYears]);

  useEffect(() => {
    const controller = new AbortController();
    fetchPvs(controller.signal);
    return () => controller.abort();
  }, [fetchPvs]);

  if (loading) return <p className="p-6 text-gray-500">Loading purchase vs sold data...</p>;
  if (error) return <ErrorBanner message={error} onRetry={() => fetchPvs()} className="m-6" />;
  if (!data || !data.brands?.length) return <p className="p-6 text-gray-500">No purchase/sold data available.</p>;

  const { brands, summary } = data;

  const chartData = brands.slice(0, 15).map((b) => ({
    brand: b.brand.length > 15 ? b.brand.substring(0, 15) + "..." : b.brand,
    purchased: b.purchased_thb,
    sold: b.sold_thb,
  }));

  const buildUpBrands = brands.filter((b) => b.inventory_build_up);
  const drawDownBrands = brands.filter((b) => !b.inventory_build_up);

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
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KpiCard label="Total Purchased" value={fmtThb(summary.total_purchased_thb)} sub="FOB cost" />
        <KpiCard label="Total Sold" value={fmtThb(summary.total_sold_thb)} sub="Revenue" />
        <KpiCard label="P/S Ratio" value={fmtRatio(summary.overall_ratio)} sub={summary.overall_ratio > 1 ? "Buying > Selling" : "Selling > Buying"} />
        <KpiCard label="Building Up" value={summary.build_up_brands} sub="brands overstocking" />
        <KpiCard label="Drawing Down" value={summary.draw_down_brands} sub="brands selling through" />
      </div>

      {/* Comparison bar chart */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Purchased vs. Sold by Brand (Top 15)</h3>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => (v / 1000000).toFixed(1) + "M"} />
            <YAxis dataKey="brand" type="category" width={130} tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Legend />
            <Bar dataKey="purchased" fill="#dc2626" name="Purchased (FOB)" />
            <Bar dataKey="sold" fill="#059669" name="Sold (Revenue)" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Build-up warning */}
      {buildUpBrands.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="text-sm font-semibold text-amber-800 mb-2">
            Inventory Build-Up Warning ({buildUpBrands.length} brands buying more than selling)
          </h3>
          <div className="overflow-x-auto">
            <SortableTable
              columns={[
                { key: "brand", label: "Brand", fmt: String },
                { key: "purchased_thb", label: "Purchased FOB (THB)", fmt: fmtThb },
                { key: "sold_thb", label: "Sold Revenue (THB)", fmt: fmtThb },
                { key: "purchase_sold_ratio", label: "P/S Ratio", tooltip: METRIC_TOOLTIPS.purchase.ps_ratio, fmt: fmtRatio },
                { key: "onhand_thb", label: "On-Hand (THB @ Master Price)", fmt: fmtThb },
              ]}
              data={buildUpBrands}
              defaultSort="purchase_sold_ratio"
            />
          </div>
        </div>
      )}

      {/* Full table with CSV */}
      <div className="rounded-lg border p-4 bg-white">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">All Brands — Purchase vs. Sold Detail</h3>
          <button
            className="text-xs px-3 py-1 rounded border hover:bg-gray-50"
            onClick={() => downloadCsv(
              `purchase_vs_sold_${selectedYears.join("_")}.csv`,
              ["Brand", "Purchased Qty", "Purchased FOB (THB)", "Sold Qty", "Sold Revenue (THB)", "P/S Ratio", "Build-Up", "On-Hand Qty", "On-Hand (THB @ Master Price)"],
              brands.map((b) => [b.brand, b.purchased_qty, b.purchased_thb, b.sold_qty, b.sold_thb, b.purchase_sold_ratio, b.inventory_build_up, b.onhand_qty, b.onhand_thb]),
            )}
          >
            CSV
          </button>
        </div>
        <SortableTable
          columns={[
            { key: "brand", label: "Brand", fmt: String },
            { key: "purchased_qty", label: "Purch Qty", fmt: fmtQty },
            { key: "purchased_thb", label: "Purch FOB (THB)", fmt: fmtThb },
            { key: "sold_qty", label: "Sold Qty", fmt: fmtQty },
            { key: "sold_thb", label: "Sold Revenue (THB)", fmt: fmtThb },
            { key: "purchase_sold_ratio", label: "P/S Ratio", tooltip: METRIC_TOOLTIPS.purchase.ps_ratio, fmt: fmtRatio },
            { key: "onhand_qty", label: "On-Hand Qty", fmt: fmtQty },
            { key: "onhand_thb", label: "On-Hand (THB @ Master Price)", fmt: fmtThb },
            {
              key: "inventory_build_up",
              label: "Status",
              fmt: (v) =>
                v ? (
                  <span className="inline-block px-2 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800">Build-Up</span>
                ) : (
                  <span className="inline-block px-2 py-0.5 rounded-full text-xs font-bold bg-green-100 text-green-800">OK</span>
                ),
            },
          ]}
          data={brands}
          defaultSort="purchased_thb"
        />
      </div>
    </div>
  );
}

/* ================================================================== */
/*  TAB 3 — Working Capital & Efficiency                               */
/* ================================================================== */
function WorkingCapitalTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/working_capital_trends", { signal });
      setData(res.data);
    } catch (e) {
      if (isAbortError(e)) return;
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(controller.signal);
    return () => controller.abort();
  }, [fetch]);

  if (loading) return <p className="p-6 text-gray-500">Loading working capital data...</p>;
  if (error) return <ErrorBanner message={error} onRetry={() => fetch()} className="m-6" />;
  if (!data || !data.monthly_trends?.length) return <p className="p-6 text-gray-500">No working capital data available.</p>;

  const { monthly_trends, summary } = data;

  const trendDir = summary.trend_direction;
  const trendColor = trendDir === "improving" ? "text-green-600" : trendDir === "declining" ? "text-red-600" : "text-gray-600";
  const trendLabel = trendDir === "improving" ? "Improving" : trendDir === "declining" ? "Declining" : "Flat";

  const chartData = monthly_trends.map((m) => ({
    period: m.period.substring(0, 7),
    onhand: m.onhand_thb,
    revenue: m.revenue_thb,
    turnover: m.turnover_rate,
    stock_to_sales: m.stock_to_sales,
  }));

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KpiCard label="Inventory Value (@ Master Price)" value={fmtThb(summary.current_onhand_thb)} sub="Current on-hand" />
        <KpiCard label="Monthly Revenue" value={fmtThb(summary.current_revenue_monthly)} sub="Latest month" />
        <KpiCard label="Turnover Rate" value={fmtRatio(summary.current_turnover)} sub="Annual (rev/inv)" />
        <KpiCard label="Trend" value={trendLabel} sub={<span className={trendColor}>{summary.months_analyzed} months analyzed</span>} />
        <KpiCard
          label="Stock/Sales Ratio"
          value={summary.current_onhand_thb && summary.current_revenue_monthly
            ? (summary.current_onhand_thb / summary.current_revenue_monthly).toFixed(1) + "x"
            : "\u2014"
          }
          sub="Lower is leaner"
        />
      </div>

      {/* Inventory value vs Revenue dual axis chart */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Inventory Value vs. Monthly Revenue</h3>
        <ResponsiveContainer width="100%" height={350}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} tickFormatter={(v) => (v / 1000000).toFixed(1) + "M"} />
            <Tooltip formatter={(v) => fmtThb(v)} />
            <Legend />
            <Bar yAxisId="left" dataKey="onhand" fill="#dc2626" name="On-Hand (@ Master Price)" opacity={0.7} />
            <Bar yAxisId="left" dataKey="revenue" fill="#059669" name="Revenue (actual sales)" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Turnover rate trend */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Annualized Turnover Rate Over Time</h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => fmtRatio(v)} />
            <Line type="monotone" dataKey="turnover" stroke="#1a3a8f" strokeWidth={2} dot={{ r: 3 }} name="Turnover Rate" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Stock-to-sales trend */}
      <div className="rounded-lg border p-4 bg-white">
        <h3 className="text-sm font-semibold mb-3">Stock-to-Sales Ratio (lower = leaner inventory)</h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData.filter((d) => d.stock_to_sales != null)}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => fmtRatio(v)} />
            <Line type="monotone" dataKey="stock_to_sales" stroke="#d97706" strokeWidth={2} dot={{ r: 3 }} name="Stock/Sales" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Detail table with CSV */}
      <div className="rounded-lg border p-4 bg-white">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Monthly Working Capital Detail</h3>
          <button
            className="text-xs px-3 py-1 rounded border hover:bg-gray-50"
            onClick={() => downloadCsv(
              "working_capital_trends.csv",
              ["Period", "On-Hand THB", "Revenue THB", "Stock/Sales", "Turnover Rate"],
              monthly_trends.map((m) => [m.period, m.onhand_thb, m.revenue_thb, m.stock_to_sales, m.turnover_rate]),
            )}
          >
            CSV
          </button>
        </div>
        <SortableTable
          columns={[
            { key: "period", label: "Period", fmt: (v) => v?.substring(0, 7) },
            { key: "onhand_thb", label: "On-Hand (THB)", tooltip: METRIC_TOOLTIPS.purchase.working_capital, fmt: fmtThb },
            { key: "revenue_thb", label: "Revenue (THB)", fmt: fmtThb },
            { key: "stock_to_sales", label: "Stock/Sales", tooltip: METRIC_TOOLTIPS.purchase.stock_to_sales, fmt: fmtRatio },
            { key: "turnover_rate", label: "Turnover", tooltip: METRIC_TOOLTIPS.purchase.turnover_rate, fmt: fmtRatio },
          ]}
          data={monthly_trends}
          defaultSort="period"
          defaultDir="asc"
        />
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Main Page                                                          */
/* ================================================================== */
export default function PurchaseAnalyticsPage() {
  const [activeTab, setActiveTab] = useState("cost_trends");

  return (
    <main className="max-w-7xl mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--nichi-blue)" }}>
        Purchase &amp; Cost Analytics
      </h1>
      <p className="text-sm text-gray-500 mb-4">
        FOB cost tracking, purchase vs. sold comparison, and working capital efficiency trends.
      </p>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === t.id
                ? "text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
            style={activeTab === t.id ? { backgroundColor: "var(--nichi-blue)" } : {}}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "cost_trends" && <CostTrendsTab />}
      {activeTab === "purchase_vs_sold" && <PurchaseVsSoldTab />}
      {activeTab === "working_capital" && <WorkingCapitalTab />}
    </main>
  );
}
