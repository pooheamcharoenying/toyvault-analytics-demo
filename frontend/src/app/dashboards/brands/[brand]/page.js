"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import api, { isAbortError } from "@/utils/api";
import SortableTable from "@/components/SortableTable";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBanner from "@/components/ErrorBanner";
import AbcdeBadge from "@/components/AbcdeBadge";
import ChartDownloadToolbar from "@/components/ChartDownloadToolbar";
import RecommendationPanel from "@/components/RecommendationCard";
import { fmtThb, fmtQty, fmtPct } from "@/utils/formatters";
import { downloadCsvFromObjects } from "@/utils/csvExport";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

/* ------------------------------------------------------------------ */
/*  Stock vs Sales by Location / by Channel charts                    */
/* ------------------------------------------------------------------ */

const LOC_BAR_DEFAULT = 20;

function BrandStockVsSalesCharts({ data, showAllLocBars, setShowAllLocBars, brandName }) {
  const router = useRouter();
  const { by_location = [], by_channel = [], year_label } = data || {};
  const locChartRef = useRef(null);
  const chChartRef = useRef(null);
  const safeYr = (year_label || "").replace(/[, ]+/g, "_");
  const safeBrand = (brandName || "brand").replace(/[\\/:*?"<>|]+/g, "_");

  const locRows = (by_location || [])
    .filter((r) => r.onhand_qty > 0 || r.sold_qty > 0)
    .map((r) => ({
      name: r.location.length > 30 ? r.location.slice(0, 28) + "…" : r.location,
      fullName: r.location,
      "On-Hand Qty": r.onhand_qty,
      "Sold Qty": r.sold_qty,
    }));

  // Lookup: chart axis label → full location name for clickable Y-axis labels
  const locNameByLabel = useMemo(
    () => Object.fromEntries(locRows.map((r) => [r.name, r.fullName])),
    [locRows]
  );
  const chNameByLabel = useMemo(
    () => Object.fromEntries((by_channel || []).map((r) => [r.channel, r.channel])),
    [by_channel]
  );

  const visibleLocRows = showAllLocBars ? locRows : locRows.slice(0, LOC_BAR_DEFAULT);
  const hasMoreLoc = locRows.length > LOC_BAR_DEFAULT;

  const chRows = (by_channel || [])
    .filter((r) => r.onhand_qty > 0 || r.sold_qty > 0)
    .map((r) => ({
      name: r.channel,
      fullName: r.channel,
      "On-Hand Qty": r.onhand_qty,
      "Sold Qty": r.sold_qty,
    }));

  return (
    <>
      {/* By Location */}
      {locRows.length > 0 && (
        <div className="bg-white rounded-lg shadow border p-4 mb-6">
          <div className="flex flex-wrap items-start justify-between gap-2 mb-1">
            <h2 className="text-base font-semibold text-gray-800">
              Stock Distribution vs. Sales by Location ({year_label})
            </h2>
            <ChartDownloadToolbar
              data={by_location}
              filenameBase={`brand_${safeBrand}_stock_vs_sales_by_location_${safeYr}`}
              chartRef={locChartRef}
              csvColumns={["location", "onhand_qty", "sold_qty", "onhand_thb", "sold_thb"]}
            />
          </div>
          <p className="text-xs text-gray-500 mb-3">
            Compare where stock is currently held (blue) against where it has sold (yellow).
            Locations with high stock but low sales are transfer-out candidates.
          </p>
          <div ref={locChartRef}>
          <ResponsiveContainer width="100%" height={Math.max(320, visibleLocRows.length * 22)}>
            <BarChart data={visibleLocRows} layout="vertical" margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis
                dataKey="name"
                type="category"
                width={170}
                tick={(tp) => {
                  const { x, y, payload } = tp;
                  const fullName = locNameByLabel[payload.value];
                  const base = { x, y, dy: 4, textAnchor: "end", fontSize: 11 };
                  if (!fullName || !brandName) {
                    return <text {...base} fill="#374151">{payload.value}</text>;
                  }
                  const href = `/dashboards/locations/${encodeURIComponent(fullName)}/${encodeURIComponent(brandName)}`;
                  return (
                    <text
                      {...base}
                      fill="var(--nichi-blue)"
                      style={{ cursor: "pointer", textDecoration: "underline" }}
                      onClick={() => router.push(href)}
                    >
                      <title>{`Open ${brandName} at ${fullName}`}</title>
                      {payload.value}
                    </text>
                  );
                }}
              />
              <Tooltip
                content={({ payload }) => {
                  if (!payload?.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-white border rounded shadow p-2 text-xs">
                      <p className="font-semibold mb-1">{d.fullName}</p>
                      <p>On-Hand Qty: {fmtQty(d["On-Hand Qty"])}</p>
                      <p>Sold Qty: {fmtQty(d["Sold Qty"])}</p>
                    </div>
                  );
                }}
              />
              <Legend />
              <Bar dataKey="On-Hand Qty" fill="#1a3a8f" />
              <Bar dataKey="Sold Qty" fill="#FFD200" />
            </BarChart>
          </ResponsiveContainer>
          </div>
          {hasMoreLoc && (
            <div className="mt-3 text-center">
              <button
                onClick={() => setShowAllLocBars(!showAllLocBars)}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 hover:bg-gray-100 text-gray-700"
              >
                {showAllLocBars
                  ? `Show Less (Top ${LOC_BAR_DEFAULT})`
                  : `Show More (${locRows.length - LOC_BAR_DEFAULT} more)`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* By Channel */}
      {chRows.length > 0 && (
        <div className="bg-white rounded-lg shadow border p-4 mb-6">
          <div className="flex flex-wrap items-start justify-between gap-2 mb-1">
            <h2 className="text-base font-semibold text-gray-800">
              Stock Distribution vs. Sales by Channel ({year_label})
            </h2>
            <ChartDownloadToolbar
              data={by_channel}
              filenameBase={`brand_${safeBrand}_stock_vs_sales_by_channel_${safeYr}`}
              chartRef={chChartRef}
              csvColumns={["channel", "onhand_qty", "sold_qty", "onhand_thb", "sold_thb"]}
            />
          </div>
          <p className="text-xs text-gray-500 mb-3">
            Same comparison aggregated by sales channel (Grandway, Plaza Group, BookPlay, E-Commerce,
            etc.). On-hand is attributed to the channel each warehouse most often sells through.
          </p>
          <div ref={chChartRef}>
          <ResponsiveContainer width="100%" height={Math.max(280, chRows.length * 28)}>
            <BarChart data={chRows} layout="vertical" margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis
                dataKey="name"
                type="category"
                width={150}
                tick={(tp) => {
                  const { x, y, payload } = tp;
                  const channelName = chNameByLabel[payload.value];
                  const base = { x, y, dy: 4, textAnchor: "end", fontSize: 11 };
                  if (!channelName) {
                    return <text {...base} fill="#374151">{payload.value}</text>;
                  }
                  const href = `/dashboards/channels/${encodeURIComponent(channelName)}`;
                  return (
                    <text
                      {...base}
                      fill="var(--nichi-blue)"
                      style={{ cursor: "pointer", textDecoration: "underline" }}
                      onClick={() => router.push(href)}
                    >
                      <title>{`Open channel: ${channelName}`}</title>
                      {payload.value}
                    </text>
                  );
                }}
              />
              <Tooltip
                content={({ payload }) => {
                  if (!payload?.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-white border rounded shadow p-2 text-xs">
                      <p className="font-semibold mb-1">{d.fullName}</p>
                      <p>On-Hand Qty: {fmtQty(d["On-Hand Qty"])}</p>
                      <p>Sold Qty: {fmtQty(d["Sold Qty"])}</p>
                    </div>
                  );
                }}
              />
              <Legend />
              <Bar dataKey="On-Hand Qty" fill="#1a3a8f" />
              <Bar dataKey="Sold Qty" fill="#FFD200" />
            </BarChart>
          </ResponsiveContainer>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  helpers                                                           */
/* ------------------------------------------------------------------ */

/** Parse orient="split" JSON (may arrive double-encoded as a string). */
function parseSplit(raw) {
  const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
  const { columns, data } = obj;
  return (data || []).map((row) => {
    const r = {};
    columns.forEach((c, i) => (r[c] = row[i]));
    return r;
  });
}

/** Chart-safe THB formatter for axis/tooltip. */
function chartThb(v) {
  if (v == null) return "";
  if (Math.abs(v) >= 1e6) return `\u0E3F${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `\u0E3F${(v / 1e3).toFixed(0)}K`;
  return `\u0E3F${v.toFixed(0)}`;
}

/* ------------------------------------------------------------------ */
/*  column definitions                                                */
/* ------------------------------------------------------------------ */

const COLUMNS = [
  {
    key: "ItemCode",
    label: "Item Code",
    linkFn: (row) =>
      row.ItemCode === "TOTAL"
        ? null
        : `/dashboards/item-detail/${encodeURIComponent(row.ItemCode)}`,
    render: (val, row) =>
      row.ItemCode === "TOTAL" ? (
        <span className="font-bold">{val}</span>
      ) : (
        <Link
          href={`/dashboards/item-detail/${encodeURIComponent(val)}`}
          className="text-[var(--nichi-blue)] hover:underline font-medium"
        >
          {val}
        </Link>
      ),
  },
  { key: "Description", label: "Description" },
  {
    key: "abcde_class",
    label: "Tier",
    render: (v, row) =>
      row.ItemCode === "TOTAL" ? "" : <AbcdeBadge tier={v} context="within brand" />,
    tooltip: "ABCDE tier by cumulative revenue within this brand",
  },
  { key: "Brought_QTY", label: "Purchased Qty", fmt: fmtQty },
  { key: "Sold_QTY", label: "Sold Qty", fmt: fmtQty },
  { key: "OnHand_QTY", label: "On-Hand Qty", fmt: fmtQty },
  {
    key: "FOB_Price_THB",
    label: "FOB Unit Cost (THB)",
    fmt: fmtThb,
    tooltip: "Weighted-average landed cost per unit (FOB import price)",
  },
  {
    key: "Master_Price",
    label: "Master Price (THB)",
    fmt: fmtThb,
    tooltip: "List price from Item Master",
  },
  {
    key: "Total_Revenue_THB",
    label: "Revenue (THB, Master)",
    fmt: fmtThb,
    tooltip: "Sold Qty \u00d7 Master Price",
  },
  {
    key: "Actual_Revenue_THB",
    label: "Revenue (THB, Actual Sales)",
    fmt: fmtThb,
    tooltip: "Sum of actual LineTotal from sales transactions — what customers paid",
  },
  {
    key: "Total_Cost_THB",
    label: "Total Cost (THB, FOB)",
    fmt: fmtThb,
    tooltip: "Purchased Qty × FOB unit cost",
  },
  {
    key: "GP_Commission_THB",
    label: "GP Commission (THB)",
    fmt: fmtThb,
    tooltip:
      "Commission paid to retailer on consignment sales (LineTotal × U_ACT_GP %)",
  },
  {
    key: "Net_Revenue_THB",
    label: "Net Revenue (THB)",
    fmt: fmtThb,
    tooltip: "Actual Revenue − GP Commission",
  },
  {
    key: "Profit_Loss_THB",
    label: "P/L (THB)",
    tooltip:
      "Net Revenue − COGS (FOB). For consignment: Revenue − COGS − GP Commission. For credit: Revenue − COGS.",
    fmt: (v) => {
      if (v == null || Number.isNaN(v)) return "\u2014";
      const formatted = fmtThb(Math.abs(v));
      return v < 0 ? (
        <span className="text-red-600">-{formatted}</span>
      ) : (
        <span className="text-green-700">+{formatted}</span>
      );
    },
  },
  {
    key: "Profit_Margin_%",
    label: "Margin %",
    tooltip: "P/L ÷ Actual Revenue × 100 (after GP commission)",
    fmt: fmtPct,
  },
];

/* ------------------------------------------------------------------ */
/*  page component                                                    */
/* ------------------------------------------------------------------ */

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

export default function BrandDetailPage() {
  const params = useParams();
  const brandName = decodeURIComponent(params.brand);

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedYears, setSelectedYears] = useState([CY]);
  const [trendData, setTrendData] = useState(null);
  const [stockVsSales, setStockVsSales] = useState(null);
  const [showAllLocBars, setShowAllLocBars] = useState(false);
  const monthlyTrendChartRef = useRef(null);
  const topProductsChartRef = useRef(null);

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
    (years, signal) => {
      setLoading(true);
      setError(null);
      const qs = new URLSearchParams();
      qs.set("brand_name", brandName);
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/sale_brand_profit_loss?${qs.toString()}`, { signal })
        .then((res) => {
          const data = res.data;
          if (data?.message === "data not ready") {
            setError("Data is still loading. Please try again in a moment.");
            return;
          }
          setRows(parseSplit(data));
        })
        .catch((err) => {
          if (!isAbortError(err))
            setError(err.response?.data?.error || err.message);
        })
        .finally(() => setLoading(false));
    },
    [brandName]
  );

  const loadTrend = useCallback(
    (years, signal) => {
      const qs = new URLSearchParams();
      qs.set("brand_name", brandName);
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/brand_monthly_trend?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.message !== "data not ready") setTrendData(res.data);
        })
        .catch(() => {});
    },
    [brandName]
  );

  const loadStockVsSales = useCallback(
    (years, signal) => {
      const qs = new URLSearchParams();
      qs.set("brand", brandName);
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/brand_stock_vs_sales?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.message !== "data not ready") setStockVsSales(res.data);
        })
        .catch(() => {});
    },
    [brandName]
  );

  useEffect(() => {
    const ctrl = new AbortController();
    loadData(selectedYears, ctrl.signal);
    loadTrend(selectedYears, ctrl.signal);
    loadStockVsSales(selectedYears, ctrl.signal);
    return () => ctrl.abort();
  }, [loadData, loadTrend, loadStockVsSales, selectedYears]);

  const trendChartData = useMemo(() => {
    if (!trendData?.trends?.length) return [];
    const t = trendData.trends[0];
    return (t.months || []).map((m) => ({
      period: m.period,
      "Revenue (Actual)": m.is_partial ? m.running_rate_sold_thb ?? m.sold_thb : m.sold_thb,
      "Revenue (Master)": m.is_partial ? m.running_rate_sold_master_thb ?? m.sold_master_thb : m.sold_master_thb,
      "COGS (FOB)": m.is_partial ? m.running_rate_cogs_thb ?? m.cogs_thb : m.cogs_thb,
      is_partial: !!m.is_partial,
      days_elapsed: m.days_elapsed,
      days_in_month: m.days_in_month,
    }));
  }, [trendData]);

  const brandTrendPartialNote = trendChartData.length > 0 && trendChartData[trendChartData.length - 1]?.is_partial
    ? `Latest month projected from ${trendChartData[trendChartData.length - 1].days_elapsed}/${trendChartData[trendChartData.length - 1].days_in_month} days`
    : null;

  /* separate products from TOTAL row */
  const products = rows.filter((r) => r.ItemCode !== "TOTAL");
  const totalRow = rows.find((r) => r.ItemCode === "TOTAL");

  /* ABCDE classification — computed client-side from product revenue */
  const { abcdeCounts, abcdeByItem } = useMemo(() => {
    if (!products.length) return { abcdeCounts: { a: 0, b: 0, c: 0, d: 0, e: 0 }, abcdeByItem: {} };
    const sorted = [...products].sort(
      (a, b) => (b.Actual_Revenue_THB || 0) - (a.Actual_Revenue_THB || 0)
    );
    const total = sorted.reduce((s, r) => s + (r.Actual_Revenue_THB || 0), 0);
    if (total <= 0) {
      const byItem = {};
      products.forEach((r) => { byItem[r.ItemCode] = "E"; });
      return { abcdeCounts: { a: 0, b: 0, c: 0, d: 0, e: products.length }, abcdeByItem: byItem };
    }
    let cumSum = 0;
    let a = 0, b = 0, c = 0, d = 0;
    const byItem = {};
    for (let i = 0; i < sorted.length; i++) {
      const r = sorted[i];
      cumSum += r.Actual_Revenue_THB || 0;
      const pct = (cumSum / total) * 100;
      let cls;
      if (pct <= 50 || i === 0) { cls = "A"; a++; }
      else if (pct <= 80) { cls = "B"; b++; }
      else if (pct <= 95) { cls = "C"; c++; }
      else if (pct <= 99) { cls = "D"; d++; }
      else { cls = "E"; }
      byItem[r.ItemCode] = cls;
    }
    return { abcdeCounts: { a, b, c, d, e: products.length - a - b - c - d }, abcdeByItem: byItem };
  }, [products]);

  /* top-10 chart data (by Revenue) */
  const chartData = [...products]
    .sort((a, b) => (b.Actual_Revenue_THB || 0) - (a.Actual_Revenue_THB || 0))
    .slice(0, 15)
    .map((r) => ({
      name: r.ItemCode,
      revenue: r.Actual_Revenue_THB || 0,
      cost: r.Total_Cost_THB || 0,
    }));

  const handleExport = () => {
    downloadCsvFromObjects(
      products.map((r) => ({
        "Item Code": r.ItemCode,
        Description: r.Description,
        "ABCDE Tier": abcdeByItem[r.ItemCode] || "E",
        "Purchased Qty": r.Brought_QTY,
        "Sold Qty": r.Sold_QTY,
        "On-Hand Qty": r.OnHand_QTY,
        "FOB Unit Cost (THB)": r.FOB_Price_THB,
        "Master Price (THB)": r.Master_Price,
        "Revenue (THB, Master)": r.Total_Revenue_THB,
        "Revenue (THB, Actual Sales)": r.Actual_Revenue_THB,
        "Total Cost (THB, FOB)": r.Total_Cost_THB,
        "GP Commission (THB)": r.GP_Commission_THB,
        "Net Revenue (THB)": r.Net_Revenue_THB,
        "P/L (THB)": r.Profit_Loss_THB,
        "Margin %": r["Profit_Margin_%"],
      })),
      `brand_${brandName}_${selectedYears.sort((a, b) => a - b).join("_")}.csv`
    );
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-500 mb-4">
        <Link href="/" className="hover:underline">
          Home
        </Link>
        <span className="mx-1">/</span>
        <Link href="/dashboards/brands" className="hover:underline">
          Brands
        </Link>
        <span className="mx-1">/</span>
        <span className="text-gray-800 font-medium">{brandName}</span>
      </nav>

      <div className="flex flex-wrap items-center justify-between mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--nichi-blue)]">
            {brandName}
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Product-level P/L for {selectedYears.sort((a, b) => a - b).join(", ")}. P/L = Actual Revenue − COGS (FOB)
            − GP Commission. Revenue shows both Master Price and actual sales.
          </p>
        </div>
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
          {products.length > 0 && (
            <>
              <div className="w-px h-6 bg-gray-200 mx-1" />
              <button
                onClick={handleExport}
                className="px-4 py-1.5 text-sm bg-[var(--nichi-blue)] text-white rounded-lg hover:bg-[var(--nichi-blue-dark)] whitespace-nowrap"
              >
                Export CSV
              </button>
            </>
          )}
        </div>
      </div>

      {loading && <LoadingSpinner />}
      {error && <ErrorBanner message={error} onRetry={() => loadData(selectedYears)} />}

      {!loading && !error && (
        <>
          {/* KPI summary row */}
          {totalRow && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4 mb-6">
              <KpiCard
                label="Total Products"
                value={products.length}
                fmt={fmtQty}
              />
              <KpiCard
                label="Total Sold Qty"
                value={totalRow.Sold_QTY}
                fmt={fmtQty}
              />
              <KpiCard
                label="On-Hand Qty"
                value={totalRow.OnHand_QTY}
                fmt={fmtQty}
              />
              <KpiCard
                label="Revenue (Actual Sales)"
                value={totalRow.Actual_Revenue_THB}
                fmt={fmtThb}
              />
              <KpiCard
                label="Total Cost (FOB)"
                value={totalRow.Total_Cost_THB}
                fmt={fmtThb}
              />
              <KpiCard
                label="GP Commission"
                value={totalRow.GP_Commission_THB}
                fmt={fmtThb}
              />
              <KpiCard
                label="Net Revenue"
                value={totalRow.Net_Revenue_THB}
                fmt={fmtThb}
              />
              <KpiCard
                label="P/L"
                value={totalRow.Profit_Loss_THB}
                fmt={fmtThb}
                color={
                  totalRow.Profit_Loss_THB >= 0
                    ? "text-green-700"
                    : "text-red-600"
                }
              />
            </div>
          )}

          {/* ABCDE Classification summary */}
          {products.length > 0 && (
            <div className="grid grid-cols-5 gap-3 mb-6">
              <div className="bg-green-50 rounded-lg border border-green-200 p-3 text-center">
                <p className="text-xs text-green-700 font-semibold mb-1">A — Stars (top 50%)</p>
                <p className="text-2xl font-bold text-green-800">{abcdeCounts.a}</p>
              </div>
              <div className="bg-blue-50 rounded-lg border border-blue-200 p-3 text-center">
                <p className="text-xs text-blue-700 font-semibold mb-1">B — Strong (50-80%)</p>
                <p className="text-2xl font-bold text-blue-800">{abcdeCounts.b}</p>
              </div>
              <div className="bg-amber-50 rounded-lg border border-amber-200 p-3 text-center">
                <p className="text-xs text-amber-700 font-semibold mb-1">C — Average (80-95%)</p>
                <p className="text-2xl font-bold text-amber-800">{abcdeCounts.c}</p>
              </div>
              <div className="bg-orange-50 rounded-lg border border-orange-200 p-3 text-center">
                <p className="text-xs text-orange-700 font-semibold mb-1">D — Weak (95-99%)</p>
                <p className="text-2xl font-bold text-orange-800">{abcdeCounts.d}</p>
              </div>
              <div className="bg-red-50 rounded-lg border border-red-200 p-3 text-center">
                <p className="text-xs text-red-700 font-semibold mb-1">E — Dead (bottom 1%)</p>
                <p className="text-2xl font-bold text-red-800">{abcdeCounts.e}</p>
              </div>
            </div>
          )}

          {/* Monthly Revenue & Margin Trend */}
          {trendChartData.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4 mb-6">
              <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                <h2 className="text-base font-semibold text-gray-800">
                  Monthly Revenue &amp; Cost Trend — {brandName} ({selectedYears.sort((a, b) => a - b).join(", ")})
                </h2>
                <ChartDownloadToolbar
                  data={trendChartData}
                  filenameBase={`brand_${brandName}_monthly_trend_${selectedYears.sort((a, b) => a - b).join("_")}`}
                  chartRef={monthlyTrendChartRef}
                  csvColumns={["period", "Revenue (Actual)", "Revenue (Master)", "COGS (FOB)"]}
                />
              </div>
              {brandTrendPartialNote && (
                <p className="text-xs text-amber-700 mb-3">
                  ⓘ {brandTrendPartialNote} → shown as full-month running-rate projection
                </p>
              )}
              <div ref={monthlyTrendChartRef}>
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={chartThb} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => fmtThb(v)} />
                  <Legend />
                  <Line type="monotone" dataKey="Revenue (Actual)" stroke="#1a3a8f" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="Revenue (Master)" stroke="#2d4ea3" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                  <Line type="monotone" dataKey="COGS (FOB)" stroke="#FFD200" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Stock Distribution vs. Sales — by Location and by Channel */}
          {stockVsSales && (stockVsSales.by_location?.length > 0 || stockVsSales.by_channel?.length > 0) && (
            <BrandStockVsSalesCharts
              data={stockVsSales}
              brandName={brandName}
              showAllLocBars={showAllLocBars}
              setShowAllLocBars={setShowAllLocBars}
            />
          )}

          {/* Chart: top products revenue vs cost */}
          {chartData.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4 mb-6">
              <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
                <h2 className="text-base font-semibold text-gray-800">
                  Top Products: Revenue vs Cost ({selectedYears.sort((a, b) => a - b).join(", ")})
                </h2>
                <ChartDownloadToolbar
                  data={chartData}
                  filenameBase={`brand_${brandName}_top_products_${selectedYears.sort((a, b) => a - b).join("_")}`}
                  chartRef={topProductsChartRef}
                  csvColumns={["name", "revenue", "cost"]}
                />
              </div>
              <div ref={topProductsChartRef}>
              <ResponsiveContainer width="100%" height={320}>
                <BarChart
                  data={chartData}
                  margin={{ left: 10, right: 10, top: 5, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11 }}
                    interval={0}
                    angle={-35}
                    textAnchor="end"
                    height={70}
                  />
                  <YAxis tickFormatter={chartThb} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(v) => fmtThb(v)}
                    labelFormatter={(l) => `Item: ${l}`}
                  />
                  <Bar
                    dataKey="revenue"
                    name="Revenue (Actual)"
                    fill="var(--nichi-blue)"
                  />
                  <Bar
                    dataKey="cost"
                    name="Cost (FOB)"
                    fill="var(--nichi-yellow)"
                  />
                </BarChart>
              </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Recommendations */}
          <RecommendationPanel context="brand" name={brandName} years={selectedYears} />

          {/* Product table */}
          <div className="bg-white rounded-lg shadow border overflow-hidden">
            <SortableTable
              columns={COLUMNS}
              data={rows.map((r) => ({
                ...r,
                abcde_class: abcdeByItem[r.ItemCode] || (r.ItemCode === "TOTAL" ? "" : "E"),
              }))}
              defaultSort="Total_Revenue_THB"
              defaultDir="desc"
              pageSize={50}
            />
          </div>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  small KPI card                                                    */
/* ------------------------------------------------------------------ */
function KpiCard({ label, value, fmt, color }) {
  return (
    <div className="bg-white rounded-lg shadow border p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color || "text-gray-900"}`}>
        {fmt ? fmt(value) : value}
      </p>
    </div>
  );
}
