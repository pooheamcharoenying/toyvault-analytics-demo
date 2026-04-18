"use client";
import InfoTooltip from "@/components/InfoTooltip";

/**
 * Shared KPI card component — displays a single metric with optional subtitle.
 *
 * Props:
 *   label  — short title (e.g., "Total Revenue")
 *   value  — the formatted value to display prominently
 *   sub    — optional subtitle / secondary info
 *   tooltip — optional tooltip text explaining the metric
 */
export default function KpiCard({ label, title, value, sub, tooltip }) {
  const displayLabel = label || title;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md transition">
      <p className="text-sm text-slate-500">
        {displayLabel}
        {tooltip && <InfoTooltip text={tooltip} size="md" />}
      </p>
      <p className="text-2xl font-semibold mt-1 tabular-nums text-[var(--nichi-blue-dark)]">
        {value}
      </p>
      {sub && <p className="text-xs text-slate-500 mt-2">{sub}</p>}
    </div>
  );
}
