"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import api, { isAbortError } from "@/utils/api";
import SortableTable from "@/components/SortableTable";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBanner from "@/components/ErrorBanner";
import AbcdeBadge from "@/components/AbcdeBadge";
import GranularityToggle from "@/components/GranularityToggle";
import ChartDownloadToolbar from "@/components/ChartDownloadToolbar";
import RecommendationPanel from "@/components/RecommendationCard";
import ProductMarketFitPanel from "@/components/ProductMarketFitPanel";
import { fmtThb, fmtQty, fmtPct, fmtRatio } from "@/utils/formatters";
import { downloadCsv, downloadCsvFromObjects } from "@/utils/csvExport";

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

// Distinct palette for top-brand lines on the monthly revenue chart.
// Avoid the two blues used by the total Actual/Master lines.
const BRAND_LINE_COLORS = [
  "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",
  "#e67e22", "#c0392b", "#27ae60", "#8e44ad", "#16a085",
];

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

function chartThb(v) {
  if (v == null) return "";
  if (Math.abs(v) >= 1e6) return `\u0E3F${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `\u0E3F${(v / 1e3).toFixed(0)}K`;
  return `\u0E3F${v.toFixed(0)}`;
}

/**
 * Reusable matrix table: rows (brand or item) × months, with per-row Total and
 * Avg/Month columns. Toggle between Revenue (Actual), Revenue (Master), and Qty.
 *
 * Backend provides each row with:
 *   rowKey (e.g. "brand" or "item_code"), months: [{period, sold_thb, sold_master_thb, sold_qty}],
 *   total_sold_thb, total_sold_master_thb, total_sold_qty,
 *   avg_sold_thb_per_month, avg_sold_master_thb_per_month, avg_sold_qty_per_month
 */
function MonthlyMatrix({
  title, subtitle, rows, periods, totalMonths, metric, setMetric,
  rowKey, rowKeyLabel, renderRowKey, extraCol, csvFilenameBase, yearLabel,
}) {
  const metricMeta = {
    sold_thb: { label: "Revenue (THB, Actual Sales)", fmt: fmtThb,
      totalKey: "total_sold_thb", avgKey: "avg_sold_thb_per_month" },
    sold_master_thb: { label: "Revenue (THB, Master)", fmt: fmtThb,
      totalKey: "total_sold_master_thb", avgKey: "avg_sold_master_thb_per_month" },
    sold_qty: { label: "Sold Qty", fmt: fmtQty,
      totalKey: "total_sold_qty", avgKey: "avg_sold_qty_per_month" },
  };
  const mm = metricMeta[metric];

  const handleExport = () => {
    const header = [
      rowKeyLabel,
      ...(extraCol ? [extraCol.label] : []),
      ...periods, "Total", "Avg/Month",
    ];
    const data = rows.map((r) => [
      r[rowKey],
      ...(extraCol ? [r[extraCol.key]] : []),
      ...r.months.map((m) => m[metric]),
      r[mm.totalKey], r[mm.avgKey],
    ]);
    const metricSlug = metric === "sold_qty" ? "qty" : metric === "sold_master_thb" ? "rev_master" : "rev_actual";
    downloadCsv(`${csvFilenameBase}_${metricSlug}_${yearLabel}.csv`, header, data);
  };

  return (
    <div className="bg-white rounded-lg shadow border overflow-hidden mb-6">
      <div className="px-4 py-3 border-b bg-gray-50">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-semibold text-gray-800">{title}</h2>
            {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
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
                onClick={() => setMetric(k)}
                className={`px-2.5 py-1 rounded text-xs font-medium ${
                  metric === k
                    ? "bg-[var(--nichi-blue)] text-white"
                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                }`}
              >
                {label}
              </button>
            ))}
            <button
              onClick={handleExport}
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
                {rowKeyLabel}
              </th>
              {extraCol && (
                <th className="px-3 py-2 text-left font-semibold text-gray-700 bg-gray-50 whitespace-nowrap max-w-[220px]">
                  {extraCol.label}
                </th>
              )}
              {periods.map((p) => (
                <th key={p} className="px-2 py-2 text-right font-semibold text-gray-700 whitespace-nowrap">{p}</th>
              ))}
              <th className="px-3 py-2 text-right font-semibold text-gray-700 whitespace-nowrap bg-gray-100">Total</th>
              <th className="px-3 py-2 text-right font-semibold text-blue-700 bg-blue-50 whitespace-nowrap">Avg/Month</th>
            </tr>
            <tr className="bg-white border-b">
              <th className="px-3 py-2 text-xs text-gray-400 font-normal sticky left-0 bg-white z-20" colSpan={(extraCol ? 2 : 1) + periods.length + 2}>
                {mm.label}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r[rowKey]} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                <td className="px-3 py-2 font-medium sticky left-0 bg-inherit z-10 whitespace-nowrap">
                  {renderRowKey ? renderRowKey(r) : r[rowKey]}
                </td>
                {extraCol && (
                  <td className="px-3 py-2 whitespace-nowrap max-w-[220px] overflow-hidden text-ellipsis" title={r[extraCol.key]}>
                    {r[extraCol.key]}
                  </td>
                )}
                {r.months.map((m) => (
                  <td key={m.period} className="px-2 py-2 text-right whitespace-nowrap">
                    {m[metric] > 0 ? mm.fmt(m[metric]) : <span className="text-gray-300">—</span>}
                  </td>
                ))}
                <td className="px-3 py-2 text-right font-semibold whitespace-nowrap bg-gray-50">
                  {mm.fmt(r[mm.totalKey])}
                </td>
                <td className="px-3 py-2 text-right font-semibold text-blue-700 bg-blue-50 whitespace-nowrap">
                  {mm.fmt(r[mm.avgKey])}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const BRAND_COLUMNS = [
  {
    key: "brand",
    label: "Brand",
    render: (val, row) => {
      const params = typeof window !== "undefined" ? window.__loc_param : "";
      return (
        <Link
          href={`/dashboards/locations/${encodeURIComponent(params || row.__location)}/` +
            encodeURIComponent(val)}
          className="text-[var(--nichi-blue)] hover:underline font-medium"
        >
          {val}
        </Link>
      );
    },
  },
  {
    key: "loc_sold_thb",
    label: "Revenue Here (THB, Actual Sales)",
    fmt: fmtThb,
  },
  {
    key: "loc_sold_master_thb",
    label: "Revenue Here (THB, Master)",
    fmt: fmtThb,
    tooltip: "Sold Qty × Master (list) Price at this location",
  },
  {
    // Derived client-side from loc_sold_thb (actual) and loc_sold_master_thb (master).
    // = (Master − Actual) ÷ Master × 100.
    // Tells you the average discount % relative to list price at this location.
    key: "avg_sale_discount_pct",
    label: "Avg Sale Discount %",
    fmt: fmtPct,
    tooltip:
      "(Master Revenue − Actual Revenue) ÷ Master Revenue × 100. " +
      "Average discount off list price at this location. Higher = more discounting.",
  },
  {
    key: "company_sold_thb",
    label: "Company Revenue (THB, Actual Sales)",
    fmt: fmtThb,
  },
  {
    key: "loc_share_pct",
    label: "Location Share %",
    fmt: fmtPct,
    tooltip: "This location's revenue as % of company-wide revenue for this brand",
  },
  {
    key: "loc_onhand_thb",
    label: "On-Hand Here (THB @ Master Price)",
    fmt: fmtThb,
  },
  {
    key: "sell_through",
    label: "Sell-Through Ratio",
    fmt: (v) => fmtRatio(v, "x"),
    tooltip: "Revenue / On-Hand value. Higher = selling faster than stocking.",
  },
];

export default function LocationDetailPage() {
  const params = useParams();
  const locationName = decodeURIComponent(params.location);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedYears, setSelectedYears] = useState([CY]);
  const [trendData, setTrendData] = useState(null);
  const [abcdeTier, setAbcdeTier] = useState(null);
  const [brandTrends, setBrandTrends] = useState(null);
  const [itemTrends, setItemTrends] = useState(null);
  const [pmfData, setPmfData] = useState(null);
  const [pmfLoading, setPmfLoading] = useState(false);
  const [pmfError, setPmfError] = useState(null);
  // Per-item Stock Bot summary at this location: {item_code: {shelf_cap,
  // net_transfer, transfers_in_qty, transfers_out_qty, ...}}.
  // First hit may take 10-30s (computes the bot plan); subsequent hits
  // are instant (cached).
  const [botSummary, setBotSummary] = useState(null);
  const [brandMetric, setBrandMetric] = useState("sold_thb");
  const [itemMetric, setItemMetric] = useState("sold_thb");
  const [topBrandsOnChart, setTopBrandsOnChart] = useState(5);
  const [granularity, setGranularity] = useState("monthly");
  const monthlyTrendChartRef = useRef(null);
  const topBrandsChartRef = useRef(null);

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
      qs.set("top_n", "50");
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
    [locationName]
  );

  const loadTrend = useCallback(
    (years, signal, gran) => {
      const qs = new URLSearchParams();
      qs.set("location", locationName);
      qs.set("granularity", gran);
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/location_trends?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.message !== "data not ready") setTrendData(res.data);
        })
        .catch(() => {});
    },
    [locationName]
  );

  const loadAbcde = useCallback(
    (years, signal) => {
      const qs = new URLSearchParams();
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/location_performance?${qs.toString()}`, { signal })
        .then((res) => {
          const locs = res.data?.locations || [];
          const match = locs.find((l) => l.location === locationName);
          setAbcdeTier(match?.abcde_class || null);
        })
        .catch(() => {});
    },
    [locationName]
  );

  const loadBrandTrends = useCallback(
    (years, signal, gran) => {
      const qs = new URLSearchParams();
      qs.set("location", locationName);
      qs.set("top_n", "50");
      qs.set("granularity", gran);
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/location_brand_trends?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.message !== "data not ready") setBrandTrends(res.data);
        })
        .catch(() => {});
    },
    [locationName]
  );

  const loadItemTrends = useCallback(
    (years, signal, gran) => {
      const qs = new URLSearchParams();
      qs.set("location", locationName);
      qs.set("top_n", "100");
      qs.set("granularity", gran);
      years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/location_item_trends?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.message !== "data not ready") setItemTrends(res.data);
        })
        .catch(() => {});
    },
    [locationName]
  );

  const loadPmf = useCallback(
    (years, signal) => {
      const qs = new URLSearchParams();
      qs.set("location", locationName);
      years.forEach((y) => qs.append("year_list", String(y)));
      setPmfLoading(true);
      setPmfError(null);
      api
        .get(`/api/product_market_fit?${qs.toString()}`, { signal })
        .then((res) => {
          if (res.data?.message !== "data not ready") setPmfData(res.data);
        })
        .catch((err) => {
          if (!isAbortError(err))
            setPmfError(err.response?.data?.error || err.message);
        })
        .finally(() => setPmfLoading(false));
    },
    [locationName]
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
          // Silent fail — the new Cap / Rec columns just stay blank.
        });
    },
    [locationName]
  );

  useEffect(() => {
    const ctrl = new AbortController();
    loadData(selectedYears, ctrl.signal);
    loadTrend(selectedYears, ctrl.signal, granularity);
    loadAbcde(selectedYears, ctrl.signal);
    loadBrandTrends(selectedYears, ctrl.signal, granularity);
    loadItemTrends(selectedYears, ctrl.signal, granularity);
    loadPmf(selectedYears, ctrl.signal);
    loadBotSummary(ctrl.signal);
    return () => ctrl.abort();
  }, [loadData, loadTrend, loadAbcde, loadBrandTrends, loadItemTrends, loadPmf, loadBotSummary, selectedYears, granularity]);

  // Lookup helpers for the new "Shelf Cap" and "Recommended Transfer" columns.
  // The Stock Bot only has data for items it considered — non-bot items just
  // show "—".
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
    // Show 1 decimal if < 10, integer otherwise — small numbers benefit
    // from precision, big ones don't
    const display = v < 10 ? v.toFixed(1) : Math.round(v).toString();
    return <span className="text-gray-700">{display}/mo</span>;
  };

  // Two reusable column definitions for the bot-derived data. Inserted
  // after sales/onhand columns on each product table so the manager can
  // see "what's recommended for this item at this store" alongside the
  // demand/supply context.
  const getCurrentPlanogram = (row) => {
    const entry = botItems[row.item_code];
    return entry && entry.current_planogram != null ? entry.current_planogram : null;
  };
  const CURRENT_PLANOGRAM_COL = {
    key: "_current_planogram",
    label: "Current Planogram",
    fmt: () => null,
    render: (_v, row) => {
      const v = getCurrentPlanogram(row);
      return v == null
        ? <span className="text-gray-300">—</span>
        : <span className="text-gray-700 font-medium">{v}</span>;
    },
    tooltip: "The planogram minimum (Min Units on Shelf) currently set for this SKU here, from the planogram page. — = not set. Compare with the AI Suggested Planogram to the right.",
  };
  const SHELF_CAP_COL = {
    key: "_shelf_cap",
    label: "AI Suggested Planogram",
    fmt: () => null,   // we use renderCell below
    render: (_v, row) => fmtShelfCap(row),
    tooltip: "AI-suggested shelf target (units) for the current month, from the demand-ceiling engine: unconstrained demand (corrected for past stockouts) × this location's channel seasonality. Hover a value for the peak month + confidence. — = not a managed-shelf item here.",
  };
  const NET_TRANSFER_COL = {
    key: "_net_transfer",
    label: "AI Recommended Transfer",
    fmt: () => null,
    render: (_v, row) => fmtNetTransfer(getNetTransfer(row)),
    tooltip: "Units to move to reach the AI Suggested Planogram: positive = bring IN from D1 (capped by D1 stock), negative = overstocked (move OUT), 0 = at target or D1 empty, — = no AI target for this SKU here.",
  };
  const D1_STOCK_COL = {
    key: "_d1_stock",
    label: "Stock at D1 Warehouse",
    fmt: () => null,
    render: (_v, row) => fmtD1Stock(getD1Stock(row)),
    tooltip: "Current on-hand units of this SKU at the D1 main warehouse — the typical source of transfers. 0 (red) = D1 is empty, no transfer can be recommended; — = data unknown.",
  };
  const MONTHLY_VELOCITY_COL = {
    key: "_monthly_velocity",
    label: "Monthly Velocity",
    fmt: () => null,
    render: (_v, row) => fmtMonthlyVelocity(getMonthlyVelocity(row)),
    tooltip: "Average units sold per month at this location (recent 90-day window). Note: the AI Suggested Planogram uses full-history, stockout-corrected demand — not this raw recent velocity — so the two can differ for items that were under-stocked.",
  };

  // Top-N brands at this location by total revenue — rendered as extra lines
  // on the monthly revenue trend chart alongside the location totals.
  const topBrandsForChart = useMemo(() => {
    if (!brandTrends?.brands?.length) return [];
    return brandTrends.brands.slice(0, topBrandsOnChart);
  }, [brandTrends, topBrandsOnChart]);

  const trendChartData = useMemo(() => {
    if (!trendData?.trends?.length) return [];
    const t = trendData.trends[0];

    // Pre-index brand monthly data by period for quick merging
    const brandMonthsByPeriod = {};
    for (const b of topBrandsForChart) {
      for (const m of b.months || []) {
        (brandMonthsByPeriod[m.period] ||= {})[b.brand] = m.sold_thb;
      }
    }

    return (t.months || []).map((m) => {
      const point = {
        period: m.period,
        // If the latest month is partial, show the running-rate projection
        // so it's comparable to prior full months. The running_rate_* fields
        // are set by the backend annotate_monthly_series helper.
        "Revenue (Actual)": m.is_partial ? m.running_rate_sold_thb : m.sold_thb,
        "Revenue (Master)": m.is_partial ? m.running_rate_sold_master_thb : m.sold_master_thb,
        is_partial: !!m.is_partial,
        days_elapsed: m.days_elapsed,
        days_in_month: m.days_in_month,
      };
      // Add one data key per top brand (using the brand name as the key)
      const perBrand = brandMonthsByPeriod[m.period] || {};
      for (const b of topBrandsForChart) {
        point[b.brand] = perBrand[b.brand] ?? 0;
      }
      return point;
    });
  }, [trendData, topBrandsForChart]);

  const partialNote = trendChartData.length > 0 && trendChartData[trendChartData.length - 1]?.is_partial
    ? `Latest month projected from ${trendChartData[trendChartData.length - 1].days_elapsed}/${trendChartData[trendChartData.length - 1].days_in_month} days`
    : null;

  const brandHeatmap = (data?.brand_heatmap || []).map((b) => {
    const master = Number(b.loc_sold_master_thb) || 0;
    const actual = Number(b.loc_sold_thb) || 0;
    // Discount % = (Master − Actual) ÷ Master × 100.
    // Null when there's no master revenue to compare against (so the formatter
    // shows an em-dash instead of a misleading 0%).
    const avg_sale_discount_pct =
      master > 0 ? ((master - actual) / master) * 100 : null;
    return {
      ...b,
      avg_sale_discount_pct,
      __location: locationName,
    };
  });
  const topItems = data?.top_items || [];

  const chartData = [...(data?.top_brands || [])]
    .slice(0, 15)
    .map((b) => ({ name: b.brand, revenue: b.sold_thb }));

  const handleExportBrands = () => {
    downloadCsvFromObjects(
      brandHeatmap.map((r) => ({
        Brand: r.brand,
        "Revenue Here (THB, Actual)": r.loc_sold_thb,
        "Revenue Here (THB, Master)": r.loc_sold_master_thb,
        "Avg Sale Discount %": r.avg_sale_discount_pct,
        "Company Revenue (THB)": r.company_sold_thb,
        "Location Share %": r.loc_share_pct,
        "On-Hand Here (THB @ Master Price)": r.loc_onhand_thb,
        "Sell-Through Ratio": r.sell_through,
      })),
      `location_${locationName}_brands_${selectedYears.sort((a, b) => a - b).join("_")}.csv`
    );
  };

  // Brand column with proper location context
  const brandColumnsWithLinks = BRAND_COLUMNS.map((col) =>
    col.key === "brand"
      ? {
          ...col,
          linkFn: (row) =>
            `/dashboards/locations/${encodeURIComponent(locationName)}/${encodeURIComponent(row.brand)}`,
        }
      : col
  );

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
        <span className="text-gray-800 font-medium">{locationName}</span>
      </nav>

      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--nichi-blue)] flex items-center gap-2">
            {locationName}
            {abcdeTier && <AbcdeBadge tier={abcdeTier} context="by company revenue" />}
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Brand performance for {selectedYears.sort((a, b) => a - b).join(", ")}. Click a brand to see
            products. Revenue uses actual sales; on-hand at Master Price.
          </p>
        </div>
        {brandHeatmap.length > 0 && (
          <button
            onClick={handleExportBrands}
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

      {/* Recommendations */}
      <RecommendationPanel context="location" name={locationName} years={selectedYears} />

      {!loading && !error && data && (
        <>
          {/* Avg monthly sales KPIs — top of page */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <KpiCard
              label={`Avg Monthly Sales — Actual (${data.active_months || 0} active months)`}
              value={data.avg_monthly_sold_thb}
              fmt={fmtThb}
              color="text-[var(--nichi-blue)]"
            />
            <KpiCard
              label={`Avg Monthly Sales — Master (${data.active_months || 0} active months)`}
              value={data.avg_monthly_sold_master_thb}
              fmt={fmtThb}
              color="text-[var(--nichi-blue-light)]"
            />
          </div>

          {/* KPI summary */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KpiCard
              label="Brands Sold Here"
              value={(data.top_brands || []).length}
              fmt={fmtQty}
            />
            <KpiCard
              label="Top Items Sold"
              value={topItems.length}
              fmt={fmtQty}
            />
            <KpiCard
              label="Non-Moving Items"
              value={(data.non_movers || []).length}
              fmt={fmtQty}
            />
            <KpiCard
              label="Dead Stock Value (Master)"
              value={data.non_mover_total_thb}
              fmt={fmtThb}
              color="text-red-600"
            />
          </div>

          {/* Product-Market Fit — which brands, lines, and price points
              over- or under-index at this location. Placed up top so a
              manager sees the strategic story before drilling into tables. */}
          <ProductMarketFitPanel
            data={pmfData}
            loading={pmfLoading}
            error={pmfError}
          />

          {/* Monthly Revenue Trend */}
          {trendChartData.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4 mb-6">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h2 className="text-base font-semibold text-gray-800">
                  {granularity === "weekly" ? "Weekly" : "Monthly"} Revenue Trend — {locationName} ({selectedYears.sort((a, b) => a - b).join(", ")})
                </h2>
                <div className="flex items-center gap-3 flex-wrap">
                  <GranularityToggle value={granularity} onChange={setGranularity} />
                  <ChartDownloadToolbar
                    data={trendChartData}
                    filenameBase={`location_${locationName}_${granularity}_revenue_trend_${selectedYears.sort((a, b) => a - b).join("_")}`}
                    chartRef={monthlyTrendChartRef}
                  />
                  {brandTrends?.brands?.length > 0 && (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs text-gray-500">Top brands:</span>
                      {[0, 3, 5, 10].map((n) => (
                        <button
                          key={n}
                          onClick={() => setTopBrandsOnChart(n)}
                          className={`px-2.5 py-1 rounded text-xs font-medium ${
                            topBrandsOnChart === n
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
              {partialNote && (
                <p className="text-xs text-amber-700 -mt-2 mb-2">
                  ⓘ {partialNote} → latest data point shown as full-month running-rate projection for fair comparison
                </p>
              )}
              {topBrandsForChart.length > 0 && (
                <p className="text-xs text-gray-500 mb-2">
                  Thick blue lines = location totals (Actual / Master). Colored lines = per-brand Actual Revenue at this location.
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
                  {topBrandsForChart.map((b, i) => (
                    <Line
                      key={b.brand}
                      type="monotone"
                      dataKey={b.brand}
                      stroke={BRAND_LINE_COLORS[i % BRAND_LINE_COLORS.length]}
                      strokeWidth={1.5}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Top brands chart */}
          {chartData.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4 mb-6">
              <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
                <h2 className="text-base font-semibold text-gray-800">
                  Top Brands by Revenue ({selectedYears.sort((a, b) => a - b).join(", ")})
                </h2>
                <ChartDownloadToolbar
                  data={chartData}
                  filenameBase={`location_${locationName}_top_brands_${selectedYears.sort((a, b) => a - b).join("_")}`}
                  chartRef={topBrandsChartRef}
                  csvColumns={["name", "revenue"]}
                />
              </div>
              <div ref={topBrandsChartRef}>
              <ResponsiveContainer width="100%" height={300}>
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
                  <Tooltip formatter={(v) => fmtThb(v)} />
                  <Bar dataKey="revenue" name="Revenue (Actual)" fill="var(--nichi-blue)" />
                </BarChart>
              </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Brand heatmap table */}
          <div className="bg-white rounded-lg shadow border overflow-hidden mb-6">
            <div className="px-4 py-3 border-b bg-gray-50">
              <h2 className="font-semibold text-gray-800">
                Brand Performance at {locationName}
              </h2>
            </div>
            <SortableTable
              columns={brandColumnsWithLinks}
              data={brandHeatmap}
              defaultSort="loc_sold_thb"
              defaultDir="desc"
              pageSize={50}
            />
          </div>

          {/* Monthly Brand Revenue matrix */}
          {brandTrends?.brands?.length > 0 && brandTrends.periods?.length > 0 && (
            <MonthlyMatrix
              title={`Monthly Sales by Brand at ${locationName}`}
              subtitle={`Per-brand monthly sales for ${selectedYears.sort((a, b) => a - b).join(", ")}. Avg/Month = Total \u00f7 ${brandTrends.total_months} months.`}
              rows={brandTrends.brands}
              periods={brandTrends.periods}
              totalMonths={brandTrends.total_months}
              metric={brandMetric}
              setMetric={setBrandMetric}
              rowKey="brand"
              rowKeyLabel="Brand"
              renderRowKey={(row) => (
                <Link
                  href={`/dashboards/locations/${encodeURIComponent(locationName)}/${encodeURIComponent(row.brand)}`}
                  className="text-[var(--nichi-blue)] hover:underline"
                >
                  {row.brand}
                </Link>
              )}
              csvFilenameBase={`brands_monthly_${locationName}`}
              yearLabel={selectedYears.sort((a, b) => a - b).join("_")}
            />
          )}

          {/* Top selling items */}
          {topItems.length > 0 && (
            <div className="bg-white rounded-lg shadow border overflow-hidden mb-6">
              <div className="px-4 py-3 border-b bg-gray-50">
                <h2 className="font-semibold text-gray-800">
                  Top Selling Items at {locationName}
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
                    key: "brand",
                    label: "Brand",
                    linkFn: (row) =>
                      `/dashboards/locations/${encodeURIComponent(locationName)}/${encodeURIComponent(row.brand)}`,
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
                  D1_STOCK_COL,
                  MONTHLY_VELOCITY_COL,
                  CURRENT_PLANOGRAM_COL,
                  SHELF_CAP_COL,
                  NET_TRANSFER_COL,
                ]}
                data={topItems}
                defaultSort="sold_thb"
                defaultDir="desc"
                pageSize={50}
              />
            </div>
          )}

          {/* Monthly Item Revenue matrix (top products at this location, all brands) */}
          {itemTrends?.items?.length > 0 && itemTrends.periods?.length > 0 && (
            <MonthlyMatrix
              title={`Monthly Sales by Product at ${locationName}`}
              subtitle={`Top ${itemTrends.items.length} products by revenue \u2014 ${selectedYears.sort((a, b) => a - b).join(", ")}. Avg/Month = Total \u00f7 ${itemTrends.total_months} months.`}
              rows={itemTrends.items}
              periods={itemTrends.periods}
              totalMonths={itemTrends.total_months}
              metric={itemMetric}
              setMetric={setItemMetric}
              rowKey="item_code"
              rowKeyLabel="Item Code"
              extraCol={{ key: "item_name", label: "Item Name" }}
              renderRowKey={(row) => (
                <Link
                  href={`/dashboards/item-detail/${encodeURIComponent(row.item_code)}/${encodeURIComponent(locationName)}`}
                  className="text-[var(--nichi-blue)] hover:underline"
                >
                  {row.item_code}
                </Link>
              )}
              csvFilenameBase={`products_monthly_${locationName}`}
              yearLabel={selectedYears.sort((a, b) => a - b).join("_")}
            />
          )}

          {/* (Product-Market Fit moved up — now appears right after the
              KPI summary; see the panel near the top of this conditional.) */}

          {/* Dead Stock Products — items in stock with zero recent sales */}
          {(data.non_movers || []).length > 0 && (
            <div className="bg-white rounded-lg shadow border overflow-hidden mb-6">
              <div className="px-4 py-3 border-b bg-red-50 flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-red-800">
                    Dead Stock Products at {locationName}
                    {" — "}
                    <span className="font-bold">{fmtQty((data.non_movers || []).length)} items</span>
                    {" totalling "}
                    <span className="font-bold">{fmtThb(data.non_mover_total_thb)}</span>
                  </h2>
                  <p className="text-xs text-red-600 mt-0.5">
                    Items with on-hand stock AND zero sales in the last {data.non_mover_window_days ?? 90} days
                    AND first received at this location {'>'} {data.non_mover_window_days ?? 90} days ago.
                    Freshly-transferred stock is excluded.
                    {data.non_mover_fresh_excluded > 0 && (
                      <span className="ml-1 text-red-700 font-medium">
                        ({data.non_mover_fresh_excluded} recently-transferred item{data.non_mover_fresh_excluded === 1 ? "" : "s"} excluded.)
                      </span>
                    )}
                    {" Sorted by on-hand value; use pagination below to see more."}
                  </p>
                </div>
                <button
                  onClick={() =>
                    downloadCsvFromObjects(
                      (data.non_movers || []).map((r) => ({
                        "Item Code": r.item_code,
                        Brand: r.brand,
                        "On-Hand Qty": r.onhand_qty,
                        "On-Hand Value (THB @ Master)": r.onhand_thb,
                        "Lifetime Sold Qty (at this location)": r.lifetime_sold_qty ?? 0,
                        "Lifetime Sold Value (THB, Actual Sales)": r.lifetime_sold_thb_actual ?? 0,
                        "Lifetime Sold Value (THB, Master)": r.lifetime_sold_thb_master ?? 0,
                        "First Seen at Location": r.first_seen_at_location || "",
                        "First Seen in Company": r.first_seen_in_company || "",
                      })),
                      `dead_stock_${locationName}_${selectedYears.sort((a, b) => a - b).join("_")}.csv`
                    )
                  }
                  className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700 whitespace-nowrap"
                >
                  Export CSV
                </button>
              </div>
              <SortableTable
                columns={[
                  {
                    key: "item_code",
                    label: "Item Code",
                    linkFn: (row) =>
                      `/dashboards/item-detail/${encodeURIComponent(row.item_code)}/${encodeURIComponent(locationName)}`,
                  },
                  {
                    key: "brand",
                    label: "Brand",
                    linkFn: (row) =>
                      `/dashboards/locations/${encodeURIComponent(locationName)}/${encodeURIComponent(row.brand)}`,
                  },
                  { key: "onhand_qty", label: "On-Hand Qty", fmt: fmtQty },
                  {
                    key: "onhand_thb",
                    label: "On-Hand Value (THB @ Master)",
                    fmt: fmtThb,
                  },
                  {
                    key: "lifetime_sold_qty",
                    label: "Lifetime Sold Qty (Here)",
                    fmt: (v) => fmtQty(v ?? 0),
                    tooltip: "Total units of this SKU ever sold AT THIS LOCATION (all years, not just selected). Zero here = the item never sold at this location — strong PMF mismatch signal.",
                  },
                  {
                    key: "lifetime_sold_thb_actual",
                    label: "Lifetime Sold (THB, Actual Sales)",
                    fmt: (v) => fmtThb(v ?? 0),
                    tooltip: "All-time revenue from this SKU at this location, at actual sales price (after discounts).",
                  },
                  {
                    key: "lifetime_sold_thb_master",
                    label: "Lifetime Sold (THB, Master)",
                    fmt: (v) => fmtThb(v ?? 0),
                    tooltip: "Same as Lifetime Sold (Actual Sales) but priced at Master Price — comparable apples-to-apples with On-Hand Value (THB @ Master).",
                  },
                  {
                    key: "first_seen_at_location",
                    label: "First Seen at Location",
                    fmt: (v) => v || "—",
                  },
                  {
                    key: "first_seen_in_company",
                    label: "First Seen in Company",
                    fmt: (v) => v || "—",
                    tooltip: "Earliest GRPO / TR IN / sale anywhere — used when no location-specific arrival is recorded",
                  },
                  D1_STOCK_COL,
                  MONTHLY_VELOCITY_COL,
                  CURRENT_PLANOGRAM_COL,
                  SHELF_CAP_COL,
                  NET_TRANSFER_COL,
                ]}
                data={data.non_movers || []}
                defaultSort="onhand_thb"
                defaultDir="desc"
                pageSize={50}
              />
            </div>
          )}

          {/* All Stock Items — every item with positive on-hand at this location */}
          {(data.all_stocks || []).length > 0 && (
            <div className="bg-white rounded-lg shadow border overflow-hidden mb-6">
              <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-gray-800">
                    All Stock Items at {locationName} ({(data.all_stocks || []).length} items)
                  </h2>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Every item with on-hand {'>'}0 at this location. Sales columns cover the selected year(s).
                  </p>
                </div>
                <button
                  onClick={() =>
                    downloadCsvFromObjects(
                      (data.all_stocks || []).map((r) => ({
                        "Item Code": r.item_code,
                        "Item Name": r.item_name,
                        Brand: r.brand,
                        "On-Hand Qty": r.onhand_qty,
                        "On-Hand Value (THB @ Master)": r.onhand_thb,
                        "Sold Qty": r.sold_qty,
                        "Revenue (THB, Actual Sales)": r.sold_thb,
                        "Revenue (THB, Master)": r.sold_master_thb,
                      })),
                      `all_stocks_${locationName}_${selectedYears.sort((a, b) => a - b).join("_")}.csv`
                    )
                  }
                  className="px-3 py-1.5 text-xs bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)] whitespace-nowrap"
                >
                  Export CSV
                </button>
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
                    key: "brand",
                    label: "Brand",
                    linkFn: (row) =>
                      `/dashboards/locations/${encodeURIComponent(locationName)}/${encodeURIComponent(row.brand)}`,
                  },
                  { key: "onhand_qty", label: "On-Hand Qty", fmt: fmtQty },
                  {
                    key: "onhand_thb",
                    label: "On-Hand (THB @ Master)",
                    fmt: fmtThb,
                  },
                  { key: "sold_qty", label: "Sold Qty", fmt: fmtQty },
                  {
                    key: "sold_thb",
                    label: "Revenue (THB, Actual)",
                    fmt: fmtThb,
                  },
                  {
                    key: "sold_master_thb",
                    label: "Revenue (THB, Master)",
                    fmt: fmtThb,
                  },
                  D1_STOCK_COL,
                  MONTHLY_VELOCITY_COL,
                  CURRENT_PLANOGRAM_COL,
                  SHELF_CAP_COL,
                  NET_TRANSFER_COL,
                ]}
                data={data.all_stocks || []}
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
