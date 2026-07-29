"use client";

import { useCallback, useEffect, useState } from "react";
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
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";

const CY = new Date().getFullYear();
const YEAR_OPTIONS = [CY, CY - 1, CY - 2, CY - 3];

const CHANNEL_COLORS = [
  "#1a3a8f", "#FFD200", "#059669", "#dc2626", "#7c3aed",
  "#d97706", "#0891b2", "#be185d", "#4f46e5", "#65a30d",
  "#ea580c", "#0d9488", "#6366f1", "#c026d3", "#84cc16",
];

export default function ChannelsListPage() {
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
    selectedYears.forEach((y) => params.append("year_list", String(y)));
    api.get(`/api/channel_list?${params}`, { signal })
      .then((res) => {
        const d = res.data || {};
        if (Array.isArray(d.channels)) {
          // Server-side now returns net_revenue_thb on unrounded aggregates.
          // Fallback kept in case of a stale cached response.
          d.channels = d.channels.map((c) => ({
            ...c,
            net_revenue_thb: c.net_revenue_thb != null
              ? c.net_revenue_thb
              : (c.sold_master_thb ?? 0) - (c.retailer_cut_thb ?? 0),
          }));
        }
        setData(d);
        setLoading(false);
      })
      .catch((err) => { if (!isAbortError(err)) { setError(err.message); setLoading(false); } });
  }, [selectedYears]);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchData(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchData]);

  const yearLabel = selectedYears.sort((a, b) => a - b).join(", ");

  const handleExport = () => {
    if (!data?.channels) return;
    const headers = ["Channel", "Description", "Revenue (THB, Master)", "Retailer Cut (THB)", "Revenue (THB, Actual)", "Revenue (THB, Invoiced)", "Share (%)", "Sold Qty", "Locations", "Brands", "Top Location", "Top Location Revenue", "GP Commission (THB)", "Discount (THB)", "Retailer Cut %"];
    const rows = data.channels.map((c) => [
      c.channel, c.description, c.sold_master_thb, c.retailer_cut_thb, c.net_revenue_thb, c.revenue,
      c.revenue_pct, c.sold_qty, c.location_count, c.brand_count, c.top_location_name, c.top_location_revenue,
      c.gp_commission_thb, c.discount_thb, c.retailer_cut_pct,
    ]);
    downloadCsv(`channels_${yearLabel.replace(/, /g, "_")}.csv`, headers, rows);
  };

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)] p-4 md:p-6">
      <div className="max-w-[1400px] mx-auto space-y-4">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[var(--nichi-blue-dark)]">
              Sales Channels
            </h1>
            <p className="text-sm text-gray-500">
              All {data?.total_channels || "—"} sales channels for {yearLabel}.
              Each channel maps to one or many physical locations (stores/warehouses).
              Revenue = Actual Sales (THB).
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

        {loading && <LoadingSpinner message="Loading channels..." />}
        {error && <ErrorBanner message={error} onRetry={() => fetchData()} />}

        {!loading && !error && data?.channels && (
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
                <div className="text-sm text-gray-500">Total Channels</div>
                <div className="text-xl font-bold">{data.total_channels}</div>
              </div>
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <div className="text-sm text-gray-500">Top Channel</div>
                <div className="text-xl font-bold">{data.channels[0]?.channel || "—"}</div>
                <div className="text-xs text-gray-400">{fmtPct(data.channels[0]?.revenue_pct || 0)} of revenue</div>
              </div>
              <div className="bg-white border rounded-lg p-4 shadow-sm">
                <div className="text-sm text-gray-500">Top 3 Channels</div>
                <div className="text-xl font-bold">
                  {fmtPct(data.channels.slice(0, 3).reduce((s, c) => s + (c.revenue_pct || 0), 0))}
                </div>
                <div className="text-xs text-gray-400">of total revenue</div>
              </div>
            </div>

            {/* Revenue by Channel — horizontal bar chart */}
            <div className="bg-white border rounded-lg p-4 shadow-sm">
              <h2 className="text-sm font-semibold mb-3">Revenue by Channel — {yearLabel} (Ranked)</h2>
              <ResponsiveContainer width="100%" height={Math.max(320, data.channels.length * 28)}>
                <BarChart data={data.channels} layout="vertical" margin={{ left: 120, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tickFormatter={(v) => (v / 1000000).toFixed(1) + "M"} />
                  <YAxis type="category" dataKey="channel" width={115} tick={{ fontSize: 11 }} interval={0} />
                  <Tooltip formatter={(v) => fmtThb(v)} />
                  <Bar dataKey="revenue" name="Revenue (THB, Actual Sales)">
                    {data.channels.map((_, i) => (
                      <Cell key={i} fill={CHANNEL_COLORS[i % CHANNEL_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Channel Table */}
            <div className="bg-white border rounded-lg p-4 shadow-sm">
              <div className="flex justify-between items-center mb-3">
                <h2 className="text-sm font-semibold">All Channels — {yearLabel}</h2>
                <button onClick={handleExport}
                  className="px-3 py-1 text-sm bg-[var(--nichi-blue)] text-white rounded hover:bg-[var(--nichi-blue-dark)]">
                  Export CSV
                </button>
              </div>
              <SortableTable
                columns={[
                  {
                    key: "channel", label: "Channel",
                    render: (v) => (
                      <Link href={`/dashboards/channels/${encodeURIComponent(v)}`}
                        className="text-[var(--nichi-blue)] hover:underline font-medium">
                        {v}
                      </Link>
                    ),
                  },
                  { key: "description", label: "Description" },
                  { key: "sold_master_thb", label: "Revenue (THB, Master)", render: (v) => fmtThb(v),
                    tooltip: "Top-line at list price. = Revenue (Actual) + Retailer Cut." },
                  {
                    key: "retailer_cut_thb", label: "Retailer Cut (THB)",
                    render: (v) => fmtThb(v),
                    tooltip: "What the retailer keeps: GP Commission (consignment) + discount (credit). Unified across both sale types.",
                  },
                  {
                    key: "net_revenue_thb", label: "Revenue (THB, Actual)",
                    render: (v) => fmtThb(v),
                    tooltip: "What Nichi actually keeps after the retailer's cut. Revenue (Master) − Retailer Cut.",
                  },
                  { key: "revenue", label: "Revenue (THB, Invoiced)", render: (v) => fmtThb(v),
                    tooltip: "SAP LineTotal — gross invoiced amount. For consignment this equals Master (GP still inside)." },
                  { key: "revenue_pct", label: "Share (%)", render: (v) => fmtPct(v) },
                  { key: "sold_qty", label: "Sold Qty", render: (v) => fmtQty(v) },
                  { key: "location_count", label: "Locations" },
                  { key: "brand_count", label: "Brands" },
                  {
                    key: "retailer_cut_pct", label: "Retailer Cut %",
                    render: (v) => fmtPct(v),
                    tooltip: "Retailer Cut ÷ Revenue (Master). Apples-to-apples channel cost.",
                  },
                  { key: "gp_commission_thb", label: "GP Commission (THB)", render: (v) => fmtThb(v) },
                  { key: "discount_thb", label: "Discount (THB)", render: (v) => fmtThb(v) },
                  { key: "top_location_name", label: "Top Location" },
                  { key: "top_location_revenue", label: "Top Location Revenue", render: (v) => fmtThb(v) },
                ]}
                data={data.channels}
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
