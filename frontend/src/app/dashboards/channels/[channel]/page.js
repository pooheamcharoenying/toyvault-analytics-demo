"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import api, { isAbortError } from "@/utils/api";
import ErrorBanner from "@/components/ErrorBanner";
import LoadingSpinner from "@/components/LoadingSpinner";
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
} from "recharts";

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

const COLORS = [
  "#1a3a8f", "#FFD200", "#059669", "#dc2626", "#7c3aed",
  "#d97706", "#0891b2", "#be185d", "#4f46e5", "#65a30d",
];

const chartThb = (v) => "฿" + (v / 1000000).toFixed(1) + "M";

export default function ChannelDetailPage() {
  const params = useParams();
  const channelName = decodeURIComponent(params.channel || "");

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

  const fetchData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    params.set("channel", channelName);
    selectedYears.forEach((y) => params.append("year_list", String(y)));
    api.get(`/api/channel_detail?${params}`, { signal })
      .then((res) => { setData(res.data); setLoading(false); })
      .catch((err) => { if (!isAbortError(err)) { setError(err.message); setLoading(false); } });
  }, [channelName, selectedYears]);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchData(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchData]);

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  const handleExportLocations = () => {
    if (!data?.locations) return;
    const headers = ["WhsCode", "Location", "Revenue (THB, Actual)", "Revenue (THB, Master)", "Share (%)", "Sold Qty", "On-Hand Qty", "On-Hand Value (THB, Master)", "Brands", "Items", "Rev/Inventory"];
    const rows = data.locations.map((l) => [
      l.whs_code, l.whs_name, l.revenue, l.sold_master_thb, l.revenue_pct, l.sold_qty,
      l.onhand_qty, l.onhand_thb, l.brand_count, l.item_count, l.revenue_per_inv,
    ]);
    downloadCsv(`channel_${channelName}_locations_${yearLabel.replace(/, /g, "_")}.csv`, headers, rows);
  };

  const handleExportBrands = () => {
    if (!data?.brands) return;
    const headers = ["Brand", "Revenue (THB, Actual)", "Revenue (THB, Master)", "Share (%)", "Sold Qty", "Items"];
    const rows = data.brands.map((b) => [b.brand, b.revenue, b.sold_master_thb, b.revenue_pct, b.sold_qty, b.item_count]);
    downloadCsv(`channel_${channelName}_brands_${yearLabel.replace(/, /g, "_")}.csv`, headers, rows);
  };

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)] p-4 md:p-6">
      <div className="max-w-[1400px] mx-auto space-y-4">
        {/* Breadcrumb */}
        <nav className="text-sm text-gray-500">
          <Link href="/dashboards/channels" className="hover:underline text-[var(--nichi-blue)]">Channels</Link>
          <span className="mx-2">&gt;</span>
          <span className="font-medium text-gray-800">{channelName}</span>
        </nav>

        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[var(--nichi-blue-dark)]">
              Channel: {channelName}
            </h1>
            <p className="text-sm text-gray-500">
              {data?.description || ""} — {yearLabel}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-gray-500">Year:</span>
            {YEAR_OPTIONS.map((y) => (
              <button key={y} onClick={() => toggleYear(y)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  selectedYears.includes(y)
                    ? "bg-[var(--nichi-blue)] text-white"
                    : "border border-gray-200 hover:bg-gray-100"
                }`}>
                {y}
              </button>
            ))}
          </div>
        </div>

        {loading && <LoadingSpinner message={`Loading ${channelName} channel data...`} />}
        {error && <ErrorBanner message={error} onRetry={() => fetchData()} />}

        {!loading && !error && data && (
          <>
            {/* KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <div className="text-sm text-gray-500">Revenue (Actual Sales)</div>
                <div className="text-xl font-bold">{fmtThb(data.total_revenue)}</div>
                <div className="text-xs text-gray-400">{yearLabel}</div>
              </div>
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <div className="text-sm text-gray-500">Revenue (Master)</div>
                <div className="text-xl font-bold">{fmtThb(data.total_revenue_master)}</div>
                <div className="text-xs text-gray-400">{yearLabel}</div>
              </div>
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <div className="text-sm text-gray-500">Total Sold Qty</div>
                <div className="text-xl font-bold">{fmtQty(data.total_sold_qty)}</div>
              </div>
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <div className="text-sm text-gray-500">Locations</div>
                <div className="text-xl font-bold">{data.location_count}</div>
                <div className="text-xs text-gray-400">Physical stores/warehouses</div>
              </div>
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <div className="text-sm text-gray-500">Top Location</div>
                <div className="text-lg font-bold truncate">{data.locations?.[0]?.whs_name || "—"}</div>
                <div className="text-xs text-gray-400">
                  {data.locations?.[0] ? `${fmtPct(data.locations[0].revenue_pct)} of channel revenue` : ""}
                </div>
              </div>
            </div>

            {/* Charts row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Revenue by Location — horizontal bar */}
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <h2 className="text-sm font-semibold mb-3">Revenue by Location — {yearLabel}</h2>
                {data.locations?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={Math.max(280, data.locations.length * 26)}>
                    <BarChart data={data.locations} layout="vertical" margin={{ left: 140, right: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" tickFormatter={chartThb} />
                      <YAxis type="category" dataKey="whs_name" width={135} tick={{ fontSize: 10 }} interval={0} />
                      <Tooltip formatter={(v) => fmtThb(v)} />
                      <Bar dataKey="revenue" name="Revenue (THB, Actual Sales)">
                        {data.locations.map((_, i) => (
                          <Cell key={i} fill={COLORS[i % COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-64 flex items-center justify-center text-gray-400">No location data</div>
                )}
              </div>

              {/* Monthly Revenue Trend */}
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <h2 className="text-sm font-semibold mb-3">Monthly Revenue Trend — {channelName} ({yearLabel})</h2>
                {data.monthly_trend?.length > 0 ? (
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart data={data.monthly_trend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                      <YAxis tickFormatter={chartThb} />
                      <Tooltip formatter={(v) => fmtThb(v)} />
                      <Legend />
                      <Line type="monotone" dataKey="revenue" name="Revenue (Actual)" stroke="var(--nichi-blue)" strokeWidth={2} dot={{ r: 3 }} />
                      <Line type="monotone" dataKey="sold_master_thb" name="Revenue (Master)" stroke="var(--nichi-blue-light)" strokeWidth={2} strokeDasharray="5 3" dot={{ r: 2 }} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-64 flex items-center justify-center text-gray-400">No trend data</div>
                )}
              </div>
            </div>

            {/* Locations Table */}
            <div className="bg-white border rounded-lg p-4 shadow-sm">
              <div className="flex justify-between items-center mb-3">
                <h2 className="text-sm font-semibold">
                  All Locations in {channelName} ({data.location_count}) — {yearLabel}
                </h2>
                <button onClick={handleExportLocations}
                  className="px-3 py-1 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)]">
                  Export CSV
                </button>
              </div>
              <SortableTable
                columns={[
                  {
                    key: "whs_name", label: "Location",
                    render: (v, row) => (
                      <Link href={`/dashboards/locations/${encodeURIComponent(row.whs_code)}`}
                        className="text-[var(--nichi-blue)] hover:underline font-medium">
                        {v}
                      </Link>
                    ),
                  },
                  { key: "whs_code", label: "Code" },
                  { key: "revenue", label: "Revenue (THB, Actual Sales)", render: (v) => fmtThb(v) },
                  { key: "sold_master_thb", label: "Revenue (THB, Master)", render: (v) => fmtThb(v) },
                  { key: "revenue_pct", label: "Share (%)", render: (v) => fmtPct(v) },
                  { key: "sold_qty", label: "Sold Qty", render: (v) => fmtQty(v) },
                  { key: "onhand_qty", label: "On-Hand Qty", render: (v) => fmtQty(v) },
                  { key: "onhand_thb", label: "On-Hand (THB, Master)", render: (v) => fmtThb(v) },
                  { key: "brand_count", label: "Brands" },
                  { key: "item_count", label: "Items" },
                  { key: "revenue_per_inv", label: "Rev/Inventory", render: (v) => v != null ? v.toFixed(2) + "x" : "—" },
                ]}
                data={data.locations || []}
                defaultSort="revenue"
                defaultDir="desc"
              />
            </div>

            {/* Top Brands Table */}
            <div className="bg-white border rounded-lg p-4 shadow-sm">
              <div className="flex justify-between items-center mb-3">
                <h2 className="text-sm font-semibold">Top Brands in {channelName} — {yearLabel}</h2>
                <button onClick={handleExportBrands}
                  className="px-3 py-1 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)]">
                  Export CSV
                </button>
              </div>
              <SortableTable
                columns={[
                  {
                    key: "brand", label: "Brand",
                    render: (v) => (
                      <Link href={`/dashboards/brands/${encodeURIComponent(v)}`}
                        className="text-[var(--nichi-blue)] hover:underline font-medium">
                        {v}
                      </Link>
                    ),
                  },
                  { key: "revenue", label: "Revenue (THB, Actual Sales)", render: (v) => fmtThb(v) },
                  { key: "sold_master_thb", label: "Revenue (THB, Master)", render: (v) => fmtThb(v) },
                  { key: "revenue_pct", label: "Share (%)", render: (v) => fmtPct(v) },
                  { key: "sold_qty", label: "Sold Qty", render: (v) => fmtQty(v) },
                  { key: "item_count", label: "Items" },
                ]}
                data={data.brands || []}
                defaultSort="revenue"
                defaultDir="desc"
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
