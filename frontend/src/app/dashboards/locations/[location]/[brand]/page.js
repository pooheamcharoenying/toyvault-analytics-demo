"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import api, { isAbortError } from "@/utils/api";
import SortableTable from "@/components/SortableTable";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBanner from "@/components/ErrorBanner";
import ItemLink from "@/components/ItemLink";
import AbcdeBadge from "@/components/AbcdeBadge";
import GranularityToggle from "@/components/GranularityToggle";
import ChartDownloadToolbar from "@/components/ChartDownloadToolbar";
import { fmtThb, fmtQty } from "@/utils/formatters";
import { downloadCsv, downloadCsvFromObjects } from "@/utils/csvExport";

function chartThb(v) {
  if (v == null) return "";
  if (Math.abs(v) >= 1e6) return `฿${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `฿${(v / 1e3).toFixed(0)}K`;
  return `฿${v.toFixed(0)}`;
}

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

// Distinct palette for top-product lines on the monthly revenue chart.
// Avoid the two blues used for the brand-total Actual/Master lines.
const PRODUCT_LINE_COLORS = [
  "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",
  "#e67e22", "#c0392b", "#27ae60", "#8e44ad", "#16a085",
];

export default function BrandAtLocationPage() {
  const params = useParams();
  const locationName = decodeURIComponent(params.location);
  const brandName = decodeURIComponent(params.brand);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedYears, setSelectedYears] = useState([CY]);
  const [trendData, setTrendData] = useState(null);
  const [itemTrendsData, setItemTrendsData] = useState(null);
  const [itemMetric, setItemMetric] = useState("sold_thb"); // "sold_thb" | "sold_master_thb" | "sold_qty"
  // Per-item Stock Bot summary at THIS location (shared across all brands at
  // the location — we just look up by item_code). First hit may need to wait
  // 10-30s while the bot computes; subsequent loads are instant (cached).
  const [botSummary, setBotSummary] = useState(null);
  const [topProductsOnChart, setTopProductsOnChart] = useState(5);
  const [granularity, setGranularity] = useState("monthly");
  const monthlyTrendChartRef = useRef(null);

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
      qs.set("location", locationName);
      qs.set("brand", brandName);
      qs.set("top_n", "100");
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/location_product_mix?${qs.toString()}`, { signal })
        .then((res) => {
          const d = res.data;
          if (d?.message === "data not ready") {
            setError("Data is still loading. Please try again in a moment.");
            return;
          }
          setData(d);
        })
        .catch((err) => {
          if (!isAbortError(err))
            setError(err.response?.data?.error || err.message);
        })
        .finally(() => setLoading(false));
    },
    [locationName, brandName]
  );

  const loadTrend = useCallback(
    (years, signal, gran) => {
      const qs = new URLSearchParams();
      qs.set("location", locationName);
      qs.set("brand", brandName);
      qs.set("granularity", gran);
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/brand_at_location_trend?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.message !== "data not ready") setTrendData(res.data);
        })
        .catch(() => {});
    },
    [locationName, brandName]
  );

  const loadItemTrends = useCallback(
    (years, signal, gran) => {
      const qs = new URLSearchParams();
      qs.set("location", locationName);
      qs.set("brand", brandName);
      qs.set("top_n", "200");
      qs.set("granularity", gran);
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/brand_at_location_item_trends?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.message !== "data not ready") setItemTrendsData(res.data);
        })
        .catch(() => {});
    },
    [locationName, brandName]
  );

  const loadBotSummary = useCallback(
    (signal) => {
      const qs = new URLSearchParams({ location: locationName });
      api
        .get(`/api/stock_bot/location_summary?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.status === "ok") setBotSummary(res.data);
        })
        .catch(() => {
          // Silent fail — Cap / Rec columns just render "—".
        });
    },
    [locationName]
  );

  useEffect(() => {
    const ctrl = new AbortController();
    loadData(selectedYears, ctrl.signal);
    loadTrend(selectedYears, ctrl.signal, granularity);
    loadItemTrends(selectedYears, ctrl.signal, granularity);
    loadBotSummary(ctrl.signal);
    return () => ctrl.abort();
  }, [loadData, loadTrend, loadItemTrends, loadBotSummary, selectedYears, granularity]);

  // Lookup helpers for the new Shelf Cap + Recommended Transfer columns
  // (mirrors the helpers on /dashboards/locations/[location]/page.js).
  const botItems = botSummary?.items || {};
  const getShelfCap = (row) => {
    const entry = botItems[row.item_code];
    return entry && entry.ai_suggested_planogram != null ? entry.ai_suggested_planogram : null;
  };
  const getNetTransfer = (row) => {
    const entry = botItems[row.item_code];
    return entry && entry.ai_recommended_transfer != null ? entry.ai_recommended_transfer : null;
  };
  const getD1Stock = (row) => {
    const entry = botItems[row.item_code];
    return entry && entry.d1_stock != null ? entry.d1_stock : null;
  };
  const getMonthlyVelocity = (row) => {
    const entry = botItems[row.item_code];
    return entry && entry.monthly_velocity != null ? entry.monthly_velocity : null;
  };
  const getCurrentPlanogram = (row) => {
    const entry = botItems[row.item_code];
    return entry && entry.current_planogram != null ? entry.current_planogram : null;
  };
  const fmtCurrentPlanogram = (row) => {
    const v = getCurrentPlanogram(row);
    return v == null
      ? <span className="text-gray-300">—</span>
      : <span className="text-gray-700 font-medium">{v}</span>;
  };
  const fmtNetTransfer = (v) => {
    if (v == null) return <span className="text-gray-300">—</span>;
    if (v === 0) return <span className="text-gray-500">0</span>;
    const color = v > 0 ? "text-green-700" : "text-red-700";
    const sign = v > 0 ? "+" : "";
    return <span className={`font-semibold ${color}`}>{sign}{v}</span>;
  };
  const fmtShelfCap = (row) => {
    const e = botItems[row.item_code];
    const v = e ? e.ai_suggested_planogram : null;
    if (v == null) return <span className="text-gray-300">—</span>;
    const conf = e.ai_confidence;
    const color =
      conf === "high" ? "text-green-700" : conf === "medium" ? "text-amber-600" : "text-gray-500";
    const title =
      `AI suggested (this month): ${v} units\n` +
      `Peak: ${e.ai_peak_planogram} in ${e.ai_peak_month}\n` +
      `Status: ${e.ai_status}\nConfidence: ${conf}`;
    return (
      <span title={title} className="inline-flex flex-col items-end leading-tight">
        <span className={`font-semibold ${color}`}>{v}</span>
        <span className="text-[11px] text-gray-400">peak {e.ai_peak_planogram} · {conf}</span>
      </span>
    );
  };
  const fmtD1Stock = (v) => {
    if (v == null) return <span className="text-gray-300">—</span>;
    if (v === 0) return <span className="text-red-600 font-medium">0</span>;
    return <span className="text-gray-700">{v}</span>;
  };
  const fmtMonthlyVelocity = (v) => {
    if (v == null) return <span className="text-gray-300">—</span>;
    const display = v < 10 ? v.toFixed(1) : Math.round(v).toString();
    return <span className="text-gray-700">{display}/mo</span>;
  };

  // Top N products for this brand at this location (already sorted by revenue
  // desc on the backend). Used as extra lines on the monthly revenue chart.
  const topProductsForChart = useMemo(() => {
    if (!itemTrendsData?.items?.length) return [];
    return itemTrendsData.items.slice(0, topProductsOnChart);
  }, [itemTrendsData, topProductsOnChart]);

  const trendChartData = useMemo(() => {
    if (!trendData?.months?.length) return [];

    // Pre-index per-product monthly data for quick merging
    const productMonthsByPeriod = {};
    for (const it of topProductsForChart) {
      for (const m of it.months || []) {
        (productMonthsByPeriod[m.period] ||= {})[it.item_code] = m.sold_thb;
      }
    }

    return trendData.months.map((m) => {
      const point = {
        period: m.period,
        "Revenue (Actual)": m.sold_thb,
        "Revenue (Master)": m.sold_master_thb,
      };
      const perProduct = productMonthsByPeriod[m.period] || {};
      for (const it of topProductsForChart) {
        // Use a label "<item_code> — <item_name>" trimmed, so the legend is readable
        const label = it.item_name
          ? `${it.item_code} — ${it.item_name.length > 28 ? it.item_name.slice(0, 26) + "\u2026" : it.item_name}`
          : it.item_code;
        point[label] = perProduct[it.item_code] ?? 0;
      }
      return point;
    });
  }, [trendData, topProductsForChart]);

  // Build the list of per-product line entries once so the render and the
  // data-key computation stay in sync.
  const productLineEntries = useMemo(() => {
    return topProductsForChart.map((it, i) => {
      const label = it.item_name
        ? `${it.item_code} — ${it.item_name.length > 28 ? it.item_name.slice(0, 26) + "\u2026" : it.item_name}`
        : it.item_code;
      return {
        key: it.item_code,
        dataKey: label,
        color: PRODUCT_LINE_COLORS[i % PRODUCT_LINE_COLORS.length],
      };
    });
  }, [topProductsForChart]);

  // Derive unit master_price from sold_master_thb/sold_qty (or onhand_thb/onhand_qty).
  // Backend computes these as qty × master_price, so division recovers the unit price exactly.
  const deriveMasterPrice = (r) => {
    if (r.master_price != null) return r.master_price;
    if (r.sold_qty > 0 && r.sold_master_thb != null) return r.sold_master_thb / r.sold_qty;
    if (r.onhand_qty > 0 && r.onhand_thb != null) return r.onhand_thb / r.onhand_qty;
    return null;
  };
  const topItems = (data?.top_items || []).map((r) => ({ ...r, master_price: deriveMasterPrice(r) }));
  const nonMovers = (data?.non_movers || []).map((r) => ({ ...r, master_price: deriveMasterPrice(r) }));

  // ABCDE classification for items at this location
  const abcdeByItem = useMemo(() => {
    if (!topItems.length) return {};
    const sorted = [...topItems].sort((a, b) => (b.sold_thb || 0) - (a.sold_thb || 0));
    const total = sorted.reduce((s, r) => s + (r.sold_thb || 0), 0);
    if (total <= 0) {
      const m = {};
      topItems.forEach((r) => { m[r.item_code] = "E"; });
      return m;
    }
    let cumSum = 0;
    const m = {};
    for (let i = 0; i < sorted.length; i++) {
      cumSum += sorted[i].sold_thb || 0;
      const pct = (cumSum / total) * 100;
      if (pct <= 50 || i === 0) m[sorted[i].item_code] = "A";
      else if (pct <= 80) m[sorted[i].item_code] = "B";
      else if (pct <= 95) m[sorted[i].item_code] = "C";
      else if (pct <= 99) m[sorted[i].item_code] = "D";
      else m[sorted[i].item_code] = "E";
    }
    return m;
  }, [topItems]);

  const totalRevenue = topItems.reduce((s, i) => s + (i.sold_thb || 0), 0);
  const totalRevenueMaster = topItems.reduce((s, i) => s + (i.sold_master_thb || 0), 0);
  const totalSoldQty = topItems.reduce((s, i) => s + (i.sold_qty || 0), 0);
  const totalDeadThb = data?.non_mover_total_thb || 0;

  const handleExport = () => {
    downloadCsvFromObjects(
      topItems.map((r) => ({
        "Item Code": r.item_code,
        "Item Name": r.item_name,
        "Master Price (THB)": r.master_price,
        "Revenue (THB, Actual Sales)": r.sold_thb,
        "Revenue (THB, Master)": r.sold_master_thb,
        "Sold Qty": r.sold_qty,
      })),
      `location_${locationName}_brand_${brandName}_${selectedYears.sort((a, b) => a - b).join("_")}.csv`
    );
  };

  return (
    <div className="max-w-screen-2xl mx-auto px-4 py-6">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-500 mb-4">
        <Link href="/" className="hover:underline">
          Home
        </Link>
        <span className="mx-1">/</span>
        <Link href="/dashboards/locations" className="hover:underline">
          Locations
        </Link>
        <span className="mx-1">/</span>
        <Link
          href={`/dashboards/locations/${encodeURIComponent(locationName)}`}
          className="hover:underline"
        >
          {locationName}
        </Link>
        <span className="mx-1">/</span>
        <span className="text-gray-800 font-medium">{brandName}</span>
      </nav>

      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--nichi-blue)]">
            {brandName}{" "}
            <span className="text-lg font-normal text-gray-500">
              @ {locationName}
            </span>
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Product performance for {selectedYears.sort((a, b) => a - b).join(", ")}. Revenue uses
            actual sales prices.{" "}
            <Link
              href={`/dashboards/brands/${encodeURIComponent(brandName)}`}
              className="text-[var(--nichi-blue)] hover:underline"
            >
              View full brand page &rarr;
            </Link>
          </p>
        </div>
        {topItems.length > 0 && (
          <button
            onClick={handleExport}
            className="px-4 py-2 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)] whitespace-nowrap"
          >
            Export CSV
          </button>
        )}
      </div>

      {/* Year filter */}
      <div className="flex items-center gap-2 flex-wrap mb-6">
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

      {loading && <LoadingSpinner />}
      {error && <ErrorBanner message={error} onRetry={() => loadData()} />}

      {!loading && !error && data && (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <KpiCard label="Products Sold" value={topItems.length} fmt={fmtQty} />
            <KpiCard
              label="Revenue (Actual Sales)"
              value={totalRevenue}
              fmt={fmtThb}
            />
            <KpiCard
              label="Revenue (Master)"
              value={totalRevenueMaster}
              fmt={fmtThb}
            />
            <KpiCard label="Total Sold Qty" value={totalSoldQty} fmt={fmtQty} />
            <KpiCard
              label="Dead Stock Value (Master)"
              value={totalDeadThb}
              fmt={fmtThb}
              color={totalDeadThb > 0 ? "text-red-600" : "text-green-700"}
            />
          </div>

          {/* Monthly Revenue Trend */}
          {trendChartData.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4 mb-6">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h2 className="text-base font-semibold text-gray-800">
                  {granularity === "weekly" ? "Weekly" : "Monthly"} Revenue — {brandName} at {locationName} ({selectedYears.sort((a, b) => a - b).join(", ")})
                </h2>
                <div className="flex items-center gap-3 flex-wrap">
                  <GranularityToggle value={granularity} onChange={setGranularity} />
                  <ChartDownloadToolbar
                    data={trendChartData}
                    filenameBase={`brand_${brandName}_at_${locationName}_${granularity}_revenue_${selectedYears.sort((a, b) => a - b).join("_")}`}
                    chartRef={monthlyTrendChartRef}
                  />
                  {itemTrendsData?.items?.length > 0 && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs text-gray-500">Top products:</span>
                      {[0, 3, 5, 10].map((n) => (
                        <button
                          key={n}
                          onClick={() => setTopProductsOnChart(n)}
                          className={`px-2.5 py-1 rounded text-xs font-medium ${
                            topProductsOnChart === n
                              ? "bg-[var(--nichi-blue)] text-white"
                              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                          }`}
                        >
                          {n === 0 ? "Off" : `Top ${n}`}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              {productLineEntries.length > 0 && (
                <p className="text-xs text-gray-500 mb-2">
                  Thick blue lines = brand totals (Actual / Master). Colored lines = per-product Actual Revenue for the top {productLineEntries.length} products.
                </p>
              )}
              <div ref={monthlyTrendChartRef}>
              <ResponsiveContainer width="100%" height={360}>
                <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={chartThb} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => fmtThb(v)} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="Revenue (Actual)" stroke="#1a3a8f" strokeWidth={3} dot={false} />
                  <Line type="monotone" dataKey="Revenue (Master)" stroke="#2d4ea3" strokeWidth={3} dot={false} strokeDasharray="5 5" />
                  {productLineEntries.map((p) => (
                    <Line
                      key={p.key}
                      type="monotone"
                      dataKey={p.dataKey}
                      stroke={p.color}
                      strokeWidth={1.5}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Selling items table */}
          <div className="bg-white rounded-lg shadow border overflow-hidden mb-6">
            <div className="px-4 py-3 border-b bg-gray-50">
              <h2 className="font-semibold text-gray-800">
                Selling Products ({topItems.length})
              </h2>
            </div>
            <SortableTable
              columns={[
                {
                  key: "item_code",
                  label: "Item Code",
                  linkFn: (row) =>
                    `/dashboards/item-detail/${encodeURIComponent(row.item_code)}/${encodeURIComponent(locationName)}`,
                },
                { key: "item_name", label: "Item Name" },
                {
                  key: "abcde_class",
                  label: "Tier",
                  render: (v) => <AbcdeBadge tier={v} context="at this location" />,
                  tooltip: "ABCDE tier by revenue at this location",
                },
                {
                  key: "master_price",
                  label: "Master Price (THB)",
                  fmt: fmtThb,
                  tooltip: "Unit list price from Item Master",
                },
                {
                  key: "sold_thb",
                  label: "Revenue (THB, Actual Sales)",
                  fmt: fmtThb,
                },
                {
                  key: "sold_master_thb",
                  label: "Revenue (THB, Master)",
                  fmt: fmtThb,
                },
                { key: "sold_qty", label: "Sold Qty", fmt: fmtQty },
                {
                  key: "onhand_qty",
                  label: "On-Hand Qty",
                  fmt: fmtQty,
                  tooltip: "Current on-hand units of this SKU at this location. 0 = currently stocked out here.",
                },
                {
                  key: "onhand_thb",
                  label: "On-Hand Value (THB @ Master)",
                  fmt: fmtThb,
                },
                {
                  key: "_d1_stock",
                  label: "Stock at D1 Warehouse",
                  fmt: () => null,
                  render: (_v, row) => fmtD1Stock(getD1Stock(row)),
                  tooltip: "Current on-hand units of this SKU at the D1 main warehouse — the typical source of transfers. 0 (red) = D1 is empty, no transfer can be recommended.",
                },
                {
                  key: "_monthly_velocity",
                  label: "Monthly Velocity",
                  fmt: () => null,
                  render: (_v, row) => fmtMonthlyVelocity(getMonthlyVelocity(row)),
                  tooltip: "Average units sold per month at this location (recent 90-day window). Note: the AI Suggested Planogram uses full-history, stockout-corrected demand — not this raw recent velocity.",
                },
                {
                  key: "_current_planogram",
                  label: "Current Planogram",
                  fmt: () => null,
                  render: (_v, row) => fmtCurrentPlanogram(row),
                  tooltip: "The planogram minimum currently set for this SKU here (from the planogram page). — = not set. Compare with the AI Suggested Planogram to the right.",
                },
                {
                  key: "_shelf_cap",
                  label: "AI Suggested Planogram",
                  fmt: () => null,
                  render: (_v, row) => fmtShelfCap(row),
                  tooltip: "AI-suggested shelf target (units) for the current month, from the demand-ceiling engine: unconstrained demand (corrected for past stockouts) × this location's channel seasonality. Hover for the peak month + confidence.",
                },
                {
                  key: "_net_transfer",
                  label: "AI Recommended Transfer",
                  fmt: () => null,
                  render: (_v, row) => fmtNetTransfer(getNetTransfer(row)),
                  tooltip: "Units to move to reach the AI Suggested Planogram: positive = bring IN from D1 (capped by D1 stock), negative = overstocked (move OUT), 0 = at target or D1 empty, — = no AI target for this SKU here.",
                },
              ]}
              data={topItems.map((r) => ({
                ...r,
                abcde_class: abcdeByItem[r.item_code] || "E",
              }))}
              defaultSort="sold_thb"
              defaultDir="desc"
              pageSize={50}
            />
          </div>

          {/* Per-product monthly breakdown */}
          {itemTrendsData?.items?.length > 0 && itemTrendsData.periods?.length > 0 && (() => {
            const metricMeta = {
              sold_thb: { label: "Revenue (THB, Actual Sales)", fmt: fmtThb, totalKey: "total_sold_thb", avgKey: "avg_sold_thb_per_month" },
              sold_master_thb: { label: "Revenue (THB, Master)", fmt: fmtThb, totalKey: "total_sold_master_thb", avgKey: "avg_sold_master_thb_per_month" },
              sold_qty: { label: "Sold Qty", fmt: fmtQty, totalKey: "total_sold_qty", avgKey: "avg_sold_qty_per_month" },
            };
            const mm = metricMeta[itemMetric];
            const periods = itemTrendsData.periods;
            const items = itemTrendsData.items;
            const totalMonths = itemTrendsData.total_months || periods.length;

            const handleItemMonthlyExport = () => {
              const header = ["Item Code", "Item Name", ...periods, "Total", "Avg/Month"];
              const rows = items.map((it) => [
                it.item_code, it.item_name,
                ...it.months.map((m) => m[itemMetric]),
                it[mm.totalKey], it[mm.avgKey],
              ]);
              const metricSlug = itemMetric === "sold_qty" ? "qty" : itemMetric === "sold_master_thb" ? "rev_master" : "rev_actual";
              downloadCsv(
                `${brandName}_at_${locationName}_items_monthly_${metricSlug}_${selectedYears.sort((a, b) => a - b).join("_")}.csv`,
                header, rows,
              );
            };

            return (
              <div className="bg-white rounded-lg shadow border overflow-hidden mb-6">
                <div className="px-4 py-3 border-b bg-gray-50">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="font-semibold text-gray-800">
                        Monthly Sales by Product ({items.length} products × {periods.length} months)
                      </h2>
                      <p className="text-xs text-gray-500 mt-0.5">
                        Per-item monthly sales at {locationName} for {selectedYears.sort((a, b) => a - b).join(", ")}.
                        Avg/Month = Total &divide; {totalMonths} months.
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs text-gray-500">Metric:</span>
                      {[
                        { k: "sold_thb", label: "Revenue (Actual)" },
                        { k: "sold_master_thb", label: "Revenue (Master)" },
                        { k: "sold_qty", label: "Qty" },
                      ].map(({ k, label }) => (
                        <button
                          key={k}
                          onClick={() => setItemMetric(k)}
                          className={`px-2.5 py-1 rounded text-xs font-medium ${
                            itemMetric === k
                              ? "bg-[var(--nichi-blue)] text-white"
                              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                      <button
                        onClick={handleItemMonthlyExport}
                        className="px-3 py-1 rounded text-xs bg-[var(--nichi-blue)] text-white hover:bg-[var(--nichi-blue-dark)]"
                      >
                        CSV
                      </button>
                    </div>
                  </div>
                </div>
                <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                  <table className="min-w-full text-xs">
                    <thead className="sticky top-0 z-10">
                      <tr className="bg-gray-50 border-b">
                        <th className="px-3 py-2 text-left font-semibold text-gray-700 sticky left-0 bg-gray-50 z-20 whitespace-nowrap">
                          Item Code
                        </th>
                        <th className="px-3 py-2 text-left font-semibold text-gray-700 sticky left-[100px] bg-gray-50 z-20 whitespace-nowrap max-w-[220px]">
                          Item Name
                        </th>
                        {periods.map((p) => (
                          <th key={p} className="px-2 py-2 text-right font-semibold text-gray-700 whitespace-nowrap">
                            {p}
                          </th>
                        ))}
                        <th className="px-3 py-2 text-right font-semibold text-gray-700 whitespace-nowrap bg-gray-100">
                          Total
                        </th>
                        <th className="px-3 py-2 text-right font-semibold text-blue-700 bg-blue-50 whitespace-nowrap">
                          Avg/Month
                        </th>
                      </tr>
                      <tr className="bg-white border-b">
                        <th className="px-3 py-2 text-xs text-gray-400 font-normal sticky left-0 bg-white z-20" colSpan={2}>
                          {mm.label}
                        </th>
                        <th className="px-2 py-2" colSpan={periods.length + 2}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it, i) => (
                        <tr key={it.item_code} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                          <td className="px-3 py-2 font-medium sticky left-0 bg-inherit z-10 whitespace-nowrap">
                            <Link
                              href={`/dashboards/item-detail/${encodeURIComponent(it.item_code)}/${encodeURIComponent(locationName)}`}
                              className="text-[var(--nichi-blue)] hover:underline"
                            >
                              {it.item_code}
                            </Link>
                          </td>
                          <td className="px-3 py-2 sticky left-[100px] bg-inherit z-10 whitespace-nowrap max-w-[220px] overflow-hidden text-ellipsis" title={it.item_name}>
                            {it.item_name}
                          </td>
                          {it.months.map((m) => (
                            <td key={m.period} className="px-2 py-2 text-right whitespace-nowrap">
                              {m[itemMetric] > 0 ? mm.fmt(m[itemMetric]) : <span className="text-gray-300">—</span>}
                            </td>
                          ))}
                          <td className="px-3 py-2 text-right font-semibold whitespace-nowrap bg-gray-50">
                            {mm.fmt(it[mm.totalKey])}
                          </td>
                          <td className="px-3 py-2 text-right font-semibold text-blue-700 bg-blue-50 whitespace-nowrap">
                            {mm.fmt(it[mm.avgKey])}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })()}

          {/* Non-movers */}
          {nonMovers.length > 0 && (
            <div className="bg-white rounded-lg shadow border overflow-hidden">
              <div className="px-4 py-3 border-b bg-red-50">
                <h2 className="font-semibold text-red-800">
                  Non-Moving Items ({nonMovers.length}) &mdash; On-Hand but Zero
                  Recent Sales
                </h2>
              </div>
              <SortableTable
                columns={[
                  {
                    key: "item_code",
                    label: "Item Code",
                    linkFn: (row) =>
                      `/dashboards/item-detail/${encodeURIComponent(row.item_code)}/${encodeURIComponent(locationName)}`,
                  },
                  { key: "onhand_qty", label: "On-Hand Qty", fmt: fmtQty },
                  {
                    key: "master_price",
                    label: "Master Price (THB)",
                    fmt: fmtThb,
                    tooltip: "Unit list price from Item Master",
                  },
                  {
                    key: "onhand_thb",
                    label: "On-Hand Value (THB @ Master Price)",
                    fmt: fmtThb,
                  },
                  {
                    key: "_d1_stock",
                    label: "Stock at D1 Warehouse",
                    fmt: () => null,
                    render: (_v, row) => fmtD1Stock(getD1Stock(row)),
                    tooltip: "Current on-hand units at the D1 main warehouse — typical source of transfers.",
                  },
                  {
                    key: "_monthly_velocity",
                    label: "Monthly Velocity",
                    fmt: () => null,
                    render: (_v, row) => fmtMonthlyVelocity(getMonthlyVelocity(row)),
                    tooltip: "Average units sold per month at this location (recent 90-day window). Note: the AI Suggested Planogram uses full-history, stockout-corrected demand — not this raw recent velocity.",
                  },
                  {
                    key: "_current_planogram",
                    label: "Current Planogram",
                    fmt: () => null,
                    render: (_v, row) => fmtCurrentPlanogram(row),
                    tooltip: "The planogram minimum currently set for this SKU here (from the planogram page). — = not set.",
                  },
                  {
                    key: "_shelf_cap",
                    label: "AI Suggested Planogram",
                    fmt: () => null,
                    render: (_v, row) => fmtShelfCap(row),
                    tooltip: "AI-suggested shelf target (units) for the current month, from the demand-ceiling engine. Hover for the peak month + confidence.",
                  },
                  {
                    key: "_net_transfer",
                    label: "AI Recommended Transfer",
                    fmt: () => null,
                    render: (_v, row) => fmtNetTransfer(getNetTransfer(row)),
                    tooltip: "Units to move to reach the AI Suggested Planogram (positive = bring IN from D1, negative = overstocked).",
                  },
                ]}
                data={nonMovers}
                defaultSort="onhand_thb"
                defaultDir="desc"
                pageSize={50}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}

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
