"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import api, { isAbortError } from "@/utils/api";
import ErrorBanner from "@/components/ErrorBanner";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import KpiCard from "@/components/KpiCard";
import SortableTable from "@/components/SortableTable";
import StatusBadge from "@/components/StatusBadge";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  LineChart,
  Line,
  Cell,
} from "recharts";

const TABS = [
  { id: "allocation", label: "Stock Allocation" },
  { id: "transfers", label: "Transfer History" },
  { id: "rebalancing", label: "Rebalancing Summary" },
];

import { fmtThb, fmtQty, fmtDays } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csvExport";

const COLORS = ["#1a3a8f", "#d97706", "#059669", "#dc2626", "#7c3aed", "#0891b2", "#be185d"];


// ──────────────────── ALLOCATION TAB ────────────────────
function AllocationTab({ data, loading }) {
  if (loading) return <p className="text-center py-8 text-gray-500">Loading allocation data...</p>;
  if (!data) return <p className="text-center py-8 text-gray-400">No data available.</p>;

  const { summary, recommendations, overstocked, understocked } = data;

  const itemLink = (row) => `/dashboards/item-detail/${encodeURIComponent(row.ItemCode)}`;

  const recCols = [
    { key: "ItemCode", label: "Item", linkFn: itemLink },
    { key: "ItemName", label: "Description" },
    { key: "Brand", label: "Brand" },
    { key: "from_name", label: "From Location", tooltip: METRIC_TOOLTIPS.allocation.transfer_from },
    { key: "from_days_cover", label: "From Days Cover", tooltip: METRIC_TOOLTIPS.allocation.days_cover, fmt: (v) => fmtDays(v) },
    { key: "to_name", label: "To Location", tooltip: METRIC_TOOLTIPS.allocation.transfer_to },
    { key: "to_days_cover", label: "To Days Cover", tooltip: METRIC_TOOLTIPS.allocation.days_cover, fmt: (v) => fmtDays(v) },
    { key: "transfer_qty", label: "Qty", tooltip: METRIC_TOOLTIPS.allocation.transfer_qty, fmt: (v) => fmtQty(v) },
    { key: "transfer_thb", label: "Value (THB @ Master Price)", fmt: (v) => fmtThb(v) },
  ];

  const overCols = [
    { key: "ItemCode", label: "Item", linkFn: itemLink },
    { key: "ItemName", label: "Description" },
    { key: "WhsName", label: "Location" },
    { key: "Brand", label: "Brand" },
    { key: "onhand_qty", label: "On Hand", fmt: (v) => fmtQty(v) },
    { key: "sold_qty", label: "Sold (90d)", fmt: (v) => fmtQty(v) },
    { key: "days_cover", label: "Days Cover", tooltip: METRIC_TOOLTIPS.allocation.days_cover, fmt: (v) => fmtDays(v) },
    { key: "excess_qty", label: "Excess Qty", tooltip: METRIC_TOOLTIPS.allocation.surplus_deficit, fmt: (v) => fmtQty(v) },
    { key: "excess_thb", label: "Excess (THB @ Master Price)", fmt: (v) => fmtThb(v) },
  ];

  const underCols = [
    { key: "ItemCode", label: "Item", linkFn: itemLink },
    { key: "ItemName", label: "Description" },
    { key: "WhsName", label: "Location" },
    { key: "Brand", label: "Brand" },
    { key: "onhand_qty", label: "On Hand", fmt: (v) => fmtQty(v) },
    { key: "sold_qty", label: "Sold (90d)", fmt: (v) => fmtQty(v) },
    { key: "days_cover", label: "Days Cover", tooltip: METRIC_TOOLTIPS.allocation.days_cover, fmt: (v) => fmtDays(v) },
    { key: "deficit_qty", label: "Deficit Qty", tooltip: METRIC_TOOLTIPS.allocation.surplus_deficit, fmt: (v) => fmtQty(v) },
    { key: "deficit_thb", label: "Deficit (THB @ Master Price)", fmt: (v) => fmtThb(v) },
  ];

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Items Analyzed" value={fmtQty(summary?.total_items)} />
        <KpiCard label="Locations" value={fmtQty(summary?.total_locations)} />
        <KpiCard label="Transfer Recs" value={fmtQty(summary?.transfer_recommendations)} />
        <KpiCard label="Potential Savings" value={fmtThb(summary?.potential_thb_savings)} />
      </div>

      {/* Transfer Recommendations */}
      {recommendations?.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-lg">Transfer Recommendations</h3>
            <button className="text-xs bg-[var(--nichi-blue)] text-white px-3 py-1 rounded" onClick={() => {
              downloadCsv("transfer_recommendations.csv",
                recCols.map(c => c.label),
                recommendations.map(r => recCols.map(c => r[c.key])));
            }}>Export CSV</button>
          </div>
          <p className="text-sm text-gray-500 mb-2">Move stock from surplus to deficit locations to optimize inventory distribution.</p>

          {/* Top recs bar chart */}
          <div className="bg-white rounded-lg shadow p-4 mb-4" style={{ height: 320 }}>
            <h4 className="text-sm font-medium text-slate-700 mb-2">Top Transfer Recommendations by Value</h4>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={recommendations.slice(0, 15)} layout="vertical" margin={{ left: 60, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} label={{ value: "Value (THB)", position: "insideBottom", offset: -5, fontSize: 11 }} />
                <YAxis type="category" dataKey="ItemCode" width={80} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => fmtThb(v)} />
                <Bar dataKey="transfer_thb" name="Transfer Value (THB)" fill="#1a3a8f" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <SortableTable columns={recCols} data={recommendations} defaultSort="transfer_thb" />
        </div>
      )}

      {/* Overstocked */}
      {overstocked?.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-lg text-amber-700">Overstocked Locations</h3>
            <button className="text-xs bg-[var(--nichi-blue)] text-white px-3 py-1 rounded" onClick={() => {
              downloadCsv("overstocked.csv",
                overCols.map(c => c.label),
                overstocked.map(r => overCols.map(c => r[c.key])));
            }}>Export CSV</button>
          </div>
          <SortableTable columns={overCols} data={overstocked} defaultSort="excess_thb" />
        </div>
      )}

      {/* Understocked */}
      {understocked?.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-lg text-red-700">Understocked Locations</h3>
            <button className="text-xs bg-[var(--nichi-blue)] text-white px-3 py-1 rounded" onClick={() => {
              downloadCsv("understocked.csv",
                underCols.map(c => c.label),
                understocked.map(r => underCols.map(c => r[c.key])));
            }}>Export CSV</button>
          </div>
          <SortableTable columns={underCols} data={understocked} defaultSort="deficit_thb" />
        </div>
      )}
    </div>
  );
}

// ──────────────────── TRANSFER HISTORY TAB ────────────────────
function TransferHistoryTab({ data, loading }) {
  if (loading) return <p className="text-center py-8 text-gray-500">Loading transfer data...</p>;
  if (!data) return <p className="text-center py-8 text-gray-400">No data available.</p>;

  const { summary, location_flows, top_items, monthly_trend } = data;

  const flowCols = [
    { key: "WhsName", label: "Location" },
    { key: "qty_in", label: "Qty In", fmt: (v) => fmtQty(v) },
    { key: "qty_out", label: "Qty Out", fmt: (v) => fmtQty(v) },
    { key: "net_flow", label: "Net Flow", fmt: (v) => { const n = Number(v); return <span className={n > 0 ? "text-green-600" : n < 0 ? "text-red-600" : ""}>{n > 0 ? "+" : ""}{fmtQty(n)}</span>; } },
    { key: "transfer_count", label: "Transfers", fmt: (v) => fmtQty(v) },
  ];

  const itemLink = (row) => `/dashboards/item-detail/${encodeURIComponent(row.ItemCode)}`;
  const itemCols = [
    { key: "ItemCode", label: "Item", linkFn: itemLink },
    { key: "Brand", label: "Brand" },
    { key: "total_in", label: "Total In", fmt: (v) => fmtQty(v) },
    { key: "total_out", label: "Total Out", fmt: (v) => fmtQty(v) },
    { key: "net", label: "Net", fmt: (v) => { const n = Number(v); return <span className={n > 0 ? "text-green-600" : n < 0 ? "text-red-600" : ""}>{n > 0 ? "+" : ""}{fmtQty(n)}</span>; } },
    { key: "location_count", label: "Locations" },
  ];

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard label="Transfers In" value={fmtQty(summary?.total_transfers_in)} />
        <KpiCard label="Transfers Out" value={fmtQty(summary?.total_transfers_out)} />
        <KpiCard label="Items Moved" value={fmtQty(summary?.total_items_transferred)} />
        <KpiCard label="Total Qty In" value={fmtQty(summary?.total_qty_in)} />
        <KpiCard label="Total Qty Out" value={fmtQty(summary?.total_qty_out)} />
        <KpiCard label="Net Qty" value={fmtQty(summary?.net_qty)} />
      </div>

      {/* Monthly Trend Chart */}
      {monthly_trend?.length > 0 && (
        <div>
          <h3 className="font-semibold text-lg mb-2">Monthly Transfer Trend</h3>
          <div className="bg-white rounded-lg shadow p-4" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthly_trend} margin={{ left: 20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={60} />
                <YAxis tickFormatter={(v) => fmtQty(v)} />
                <Tooltip formatter={(v) => fmtQty(v)} />
                <Legend />
                <Bar dataKey="qty_in" name="Qty In" fill="#059669" />
                <Bar dataKey="qty_out" name="Qty Out" fill="#dc2626" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Net Flow by Location */}
      {location_flows?.length > 0 && (
        <div>
          <h3 className="font-semibold text-lg mb-2">Net Flow by Location</h3>
          <div className="bg-white rounded-lg shadow p-4 mb-4" style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={location_flows} margin={{ left: 20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="WhsName" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v) => fmtQty(v)} />
                <Tooltip formatter={(v) => fmtQty(v)} />
                <Bar dataKey="net_flow" name="Net Flow">
                  {location_flows.map((entry, i) => (
                    <Cell key={i} fill={entry.net_flow >= 0 ? "#059669" : "#dc2626"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <SortableTable columns={flowCols} data={location_flows} defaultSort="net_flow" />
        </div>
      )}

      {/* Top Transferred Items */}
      {top_items?.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-lg">Top Transferred Items</h3>
            <button className="text-xs bg-[var(--nichi-blue)] text-white px-3 py-1 rounded" onClick={() => {
              downloadCsv("top_transferred_items.csv",
                itemCols.map(c => c.label),
                top_items.map(r => itemCols.map(c => r[c.key])));
            }}>Export CSV</button>
          </div>
          <SortableTable columns={itemCols} data={top_items} defaultSort="total_in" />
        </div>
      )}
    </div>
  );
}

// ──────────────────── REBALANCING SUMMARY TAB ────────────────────
function RebalancingTab({ data, loading }) {
  if (loading) return <p className="text-center py-8 text-gray-500">Loading rebalancing data...</p>;
  if (!data) return <p className="text-center py-8 text-gray-400">No data available.</p>;

  const { summary, location_balance, brand_opportunities } = data;

  const locCols = [
    { key: "WhsName", label: "Location" },
    { key: "surplus_thb", label: "Surplus (THB @ Master Price)", fmt: (v) => fmtThb(v) },
    { key: "deficit_thb", label: "Deficit (THB @ Master Price)", fmt: (v) => fmtThb(v) },
    { key: "net_thb", label: "Net (THB @ Master Price)", fmt: (v) => { const n = Number(v); return <span className={n > 0 ? "text-amber-600 font-semibold" : n < 0 ? "text-red-600 font-semibold" : ""}>{fmtThb(n)}</span>; } },
    { key: "status", label: "Status", fmt: (v) => <StatusBadge status={v} /> },
    { key: "priority", label: "Priority", fmt: (v) => <StatusBadge status={v} /> },
  ];

  const brandCols = [
    { key: "Brand", label: "Brand" },
    { key: "surplus_thb", label: "Surplus (THB @ Master Price)", tooltip: METRIC_TOOLTIPS.allocation.surplus_deficit, fmt: (v) => fmtThb(v) },
    { key: "deficit_thb", label: "Deficit (THB @ Master Price)", tooltip: METRIC_TOOLTIPS.allocation.surplus_deficit, fmt: (v) => fmtThb(v) },
    { key: "rebalanceable_thb", label: "Rebalanceable (THB @ Master Price)", tooltip: METRIC_TOOLTIPS.allocation.rebalanceable, fmt: (v) => fmtThb(v) },
    { key: "item_count", label: "Items" },
  ];

  // Location balance bar chart data
  const locChartData = (location_balance || []).map(l => ({
    name: l.WhsName,
    surplus: l.surplus_thb,
    deficit: -l.deficit_thb,
  }));

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard label="Total Surplus" value={fmtThb(summary?.total_surplus_thb)} sub="Excess stock value" />
        <KpiCard label="Total Deficit" value={fmtThb(summary?.total_deficit_thb)} sub="Needed stock value" />
        <KpiCard label="Rebalanceable" value={fmtThb(summary?.rebalanceable_thb)} sub="Can be moved" />
        <KpiCard label="Surplus Locations" value={summary?.surplus_locations} />
        <KpiCard label="Deficit Locations" value={summary?.deficit_locations} />
        <KpiCard label="Items to Move" value={fmtQty(summary?.items_to_move)} />
      </div>

      {/* Location Balance Chart */}
      {locChartData.length > 0 && (
        <div>
          <h3 className="font-semibold text-lg mb-2">Location Surplus / Deficit</h3>
          <div className="bg-white rounded-lg shadow p-4" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={locChartData} margin={{ left: 20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v) => fmtThb(Math.abs(v))} />
                <Legend />
                <Bar dataKey="surplus" name="Surplus" fill="#d97706" />
                <Bar dataKey="deficit" name="Deficit" fill="#dc2626" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Location Balance Table */}
      {location_balance?.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-lg">Location Balance</h3>
            <button className="text-xs bg-[var(--nichi-blue)] text-white px-3 py-1 rounded" onClick={() => {
              downloadCsv("location_balance.csv",
                ["Location", "Surplus THB", "Deficit THB", "Net THB", "Status", "Priority"],
                location_balance.map(r => [r.WhsName, r.surplus_thb, r.deficit_thb, r.net_thb, r.status, r.priority]));
            }}>Export CSV</button>
          </div>
          <SortableTable columns={locCols} data={location_balance} defaultSort="net_thb" />
        </div>
      )}

      {/* Brand Opportunities */}
      {brand_opportunities?.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-lg">Brand Rebalancing Opportunities</h3>
            <button className="text-xs bg-[var(--nichi-blue)] text-white px-3 py-1 rounded" onClick={() => {
              downloadCsv("brand_rebalancing.csv",
                brandCols.map(c => c.label),
                brand_opportunities.map(r => brandCols.map(c => r[c.key])));
            }}>Export CSV</button>
          </div>

          {/* Brand bar chart */}
          <div className="bg-white rounded-lg shadow p-4 mb-4" style={{ height: 300 }}>
            <h4 className="text-sm font-medium text-slate-700 mb-2">Brand Rebalancing Opportunities</h4>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={brand_opportunities.slice(0, 10)} margin={{ left: 20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="Brand" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" height={60} />
                <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(v) => fmtThb(v)} />
                <Legend />
                <Bar dataKey="surplus_thb" name="Surplus" fill="#d97706" />
                <Bar dataKey="deficit_thb" name="Deficit" fill="#dc2626" />
                <Bar dataKey="rebalanceable_thb" name="Rebalanceable" fill="#059669" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <SortableTable columns={brandCols} data={brand_opportunities} defaultSort="rebalanceable_thb" />
        </div>
      )}
    </div>
  );
}

// ──────────────────── MAIN PAGE ────────────────────
const VALID_ALLOC_TABS = TABS.map((t) => t.id);

export default function StockAllocationPage() {
  const searchParams = useSearchParams();
  const urlTab = searchParams.get("tab");
  const urlBrand = searchParams.get("brand");

  const [tab, setTab] = useState(
    VALID_ALLOC_TABS.includes(urlTab) ? urlTab : "allocation"
  );
  const [allocData, setAllocData] = useState(null);
  const [transferData, setTransferData] = useState(null);
  const [rebalData, setRebalData] = useState(null);
  const [loading, setLoading] = useState({ allocation: false, transfers: false, rebalancing: false });
  const [errors, setErrors] = useState({});
  const [brandFilter, setBrandFilter] = useState(urlBrand || "");

  const fetchAllocation = useCallback(async (brand, signal) => {
    setLoading((p) => ({ ...p, allocation: true }));
    setErrors((p) => ({ ...p, allocation: null }));
    try {
      const params = {};
      if (brand) params.brand = brand;
      const { data } = await api.get("/api/stock_allocation", { params, signal });
      setAllocData(data);
    } catch (e) {
      if (!isAbortError(e)) {
        setErrors((p) => ({ ...p, allocation: e.message }));
      }
    } finally {
      setLoading((p) => ({ ...p, allocation: false }));
    }
  }, []);

  const fetchTransfers = useCallback(async (signal) => {
    setLoading((p) => ({ ...p, transfers: true }));
    setErrors((p) => ({ ...p, transfers: null }));
    try {
      const { data } = await api.get("/api/transfer_history", { signal });
      setTransferData(data);
    } catch (e) {
      if (!isAbortError(e)) {
        setErrors((p) => ({ ...p, transfers: e.message }));
      }
    } finally {
      setLoading((p) => ({ ...p, transfers: false }));
    }
  }, []);

  const fetchRebalancing = useCallback(async (signal) => {
    setLoading((p) => ({ ...p, rebalancing: true }));
    setErrors((p) => ({ ...p, rebalancing: null }));
    try {
      const { data } = await api.get("/api/rebalancing_summary", { signal });
      setRebalData(data);
    } catch (e) {
      if (!isAbortError(e)) {
        setErrors((p) => ({ ...p, rebalancing: e.message }));
      }
    } finally {
      setLoading((p) => ({ ...p, rebalancing: false }));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchAllocation(urlBrand || "", controller.signal);
    fetchTransfers(controller.signal);
    fetchRebalancing(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchAllocation, fetchTransfers, fetchRebalancing]);

  const handleBrandFilter = () => {
    fetchAllocation(brandFilter);
  };

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)] p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold text-[var(--nichi-blue)] mb-1">Stock Allocation Optimization</h1>
        <p className="text-sm text-gray-500 mb-6">
          Identify overstocked and understocked locations, get transfer recommendations, and analyze stock movement patterns.
        </p>

        {/* Tab Bar */}
        <div className="flex space-x-1 bg-white rounded-lg shadow p-1 mb-6">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-colors ${
                tab === t.id
                  ? "bg-[var(--nichi-blue)] text-white"
                  : "text-gray-600 hover:bg-gray-100"
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Brand filter for allocation tab */}
        {tab === "allocation" && (
          <div className="flex items-center gap-2 mb-4">
            <input
              type="text"
              placeholder="Filter by brand (e.g. ToyWorld)"
              value={brandFilter}
              onChange={(e) => setBrandFilter(e.target.value)}
              className="border rounded px-3 py-1.5 text-sm w-64"
            />
            <button
              onClick={handleBrandFilter}
              className="bg-[var(--nichi-blue)] text-white text-sm px-4 py-1.5 rounded"
            >
              Apply
            </button>
            {brandFilter && (
              <button
                onClick={() => { setBrandFilter(""); fetchAllocation(""); }}
                className="text-sm text-gray-500 underline"
              >
                Clear
              </button>
            )}
          </div>
        )}

        {/* Tab Content */}
        {tab === "allocation" && (errors.allocation ? <ErrorBanner message={errors.allocation} onRetry={() => fetchAllocation(brandFilter)} /> : <AllocationTab data={allocData} loading={loading.allocation} />)}
        {tab === "transfers" && (errors.transfers ? <ErrorBanner message={errors.transfers} onRetry={() => fetchTransfers()} /> : <TransferHistoryTab data={transferData} loading={loading.transfers} />)}
        {tab === "rebalancing" && (errors.rebalancing ? <ErrorBanner message={errors.rebalancing} onRetry={() => fetchRebalancing()} /> : <RebalancingTab data={rebalData} loading={loading.rebalancing} />)}
      </div>
    </div>
  );
}
