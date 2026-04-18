"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { fmtThb, fmtQty } from "@/utils/formatters";
import { downloadCsvFromObjects } from "@/utils/csvExport";

function chartThb(v) {
  if (v == null) return "";
  if (Math.abs(v) >= 1e6) return `฿${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `฿${(v / 1e3).toFixed(0)}K`;
  return `฿${v.toFixed(0)}`;
}

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

export default function BrandAtLocationPage() {
  const params = useParams();
  const locationName = decodeURIComponent(params.location);
  const brandName = decodeURIComponent(params.brand);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedYears, setSelectedYears] = useState([CY]);
  const [trendData, setTrendData] = useState(null);

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
    (years, signal) => {
      const qs = new URLSearchParams();
      qs.set("location", locationName);
      qs.set("brand", brandName);
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

  useEffect(() => {
    const ctrl = new AbortController();
    loadData(selectedYears, ctrl.signal);
    loadTrend(selectedYears, ctrl.signal);
    return () => ctrl.abort();
  }, [loadData, loadTrend, selectedYears]);

  const trendChartData = useMemo(() => {
    if (!trendData?.months?.length) return [];
    return trendData.months.map((m) => ({
      period: m.period,
      "Revenue (Actual)": m.sold_thb,
      "Revenue (Master)": m.sold_master_thb,
    }));
  }, [trendData]);

  const topItems = data?.top_items || [];
  const nonMovers = data?.non_movers || [];

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
        "Revenue (THB, Actual Sales)": r.sold_thb,
        "Revenue (THB, Master)": r.sold_master_thb,
        "Sold Qty": r.sold_qty,
      })),
      `location_${locationName}_brand_${brandName}_${selectedYears.sort((a, b) => a - b).join("_")}.csv`
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
              <h2 className="text-base font-semibold text-gray-800 mb-3">
                Monthly Revenue — {brandName} at {locationName} ({selectedYears.sort((a, b) => a - b).join(", ")})
              </h2>
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
                    `/dashboards/item-detail/${encodeURIComponent(row.item_code)}`,
                },
                { key: "item_name", label: "Item Name" },
                {
                  key: "abcde_class",
                  label: "Tier",
                  render: (v) => <AbcdeBadge tier={v} context="at this location" />,
                  tooltip: "ABCDE tier by revenue at this location",
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
              data={topItems.map((r) => ({
                ...r,
                abcde_class: abcdeByItem[r.item_code] || "E",
              }))}
              defaultSort="sold_thb"
              defaultDir="desc"
              pageSize={50}
            />
          </div>

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
                      `/dashboards/item-detail/${encodeURIComponent(row.item_code)}`,
                  },
                  { key: "onhand_qty", label: "On-Hand Qty", fmt: fmtQty },
                  {
                    key: "onhand_thb",
                    label: "On-Hand Value (THB @ Master Price)",
                    fmt: fmtThb,
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
