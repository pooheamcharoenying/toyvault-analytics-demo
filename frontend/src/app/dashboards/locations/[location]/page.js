"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import api, { isAbortError } from "@/utils/api";
import SortableTable from "@/components/SortableTable";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBanner from "@/components/ErrorBanner";
import AbcdeBadge from "@/components/AbcdeBadge";
import RecommendationPanel from "@/components/RecommendationCard";
import { fmtThb, fmtQty, fmtPct, fmtRatio } from "@/utils/formatters";
import { downloadCsvFromObjects } from "@/utils/csvExport";

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

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
    (years, signal) => {
      const qs = new URLSearchParams();
      qs.set("location", locationName);
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

  useEffect(() => {
    const ctrl = new AbortController();
    loadData(selectedYears, ctrl.signal);
    loadTrend(selectedYears, ctrl.signal);
    loadAbcde(selectedYears, ctrl.signal);
    return () => ctrl.abort();
  }, [loadData, loadTrend, loadAbcde, selectedYears]);

  const trendChartData = useMemo(() => {
    if (!trendData?.trends?.length) return [];
    const t = trendData.trends[0];
    return (t.months || []).map((m) => ({
      period: m.period,
      // If the latest month is partial, show the running-rate projection
      // so it's comparable to prior full months. The running_rate_* fields
      // are set by the backend annotate_monthly_series helper.
      "Revenue (Actual)": m.is_partial ? m.running_rate_sold_thb : m.sold_thb,
      "Revenue (Master)": m.is_partial ? m.running_rate_sold_master_thb : m.sold_master_thb,
      is_partial: !!m.is_partial,
      days_elapsed: m.days_elapsed,
      days_in_month: m.days_in_month,
    }));
  }, [trendData]);

  const partialNote = trendChartData.length > 0 && trendChartData[trendChartData.length - 1]?.is_partial
    ? `Latest month projected from ${trendChartData[trendChartData.length - 1].days_elapsed}/${trendChartData[trendChartData.length - 1].days_in_month} days`
    : null;

  const brandHeatmap = (data?.brand_heatmap || []).map((b) => ({
    ...b,
    __location: locationName,
  }));
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
    <div className="max-w-7xl mx-auto px-4 py-6">
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

          {/* Monthly Revenue Trend */}
          {trendChartData.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4 mb-6">
              <h2 className="text-base font-semibold text-gray-800 mb-3">
                Monthly Revenue Trend — {locationName} ({selectedYears.sort((a, b) => a - b).join(", ")})
              </h2>
              {partialNote && (
                <p className="text-xs text-amber-700 -mt-2 mb-2">
                  ⓘ {partialNote} → latest data point shown as full-month running-rate projection for fair comparison
                </p>
              )}
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={trendChartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200" />
                  <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={chartThb} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => fmtThb(v)} />
                  <Legend />
                  <Line type="monotone" dataKey="Revenue (Actual)" stroke="#1a3a8f" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="Revenue (Master)" stroke="#2d4ea3" strokeWidth={2} dot={false} strokeDasharray="5 5" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Top brands chart */}
          {chartData.length > 0 && (
            <div className="bg-white rounded-lg shadow border p-4 mb-6">
              <h2 className="text-base font-semibold text-gray-800 mb-3">
                Top Brands by Revenue ({selectedYears.sort((a, b) => a - b).join(", ")})
              </h2>
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
                      `/dashboards/item-detail/${encodeURIComponent(row.item_code)}`,
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
                ]}
                data={topItems}
                defaultSort="sold_thb"
                defaultDir="desc"
                pageSize={50}
              />
            </div>
          )}

          {/* Dead Stock Products — items in stock with zero recent sales */}
          {(data.non_movers || []).length > 0 && (
            <div className="bg-white rounded-lg shadow border overflow-hidden mb-6">
              <div className="px-4 py-3 border-b bg-red-50 flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-red-800">
                    Dead Stock Products at {locationName}
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
                        "First Seen at Location": r.first_seen_at_location || "",
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
                      `/dashboards/item-detail/${encodeURIComponent(row.item_code)}`,
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
                    key: "first_seen_at_location",
                    label: "First Seen at Location",
                    fmt: (v) => v || "—",
                  },
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
                      `/dashboards/item-detail/${encodeURIComponent(row.item_code)}`,
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
