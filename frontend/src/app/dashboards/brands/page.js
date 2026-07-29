"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  PieChart,
  Pie,
} from "recharts";
import api, { isAbortError } from "@/utils/api";
import SortableTable from "@/components/SortableTable";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBanner from "@/components/ErrorBanner";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import ChartDownloadToolbar from "@/components/ChartDownloadToolbar";
import { fmtThb, fmtQty, fmtPct } from "@/utils/formatters";
import { downloadCsv, downloadCsvFromObjects } from "@/utils/csvExport";

function chartThb(v) {
  if (v == null) return "";
  if (Math.abs(v) >= 1e6) return `฿${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `฿${(v / 1e3).toFixed(0)}K`;
  return `฿${v.toFixed(0)}`;
}

const BRAND_COLORS = [
  "#1a3a8f", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6",
  "#1abc9c", "#e67e22", "#3498db", "#c0392b", "#27ae60",
];

const ABCDE_COLORS = { A: "#059669", B: "#2563eb", C: "#d97706", D: "#ea580c", E: "#dc2626" };
const ABCDE_BG = {
  A: "bg-green-100 text-green-800",
  B: "bg-blue-100 text-blue-800",
  C: "bg-amber-100 text-amber-800",
  D: "bg-orange-100 text-orange-800",
  E: "bg-red-100 text-red-800",
};

const CHANNEL_COLORS = [
  "#1a3a8f", "#FFD200", "#059669", "#dc2626", "#7c3aed",
  "#d97706", "#0891b2", "#be185d", "#4f46e5", "#65a30d",
  "#ea580c", "#0d9488", "#6366f1", "#c026d3", "#84cc16",
];

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

const CHANNEL_DESCRIPTIONS = {
  Shop: "ToyVault standalone retail stores (19 locations).",
  Online: "E-commerce via E-Commerce & E-Commerce.",
  Grandway: "Grandway department store branches across Thailand.",
  Pinnacle: "Pinnacle department store branches.",
  "Plaza Group": "Plaza Group Group shopping center locations.",
  "DutyFree Plus": "DutyFree Plus duty-free stores.",
  "Value Mart": "Outlet mall locations.",
  Promotions: "Promotional events, pop-ups, and seasonal sales.",
  "WH Sale": "Direct warehouse sales.",
  "KidZone": "KidZone retail locations in Thailand.",
  "SIAM Takashimaya": "Grandway Takashimaya department store.",
  BookPlay: "BookPlay bookstore chain (toy sections).",
  AsiaBook: "Asia Books retail locations.",
  "Baby-And-Children": "Baby & children specialty retailers.",
  DiscountWorld: "Don Quijote (DiscountWorld) discount stores.",
  "7-Eleven": "7-Eleven convenience store consignment.",
};

function AbcdeBadgeInline({ cls }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold ${ABCDE_BG[cls] || "bg-gray-100 text-gray-700"}`}>
      {cls}
    </span>
  );
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "classification", label: "Product Classification" },
  { id: "channel_fit", label: "Channel Fit" },
];


// ====================== OVERVIEW TAB ======================

const OVERVIEW_COLUMNS = [
  {
    key: "brand",
    label: "Brand",
    linkFn: (row) => `/dashboards/brands/${encodeURIComponent(row.brand)}`,
  },
  {
    key: "revenue_master_thb",
    label: "Revenue (THB, Master)",
    fmt: fmtThb,
    tooltip: "Top-line revenue at the master (list) price. Revenue (Master) = Revenue (Actual) + Retailer Cut.",
  },
  {
    key: "retailer_cut_thb",
    label: "Retailer Cut (THB)",
    fmt: fmtThb,
    tooltip: "What the retailer keeps. For consignment = GP Commission; for credit = discount (Master − invoiced). Unified across both sale types.",
  },
  {
    key: "net_revenue_thb",
    label: "Revenue (THB, Actual)",
    fmt: fmtThb,
    tooltip: "What ToyVault actually keeps after the retailer's cut. Revenue (Master) − Retailer Cut. Consistent across consignment and credit sales.",
  },
  {
    key: "revenue_thb",
    label: "Revenue (THB, Invoiced)",
    fmt: fmtThb,
    tooltip: "SAP LineTotal — the gross invoiced amount. For consignment this equals Master (GP not yet deducted); for credit it's the already-discounted price. Useful for SAP reconciliation; for economic 'Revenue to Nichi' see Revenue (Actual).",
  },
  { key: "cogs_thb", label: "COGS (THB, FOB)", fmt: fmtThb },
  {
    key: "gp_commission_thb",
    label: "GP Commission (THB)",
    fmt: fmtThb,
    tooltip: "Retailer's cut on consignment sales (part of Retailer Cut).",
  },
  {
    key: "discount_thb",
    label: "Discount (THB)",
    fmt: fmtThb,
    tooltip: "Retailer's cut on credit/outright sales = Revenue (Master) − Revenue (Invoiced). Part of Retailer Cut.",
  },
  {
    key: "retailer_cut_pct",
    label: "Retailer Cut %",
    fmt: fmtPct,
    tooltip: "Retailer Cut ÷ Revenue (Master). Apples-to-apples cost-of-channel across consignment and credit.",
  },
  {
    key: "gross_margin_thb",
    label: "Gross Margin (THB)",
    fmt: fmtThb,
    tooltip: "Revenue (Actual) − COGS (FOB) − GP Commission",
  },
  { key: "gross_margin_pct", label: "Margin %", fmt: fmtPct },
  { key: "sold_qty", label: "Sold Qty (Units)", fmt: fmtQty },
  { key: "onhand_qty", label: "On-Hand Qty (Units)", fmt: fmtQty },
  {
    key: "onhand_thb",
    label: "On-Hand Value (THB @ Master Price)",
    fmt: fmtThb,
    tooltip: "Current inventory valued at Master (list) Price",
  },
  {
    key: "sell_through_rate",
    label: "Sell-Through %",
    fmt: fmtPct,
    tooltip: "Sold Qty / (Sold Qty + On-Hand Qty) × 100",
  },
  {
    key: "abcde_a_count", label: "A", fmt: fmtQty,
    tooltip: "Star products — top items contributing to 50% of this brand's revenue",
    render: (v) => <span className="text-green-700 font-semibold">{fmtQty(v)}</span>,
  },
  {
    key: "abcde_b_count", label: "B", fmt: fmtQty,
    tooltip: "Strong performers — next items contributing to 80% of revenue",
    render: (v) => <span className="text-blue-700 font-medium">{fmtQty(v)}</span>,
  },
  { key: "abcde_c_count", label: "C", fmt: fmtQty, tooltip: "Average — next items contributing to 95% of revenue" },
  {
    key: "abcde_d_count", label: "D", fmt: fmtQty,
    tooltip: "Weak — next items contributing to 99% of revenue, candidates for markdown",
    render: (v) => v > 0 ? <span className="text-orange-600 font-medium">{fmtQty(v)}</span> : <span>{fmtQty(v)}</span>,
  },
  {
    key: "abcde_e_count", label: "E", fmt: fmtQty,
    tooltip: "Dead weight — bottom 1% of revenue, candidates for discontinuation",
    render: (v) => v > 0 ? <span className="text-red-600 font-medium">{fmtQty(v)}</span> : <span>{fmtQty(v)}</span>,
  },
];

function OverviewTab({ selectedYears, toggleYear }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const trendChartRef = useRef(null);

  const loadData = useCallback((years, signal) => {
    setLoading(true);
    setError(null);
    const qs = new URLSearchParams();
    years.forEach((y) => qs.append("year_list", String(y)));
    api.get(`/api/brand_list_metrics?${qs.toString()}`, { signal })
      .then((res) => {
        const data = res.data;
        if (data.message === "data not ready") { setError("Data is still loading."); return; }
        // net_revenue_thb is now computed server-side on unrounded aggregates
        // so the identity Master = Net + Retailer Cut holds exactly.
        // Client-side fallback kept for safety during rollout.
        const enriched = (data.rows || []).map((r) => ({
          ...r,
          net_revenue_thb: r.net_revenue_thb != null
            ? r.net_revenue_thb
            : (r.revenue_master_thb ?? 0) - (r.retailer_cut_thb ?? 0),
        }));
        setRows(enriched);
      })
      .catch((err) => { if (!isAbortError(err)) setError(err.response?.data?.error || err.message); })
      .finally(() => setLoading(false));
  }, []);

  const loadTrend = useCallback((years, signal) => {
    const qs = new URLSearchParams();
    years.forEach((y) => qs.append("year_list", String(y)));
    api.get(`/api/brand_monthly_trend?top_n=5&${qs.toString()}`, { signal })
      .then((res) => { if (res.data?.message !== "data not ready") setTrendData(res.data); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    loadData(selectedYears, ctrl.signal);
    loadTrend(selectedYears, ctrl.signal);
    return () => ctrl.abort();
  }, [loadData, loadTrend, selectedYears]);

  const trendChartData = useMemo(() => {
    if (!trendData?.trends?.length) return [];
    const periods = trendData.periods || [];
    return periods.map((p) => {
      const point = { period: p };
      for (const t of trendData.trends) {
        const m = t.months.find((m) => m.period === p);
        point[t.brand] = m ? m.sold_thb : 0;
      }
      return point;
    });
  }, [trendData]);

  const handleExport = () => {
    downloadCsvFromObjects(
      rows.map((r) => ({
        Brand: r.brand,
        "Revenue (THB, Master)": r.revenue_master_thb,
        "Retailer Cut (THB)": r.retailer_cut_thb,
        "Revenue (THB, Actual)": r.net_revenue_thb,
        "Revenue (THB, Invoiced)": r.revenue_thb,
        "COGS FOB (THB)": r.cogs_thb,
        "GP Commission (THB)": r.gp_commission_thb,
        "Discount (THB)": r.discount_thb,
        "Retailer Cut %": r.retailer_cut_pct,
        "Gross Margin (THB)": r.gross_margin_thb,
        "Margin %": r.gross_margin_pct,
        "Sold Qty": r.sold_qty,
        "On-Hand Qty": r.onhand_qty,
        "On-Hand Value (THB @ Master Price)": r.onhand_thb,
        "Sell-Through %": r.sell_through_rate,
      })),
      `brands_${selectedYears.sort((a, b) => a - b).join("_")}.csv`
    );
  };

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  return (
    <div className="space-y-6">
      {/* Year filter + export */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-gray-500">Year:</span>
        {YEAR_OPTIONS.map((y) => (
          <button key={y} onClick={() => toggleYear(y)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${selectedYears.includes(y) ? "bg-[var(--nichi-blue)] text-white" : "border border-gray-200 hover:bg-gray-100"}`}
          >{y}</button>
        ))}
        {rows.length > 0 && (
          <>
            <div className="w-px h-6 bg-gray-200 mx-1" />
            <button onClick={handleExport}
              className="px-4 py-1.5 text-sm bg-[var(--nichi-blue)] text-white rounded-lg hover:bg-[var(--nichi-blue-dark)] whitespace-nowrap">
              Export CSV
            </button>
          </>
        )}
      </div>

      {/* Monthly Revenue Trend Chart */}
      {trendChartData.length > 0 && (
        <div className="bg-white rounded-lg shadow border p-4">
          <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
            <h2 className="text-base font-semibold text-gray-800">
              Monthly Revenue by Top Brands — {yearLabel}
            </h2>
            <ChartDownloadToolbar
              data={trendChartData}
              filenameBase={`brands_top_monthly_revenue_${yearLabel.replace(/, /g, "_")}`}
              chartRef={trendChartRef}
            />
          </div>
          <div ref={trendChartRef}>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={chartThb} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Legend />
              {(trendData?.trends || []).map((t, i) => (
                <Line key={t.brand} type="monotone" dataKey={t.brand}
                  stroke={BRAND_COLORS[i % BRAND_COLORS.length]} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
          </div>
        </div>
      )}

      {loading && <LoadingSpinner />}
      {error && <ErrorBanner message={error} onRetry={() => loadData(selectedYears)} />}
      {!loading && !error && (
        <div className="bg-white rounded-lg shadow border overflow-hidden">
          <SortableTable columns={OVERVIEW_COLUMNS} data={rows} defaultSort="revenue_thb" defaultDir="desc" pageSize={100} />
        </div>
      )}
    </div>
  );
}


// ====================== PRODUCT CLASSIFICATION TAB (ABCDE) ======================

function ClassificationTab({ selectedYears, toggleYear }) {
  const pieChartRef = useRef(null);
  const paretoChartRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dimension, setDimension] = useState("item");
  // Use the first selected year for classification (single-year view)
  const selectedYear = selectedYears.length > 0 ? Math.max(...selectedYears) : CY;

  const fetchData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    params.set("dimension", dimension);
    params.set("year", String(selectedYear));
    api.get(`/api/abc_classification?${params}`, { signal })
      .then((res) => { setData(res.data); setLoading(false); })
      .catch((err) => { if (!isAbortError(err)) { setError(err.message); setLoading(false); } });
  }, [dimension, selectedYear]);

  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
    return () => controller.abort();
  }, [fetchData]);

  if (loading) return <LoadingSpinner message="Loading classification..." />;
  if (error) return <ErrorBanner message={error} onRetry={() => fetchData()} className="m-8" />;
  if (!data || !data.rows || data.rows.length === 0)
    return <div className="p-8 text-center text-gray-500">No data available for selected filters.</div>;

  const summary = data.summary || {};
  const tiers = ["A", "B", "C", "D", "E"];
  const pieData = tiers
    .filter((cls) => summary[cls])
    .map((cls) => ({
      name: `Class ${cls}`, value: summary[cls]?.revenue_thb || 0, count: summary[cls]?.count || 0,
    }));

  const columns = dimension === "item" ? [
    { key: "rank", label: "#" },
    { key: "abc_class", label: "Tier", render: (v) => <AbcdeBadgeInline cls={v} /> },
    { key: "item_code", label: "Item Code", render: (v) => v ? <Link href={`/dashboards/item-detail/${encodeURIComponent(v)}`} className="text-[var(--nichi-blue)] hover:underline font-medium">{v}</Link> : "—" },
    { key: "brand", label: "Brand" },
    { key: "description", label: "Description" },
    { key: "revenue_thb", label: "Revenue (THB)", render: (v) => fmtThb(v) },
    { key: "revenue_pct", label: "% of Total", render: (v) => fmtPct(v) },
    { key: "cumulative_pct", label: "Cumulative %", render: (v) => fmtPct(v) },
    { key: "sold_qty", label: "Sold Qty", render: (v) => fmtQty(v) },
    { key: "onhand_qty", label: "On-Hand", render: (v) => fmtQty(v) },
  ] : [
    { key: "rank", label: "#" },
    { key: "abc_class", label: "Tier", render: (v) => <AbcdeBadgeInline cls={v} /> },
    { key: "brand", label: "Brand" },
    { key: "sku_count", label: "SKUs" },
    { key: "revenue_thb", label: "Revenue (THB)", render: (v) => fmtThb(v) },
    { key: "revenue_pct", label: "% of Total", render: (v) => fmtPct(v) },
    { key: "cumulative_pct", label: "Cumulative %", render: (v) => fmtPct(v) },
    { key: "sold_qty", label: "Sold Qty", render: (v) => fmtQty(v) },
    { key: "onhand_qty", label: "On-Hand", render: (v) => fmtQty(v) },
  ];

  const handleExport = () => {
    const headers = columns.map((c) => c.label);
    const csvRows = data.rows.map((r) => columns.map((c) => r[c.key]));
    downloadCsv(`product_classification_${dimension}_${selectedYear}.csv`, headers, csvRows);
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex flex-wrap gap-4 items-center">
        <label className="flex items-center gap-2 text-sm font-medium">
          View:
          <select value={dimension} onChange={(e) => setDimension(e.target.value)}
            className="border rounded px-3 py-1.5 text-sm bg-white">
            <option value="item">By Item</option>
            <option value="brand">By Brand</option>
          </select>
        </label>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">Year:</span>
          {YEAR_OPTIONS.map((y) => (
            <button key={y} onClick={() => toggleYear(y)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${selectedYears.includes(y) ? "bg-[var(--nichi-blue)] text-white" : "border border-gray-200 hover:bg-gray-100"}`}>
              {y}
            </button>
          ))}
        </div>
        <button onClick={handleExport}
          className="ml-auto px-3 py-1 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)]">
          Export CSV
        </button>
      </div>

      <p className="text-sm text-gray-500">
        ABCDE classification for {selectedYear}. A = top 50% revenue (stars), B = 50-80% (strong),
        C = 80-95% (average), D = 95-99% (weak), E = bottom 1% (dead weight).
      </p>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <div className="text-sm text-gray-500">Total Revenue</div>
          <div className="text-xl font-bold">{fmtThb(data.total_revenue_thb)}</div>
          <div className="text-xs text-gray-400">{data.total_skus} {dimension === "item" ? "items" : "brands"}</div>
        </div>
        {tiers.map((cls) => summary[cls] ? (
          <div key={cls} className="bg-white border rounded-lg p-4 shadow-sm">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              Class <AbcdeBadgeInline cls={cls} />
            </div>
            <div className="text-xl font-bold">{fmtThb(summary[cls]?.revenue_thb || 0)}</div>
            <div className="text-xs text-gray-400">
              {summary[cls]?.count || 0} {dimension === "item" ? "items" : "brands"} ({fmtPct(summary[cls]?.revenue_pct || 0)})
            </div>
          </div>
        ) : null)}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
            <h3 className="text-sm font-semibold">Revenue Distribution by Tier</h3>
            <ChartDownloadToolbar
              data={pieData}
              filenameBase={`abcde_distribution_${dimension}`}
              chartRef={pieChartRef}
              csvColumns={["name", "value"]}
            />
          </div>
          <div ref={pieChartRef}>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                outerRadius={100} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {pieData.map((entry, i) => (
                  <Cell key={i} fill={ABCDE_COLORS[entry.name.split(" ")[1]] || "#8884d8"} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => fmtThb(v)} />
            </PieChart>
          </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
            <h3 className="text-sm font-semibold">Top 15 by Revenue (Pareto)</h3>
            <ChartDownloadToolbar
              data={data.rows.slice(0, 15)}
              filenameBase={`abcde_top15_pareto_${dimension}`}
              chartRef={paretoChartRef}
              csvColumns={[dimension === "item" ? "item_code" : "brand", "revenue_thb", "abc_class"]}
            />
          </div>
          <div ref={paretoChartRef}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data.rows.slice(0, 15)} margin={{ bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={dimension === "item" ? "item_code" : "brand"}
                angle={-45} textAnchor="end" interval={0} tick={{ fontSize: 10 }} />
              <YAxis tickFormatter={(v) => (v / 1000000).toFixed(1) + "M"} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Bar dataKey="revenue_thb" name="Revenue">
                {data.rows.slice(0, 15).map((r, i) => (
                  <Cell key={i} fill={ABCDE_COLORS[r.abc_class] || "#8884d8"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold mb-3">Full Classification ({data.rows.length} {dimension === "item" ? "items" : "brands"})</h3>
        <SortableTable columns={columns} data={data.rows} defaultSort="rank" defaultDir="asc" />
      </div>
    </div>
  );
}


// ====================== CHANNEL FIT TAB ======================

function ChannelFitTab({ selectedYears, toggleYear }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dimension, setDimension] = useState("brand");
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [showAllChannels, setShowAllChannels] = useState(false);
  const channelChartRef = useRef(null);
  const topPerChannelRef = useRef(null);

  const fetchData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    params.set("dimension", dimension);
    selectedYears.forEach((y) => params.append("year_list", String(y)));
    api.get(`/api/product_channel_fit?${params}`, { signal })
      .then((res) => { setData(res.data); setLoading(false); })
      .catch((err) => { if (!isAbortError(err)) { setError(err.message); setLoading(false); } });
  }, [dimension, selectedYears]);

  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
    return () => controller.abort();
  }, [fetchData]);

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  if (loading) return <LoadingSpinner message="Loading product-channel fit..." />;
  if (error) return <ErrorBanner message={error} onRetry={() => fetchData()} className="m-8" />;
  if (!data || !data.matrix || data.matrix.length === 0)
    return <div className="p-8 text-center text-gray-500">No data available for selected filters.</div>;

  const channels = data.channels || [];
  const summary = data.summary || {};
  const chBarData = Object.entries(summary)
    .sort((a, b) => b[1].revenue - a[1].revenue)
    .map(([ch, v]) => ({ channel: ch, revenue: v.revenue, revenue_pct: v.revenue_pct, product_count: v.product_count, qty: v.qty }));
  const totalChannelRevenue = chBarData.reduce((s, c) => s + c.revenue, 0);
  const heatmapMax = Math.max(...data.matrix.flatMap((r) => Object.values(r.channels).map((v) => v.revenue)), 1);
  const visibleChannelCards = showAllChannels ? chBarData : chBarData.slice(0, 12);

  const handleExport = () => {
    const headers = ["Product", "Total Revenue", "Total Qty", "Channels Active", ...channels.map((c) => `${c} Revenue`), ...channels.map((c) => `${c} Qty`)];
    const csvRows = data.matrix.map((r) => [
      r.product, r.total_revenue, r.total_qty, r.channel_count,
      ...channels.map((c) => r.channels[c]?.revenue || 0),
      ...channels.map((c) => r.channels[c]?.qty || 0),
    ]);
    downloadCsv(`product_channel_fit_${dimension}_${yearLabel.replace(/, /g, "_")}.csv`, headers, csvRows);
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex flex-wrap gap-4 items-center">
        <label className="flex items-center gap-2 text-sm font-medium">
          View:
          <select value={dimension} onChange={(e) => setDimension(e.target.value)}
            className="border rounded px-3 py-1.5 text-sm bg-white">
            <option value="brand">By Brand</option>
            <option value="item">By Item</option>
          </select>
        </label>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">Year:</span>
          {YEAR_OPTIONS.map((y) => (
            <button key={y} onClick={() => toggleYear(y)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${selectedYears.includes(y) ? "bg-[var(--nichi-blue)] text-white" : "border border-gray-200 hover:bg-gray-100"}`}>
              {y}
            </button>
          ))}
        </div>
        <button onClick={handleExport}
          className="ml-auto px-3 py-1 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)]">
          Export CSV
        </button>
      </div>

      <p className="text-sm text-gray-500">
        Product-channel fit for {yearLabel}. Which products sell through which channels?
      </p>

      {/* Channel cards */}
      <div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {visibleChannelCards.map((ch) => (
            <div key={ch.channel}
              className={`bg-white border rounded-lg p-3 shadow-sm cursor-pointer hover:ring-2 hover:ring-[var(--nichi-blue)] transition-all ${selectedChannel === ch.channel ? "ring-2 ring-[var(--nichi-blue)]" : ""}`}
              onClick={() => setSelectedChannel(selectedChannel === ch.channel ? null : ch.channel)}
              title={CHANNEL_DESCRIPTIONS[ch.channel] || `Sales channel: ${ch.channel}`}>
              <div className="text-xs text-gray-500 truncate font-medium">{ch.channel}</div>
              <div className="text-lg font-bold">{fmtThb(ch.revenue)}</div>
              <div className="text-xs text-gray-400">
                {fmtPct(ch.revenue_pct || (totalChannelRevenue > 0 ? (ch.revenue / totalChannelRevenue) * 100 : 0))} share
                {" · "}{ch.product_count} {dimension === "item" ? "items" : "brands"}
              </div>
            </div>
          ))}
        </div>
        {chBarData.length > 12 && (
          <button onClick={() => setShowAllChannels(!showAllChannels)}
            className="mt-2 text-sm text-[var(--nichi-blue)] hover:underline">
            {showAllChannels ? "Show fewer channels" : `Show all ${chBarData.length} channels`}
          </button>
        )}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
            <h3 className="text-sm font-semibold">Revenue by Channel — {yearLabel}</h3>
            <ChartDownloadToolbar
              data={chBarData}
              filenameBase={`channels_revenue_${yearLabel.replace(/, /g, "_")}`}
              chartRef={channelChartRef}
              csvColumns={["channel", "revenue"]}
            />
          </div>
          <div ref={channelChartRef}>
          <ResponsiveContainer width="100%" height={Math.max(280, chBarData.length * 24)}>
            <BarChart data={chBarData} layout="vertical" margin={{ left: 100, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tickFormatter={(v) => (v / 1000000).toFixed(1) + "M"} />
              <YAxis type="category" dataKey="channel" width={95} tick={{ fontSize: 11 }} interval={0} />
              <Tooltip formatter={(v) => fmtThb(v)} />
              <Bar dataKey="revenue" name="Revenue (THB, Actual Sales)">
                {chBarData.map((entry, i) => (
                  <Cell key={i} fill={selectedChannel === entry.channel ? "#FFD200" : CHANNEL_COLORS[i % CHANNEL_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          </div>
        </div>
        <div className="bg-white border rounded-lg p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
            <h3 className="text-sm font-semibold">
              {selectedChannel ? `Top ${dimension === "item" ? "Items" : "Brands"} in ${selectedChannel}` : "Click a channel to see top products"}
            </h3>
            {selectedChannel && data.top_per_channel[selectedChannel] && (
              <ChartDownloadToolbar
                data={data.top_per_channel[selectedChannel].slice(0, 10)}
                filenameBase={`channel_${selectedChannel}_top_${dimension}_${yearLabel.replace(/, /g, "_")}`}
                chartRef={topPerChannelRef}
                csvColumns={["product", "revenue"]}
              />
            )}
          </div>
          {selectedChannel && data.top_per_channel[selectedChannel] ? (
            <div ref={topPerChannelRef}>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={data.top_per_channel[selectedChannel].slice(0, 10)} margin={{ bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="product" angle={-45} textAnchor="end" interval={0} tick={{ fontSize: 10 }} />
                <YAxis tickFormatter={(v) => (v / 1000000).toFixed(1) + "M"} />
                <Tooltip formatter={(v) => fmtThb(v)} />
                <Bar dataKey="revenue" name="Revenue (THB)" fill="#1a3a8f" />
              </BarChart>
            </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-400">Click a channel card or bar above</div>
          )}
        </div>
      </div>

      {/* Channel Summary Table */}
      <div className="bg-white border rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold mb-3">Channel Summary — {yearLabel}</h3>
        <SortableTable
          columns={[
            { key: "channel", label: "Channel" },
            { key: "revenue", label: "Revenue (THB, Actual Sales)", render: (v) => fmtThb(v) },
            { key: "revenue_pct", label: "Share (%)", render: (v) => fmtPct(v) },
            { key: "product_count", label: `${dimension === "item" ? "Items" : "Brands"}` },
            { key: "qty", label: "Sold Qty", render: (v) => fmtQty(v) },
          ]}
          data={chBarData}
          defaultSort="revenue"
          defaultDir="desc"
        />
      </div>

      {/* Heatmap */}
      <div className="bg-white border rounded-lg p-4 shadow-sm">
        <h3 className="text-sm font-semibold mb-3">
          {dimension === "item" ? "Item" : "Brand"}-Channel Revenue Heatmap — {yearLabel}
        </h3>
        <p className="text-xs text-gray-400 mb-2">Darker blue = higher revenue.</p>
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs border-collapse">
            <thead>
              <tr className="bg-gray-50">
                <th className="px-2 py-1.5 text-left font-semibold border-b sticky left-0 bg-gray-50 z-10">
                  {dimension === "item" ? "Item" : "Brand"}
                </th>
                <th className="px-2 py-1.5 text-right font-semibold border-b">Total Revenue</th>
                <th className="px-2 py-1.5 text-center font-semibold border-b">#Ch</th>
                {channels.map((ch) => (
                  <th key={ch} className="px-2 py-1.5 text-right font-semibold border-b whitespace-nowrap cursor-help"
                    title={CHANNEL_DESCRIPTIONS[ch] || ch}>{ch}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.matrix.map((row, i) => (
                <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  <td className="px-2 py-1 border-b font-medium sticky left-0 bg-inherit z-10 whitespace-nowrap">
                    {dimension === "item" ? (
                      <Link href={`/dashboards/item-detail/${encodeURIComponent(row.product)}`} className="text-[var(--nichi-blue)] hover:underline">{row.product}</Link>
                    ) : row.product}
                    {dimension === "item" && row.brand && <span className="ml-1 text-gray-400">({row.brand})</span>}
                  </td>
                  <td className="px-2 py-1 border-b text-right font-semibold">{fmtThb(row.total_revenue)}</td>
                  <td className="px-2 py-1 border-b text-center">{row.channel_count}</td>
                  {channels.map((ch) => {
                    const rev = row.channels[ch]?.revenue || 0;
                    const intensity = rev > 0 ? Math.max(0.1, Math.min(1, rev / heatmapMax)) : 0;
                    const bg = rev > 0 ? `rgba(26, 58, 143, ${intensity * 0.3 + 0.05})` : "transparent";
                    return (
                      <td key={ch} className="px-2 py-1 border-b text-right whitespace-nowrap" style={{ backgroundColor: bg }}>
                        {rev > 0 ? fmtThb(rev) : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


// ====================== MAIN PAGE ======================

export default function BrandsListPage() {
  const [activeTab, setActiveTab] = useState("overview");
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

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  return (
    <div className="max-w-[1400px] mx-auto px-4 py-6">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-500 mb-4">
        <Link href="/" className="hover:underline">Home</Link>
        <span className="mx-1">/</span>
        <span className="text-gray-800 font-medium">Brands</span>
      </nav>

      <div className="mb-4">
        <h1 className="text-2xl font-bold text-[var(--nichi-blue)]">Brands & Products</h1>
        <p className="text-sm text-gray-500 mt-1">
          Brand performance, product classification, and channel fit for {yearLabel}.
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

      {activeTab === "overview" && <OverviewTab selectedYears={selectedYears} toggleYear={toggleYear} />}
      {activeTab === "classification" && <ClassificationTab selectedYears={selectedYears} toggleYear={toggleYear} />}
      {activeTab === "channel_fit" && <ChannelFitTab selectedYears={selectedYears} toggleYear={toggleYear} />}
    </div>
  );
}
