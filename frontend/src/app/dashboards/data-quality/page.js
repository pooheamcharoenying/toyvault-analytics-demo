"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  Legend,
} from "recharts";
import api, { isAbortError } from "@/utils/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBanner from "@/components/ErrorBanner";
import { fmtThb, fmtQty, fmtPct } from "@/utils/formatters";

const TIER_COLORS = {
  master: "#059669",       // green — authoritative
  sale_derived: "#2563eb", // blue — recovered from sales
  sale: "#2563eb",
  prefix: "#d97706",       // amber — inferred
  grpo_fob: "#d97706",
  unpriceable: "#dc2626",  // red — truly missing
  unknown: "#dc2626",
};

const TIER_LABELS = {
  master: "Item Master (authoritative)",
  sale_derived: "Recovered from Sale.Price Master",
  sale: "Recovered from Sale.Brand",
  grpo_fob: "Recovered from GRPO FOB",
  prefix: "Inferred from item-code prefix",
  unpriceable: "No price data anywhere",
  unknown: "No brand data anywhere",
};

function KpiCard({ label, value, sub, tone = "default" }) {
  const toneClass = {
    default: "bg-white",
    good: "bg-green-50 border-green-200",
    warn: "bg-amber-50 border-amber-200",
    bad: "bg-red-50 border-red-200",
  }[tone];
  return (
    <div className={`${toneClass} border border-gray-200 rounded-lg p-4`}>
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</div>
      <div className="text-2xl font-bold text-gray-800 mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

function TierBreakdown({ title, tiers }) {
  // tiers: object { master: N, sale_derived: N, ... }
  const rows = Object.entries(tiers)
    .filter(([, v]) => v > 0)
    .map(([source, count]) => ({
      source,
      label: TIER_LABELS[source] || source,
      count,
      fill: TIER_COLORS[source] || "#6b7280",
    }));
  const total = rows.reduce((s, r) => s + r.count, 0);
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5">
      <h3 className="text-base font-semibold text-gray-800 mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={rows} layout="vertical" margin={{ left: 20, right: 40 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" />
          <YAxis type="category" dataKey="label" width={240} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v) => `${fmtQty(v)} items (${fmtPct(v / total * 100, 1)})`} />
          <Bar dataKey="count">
            {rows.map((r, i) => (
              <Cell key={i} fill={r.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-2 text-xs text-gray-500 text-right">Total: {fmtQty(total)} items</div>
    </div>
  );
}

export default function DataQualityPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    api
      .get("/api/data_quality", { signal })
      .then((r) => setData(r.data))
      .catch((e) => {
        if (!isAbortError(e)) setError(e.message || "Failed to load data quality summary");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const c = new AbortController();
    loadData(c.signal);
    return () => c.abort();
  }, [loadData]);

  if (loading) return <div className="p-8"><LoadingSpinner /></div>;
  if (error) return <div className="p-8"><ErrorBanner message={error} onRetry={() => loadData()} /></div>;
  if (!data) return null;

  const ov = data.overview || {};
  const rev = data.revenue_coverage || {};
  const oh = data.onhand_coverage || {};

  return (
    <div className="min-h-screen bg-[var(--nichi-gray-50)] p-6">
      <div className="max-w-[1400px] mx-auto">
        <div className="mb-4 text-sm text-gray-500">
          <span>Home</span>
          <span className="mx-2">/</span>
          <span className="text-gray-800 font-medium">Data Quality</span>
        </div>

        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[var(--nichi-blue)]">Data Quality</h1>
          <p className="text-gray-600 text-sm mt-1">
            Item Master coverage and data-recovery tier breakdown. Surfaces how much of
            the business is attributed to authoritative master data vs. recovered from
            Sale / GRPO fallbacks vs. truly missing.
          </p>
        </div>

        {/* Overview KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KpiCard
            label="Total Unique Items"
            value={fmtQty(ov.total_unique_items)}
            sub={`${fmtQty(ov.items_in_master)} in Item Master`}
          />
          <KpiCard
            label="Missing from Master"
            value={fmtQty(ov.items_missing_from_master)}
            sub={`${fmtPct(100 - (ov.pct_items_covered_by_master || 0), 1)} of universe`}
            tone={(ov.pct_items_covered_by_master || 0) < 50 ? "bad" : "warn"}
          />
          <KpiCard
            label="Revenue from Master Items"
            value={fmtThb(rev.from_master_items_thb)}
            sub={`${fmtPct(rev.pct_revenue_from_master, 1)} of ${fmtThb(rev.total_revenue_thb)} total`}
            tone={rev.pct_revenue_from_master > 70 ? "good" : "warn"}
          />
          <KpiCard
            label="Revenue Unattributed"
            value={fmtThb(rev.from_unmapped_items_thb)}
            sub="From items missing from Item Master"
            tone="bad"
          />
        </div>

        {/* On-hand value recovery */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <KpiCard
            label="On-Hand Value (Master only)"
            value={fmtThb(oh.value_master_only_thb)}
            sub="What dashboards showed before recovery"
          />
          <KpiCard
            label="On-Hand Value (with recovery)"
            value={fmtThb(oh.value_with_recovery_thb)}
            sub="Using Sale & GRPO fallbacks for missing items"
            tone="good"
          />
          <KpiCard
            label="Value Recovered"
            value={fmtThb(oh.value_recovery_gain_thb)}
            sub={`${fmtQty(oh.units_unmapped)} unmapped units (${fmtPct(oh.pct_units_unmapped, 1)})`}
            tone="good"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <TierBreakdown title="Price Coverage by Tier" tiers={data.price_coverage || {}} />
          <TierBreakdown title="Brand Coverage by Tier" tiers={data.brand_coverage || {}} />
        </div>

        <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-gray-700">
          <p className="font-semibold mb-1 text-[var(--nichi-blue-dark)]">How recovery works</p>
          <ol className="list-decimal list-inside space-y-1">
            <li>
              <span className="font-medium">Price:</span> Item Master.Price → Sale.Price Master ÷ Quantity → GRPO FOB × 2.5 markup.
              The Item Master is never overridden; fallbacks only fill gaps.
            </li>
            <li>
              <span className="font-medium">Brand:</span> Item Master.GroupName → Sale.Brand (most common per item) → Item-code prefix
              inference (e.g. AE→AeroBot, SN→StackNova).
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
