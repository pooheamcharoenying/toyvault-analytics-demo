"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import api, { isAbortError } from "@/utils/api";
import Link from "next/link";
import InfoTooltip, { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
import ErrorBanner from "@/components/ErrorBanner";
import { downloadCsv } from "@/utils/csvExport";

/* ── colour / label helpers ────────────────────────────────────────── */
const SEV_STYLE = {
  critical: {
    border: "border-l-4 border-red-600",
    badge: "bg-red-100 text-red-800",
    icon: "\u26A0",
  },
  warning: {
    border: "border-l-4 border-amber-500",
    badge: "bg-amber-100 text-amber-800",
    icon: "\u25B2",
  },
  info: {
    border: "border-l-4 border-blue-400",
    badge: "bg-blue-100 text-blue-800",
    icon: "\u2139",
  },
};

const TYPE_LABEL = {
  reorder: "Reorder",
  transfer: "Transfer Stock",
  markdown: "Markdown / Liquidate / Promotions",
  investigate: "Investigate",
};

const TYPE_ICON = {
  reorder: "\uD83D\uDCE6",
  transfer: "\uD83D\uDE9A",
  markdown: "\uD83C\uDFF7\uFE0F",
  investigate: "\uD83D\uDD0D",
};

import { fmtThb } from "@/utils/formatters";

const TYPE_ORDER = ["reorder", "transfer", "markdown", "investigate"];

function downloadActionsCSV(actions) {
  if (!actions.length) return;
  const headers = ["Rank", "Severity", "Type", "Title", "Reason", "Impact (THB)", "Link"];
  const rows = actions.map((a, i) => [
    i + 1,
    a.severity,
    TYPE_LABEL[a.type] || a.type,
    a.title || "",
    a.reason || "",
    a.impact_thb ?? "",
    a.link || "",
  ]);
  downloadCsv("priority_actions.csv", headers, rows);
}

/* ── localStorage helpers for acknowledge state ────────────────────── */
const ACK_STORAGE_KEY = "nichiworld_actions_ack";
const ACK_DATE_KEY = "nichiworld_actions_ack_date";

function hashAction(action) {
  // Simple hash from title + type to identify an action across refreshes
  return `${action.type}::${action.title}`;
}

function loadAcknowledged(dataDate) {
  try {
    const storedDate = localStorage.getItem(ACK_DATE_KEY);
    // Reset if data file date changed
    if (storedDate && storedDate !== dataDate) {
      localStorage.removeItem(ACK_STORAGE_KEY);
      localStorage.setItem(ACK_DATE_KEY, dataDate || "");
      return new Set();
    }
    if (dataDate) localStorage.setItem(ACK_DATE_KEY, dataDate);
    const raw = localStorage.getItem(ACK_STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function saveAcknowledged(ackSet) {
  try {
    localStorage.setItem(ACK_STORAGE_KEY, JSON.stringify([...ackSet]));
  } catch {
    // localStorage full or unavailable — ignore
  }
}

/* ── main page component ────────────────────────────────────────────── */
export default function ActionsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterType, setFilterType] = useState("all");
  const [filterSeverity, setFilterSeverity] = useState("all");
  const [acknowledged, setAcknowledged] = useState(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState(new Set());

  const loadData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    api
      .get("/api/priority_actions", { signal })
      .then((res) => {
        setData(res.data);
        // Load acknowledged state, resetting if data date changed
        const ack = loadAcknowledged(res.data?.as_of || "");
        setAcknowledged(ack);
      })
      .catch((err) => {
        if (!isAbortError(err)) setError(err.response?.data?.error || err.message);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  const toggleAck = useCallback((action) => {
    setAcknowledged((prev) => {
      const next = new Set(prev);
      const key = hashAction(action);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      saveAcknowledged(next);
      return next;
    });
  }, []);

  const toggleGroup = useCallback((type) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  // Clicking a type badge sets the filter (or clears it if already active)
  const handleTypeBadgeClick = useCallback((type) => {
    setFilterType((prev) => (prev === type ? "all" : type));
  }, []);

  // Filtered actions (excluding acknowledged unless showing all)
  const { activeActions, ackedActions, grouped } = useMemo(() => {
    if (!data?.actions) return { activeActions: [], ackedActions: [], grouped: {} };

    const filtered = data.actions.filter((a) => {
      if (filterType !== "all" && a.type !== filterType) return false;
      if (filterSeverity !== "all" && a.severity !== filterSeverity) return false;
      return true;
    });

    const active = [];
    const acked = [];
    filtered.forEach((a) => {
      if (acknowledged.has(hashAction(a))) acked.push(a);
      else active.push(a);
    });

    // Group active actions by type
    const groups = {};
    active.forEach((a) => {
      if (!groups[a.type]) groups[a.type] = [];
      groups[a.type].push(a);
    });

    return { activeActions: active, ackedActions: acked, grouped: groups };
  }, [data, filterType, filterSeverity, acknowledged]);

  const ackCount = acknowledged.size;
  const totalFiltered = (data?.actions || []).filter((a) => {
    if (filterType !== "all" && a.type !== filterType) return false;
    if (filterSeverity !== "all" && a.severity !== filterSeverity) return false;
    return true;
  }).length;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#1a3a8f] mx-auto mb-4" />
          <p className="text-gray-600">Analysing business priorities...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return <ErrorBanner message={error} onRetry={() => loadData()} className="m-8" />;
  }

  if (!data || !data.actions) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">No action data available.</p>
      </div>
    );
  }

  // Determine which types exist in the data for ordered rendering
  const orderedTypes = TYPE_ORDER.filter((t) => grouped[t]?.length > 0);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* ── header ──────────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-[#1a3a8f] to-[#0f2560] text-white px-6 py-6">
        <h1 className="text-2xl font-bold">Priority Actions</h1>
        <p className="text-blue-200 text-sm mt-1">
          The most urgent business actions ranked by severity and impact.
          {data.as_of && <span> Data as of {data.as_of}.</span>}
        </p>
      </div>

      {/* ── KPI strip ───────────────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-4 -mt-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <KpiCard
            label="Total Actions"
            value={data.total_actions}
            color="bg-[#1a3a8f]"
          />
          <KpiCard
            label="Critical"
            value={data.by_severity?.critical || 0}
            color="bg-red-600"
          />
          <KpiCard
            label="Warning"
            value={data.by_severity?.warning || 0}
            color="bg-amber-500"
          />
          <KpiCard
            label="Acknowledged"
            value={`${ackCount} of ${data.total_actions}`}
            color="bg-gray-500"
          />
          <KpiCard
            label="Total Impact"
            value={fmtThb(data.total_impact_thb)}
            color="bg-emerald-600"
            tooltip={METRIC_TOOLTIPS.actions?.impact_thb}
          />
        </div>
      </div>

      {/* ── type summary badges (clickable — OBJ-26) ──────────── */}
      <div className="max-w-7xl mx-auto px-4 mt-4">
        <div className="flex flex-wrap gap-3">
          {Object.entries(data.by_type || {}).map(([t, count]) => {
            const isActive = filterType === t;
            return (
              <button
                key={t}
                onClick={() => handleTypeBadgeClick(t)}
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border shadow-sm transition-all cursor-pointer ${
                  isActive
                    ? "bg-[#1a3a8f] text-white border-[#1a3a8f] shadow-md"
                    : "bg-white hover:bg-gray-50 border-gray-200"
                }`}
              >
                <span>{TYPE_ICON[t] || ""}</span>
                <span>{TYPE_LABEL[t] || t}</span>
                <span className={`rounded-full px-2 text-xs font-bold ${isActive ? "bg-white/20" : "bg-gray-100"}`}>{count}</span>
              </button>
            );
          })}
          {filterType !== "all" && (
            <button
              onClick={() => setFilterType("all")}
              className="text-xs text-gray-500 underline self-center ml-1"
            >
              Clear filter
            </button>
          )}
        </div>
      </div>

      {/* ── filters ─────────────────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-4 mt-4 flex flex-wrap gap-3">
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm bg-white"
        >
          <option value="all">All Types</option>
          {[...new Set(data.actions.map((a) => a.type))].map((t) => (
            <option key={t} value={t}>{TYPE_LABEL[t] || t}</option>
          ))}
        </select>
        <select
          value={filterSeverity}
          onChange={(e) => setFilterSeverity(e.target.value)}
          className="border rounded px-3 py-1.5 text-sm bg-white"
        >
          <option value="all">All Severities</option>
          {[...new Set(data.actions.map((a) => a.severity))].map((s) => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
          ))}
        </select>
        <button
          onClick={() => downloadActionsCSV([...activeActions, ...ackedActions])}
          className="px-3 py-1.5 text-sm bg-[#1a3a8f] text-white rounded-lg hover:bg-[#0f2560] transition"
        >
          Export CSV
        </button>
        <span className="text-sm text-gray-500 self-center">
          Showing {totalFiltered} of {data.total_actions} actions
          {ackCount > 0 && <span className="ml-1">({ackCount} acknowledged)</span>}
        </span>
      </div>

      {/* ── grouped action cards ────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {orderedTypes.length === 0 && ackedActions.length === 0 && (
          <p className="text-center text-gray-400 py-12">No actions match the selected filters.</p>
        )}

        {orderedTypes.map((type) => {
          const items = grouped[type];
          const isCollapsed = collapsedGroups.has(type);
          const critCount = items.filter((a) => a.severity === "critical").length;
          const warnCount = items.filter((a) => a.severity === "warning").length;

          return (
            <div key={type} className="bg-white rounded-xl shadow-sm border overflow-hidden">
              {/* Group header — always visible */}
              <button
                onClick={() => toggleGroup(type)}
                className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-lg">{TYPE_ICON[type]}</span>
                  <span className="font-semibold text-gray-900">{TYPE_LABEL[type] || type}</span>
                  <span className="bg-[#1a3a8f] text-white rounded-full px-2.5 py-0.5 text-xs font-bold">{items.length}</span>
                  {critCount > 0 && (
                    <span className="bg-red-100 text-red-700 rounded-full px-2 py-0.5 text-xs font-semibold">{critCount} critical</span>
                  )}
                  {warnCount > 0 && (
                    <span className="bg-amber-100 text-amber-700 rounded-full px-2 py-0.5 text-xs font-semibold">{warnCount} warning</span>
                  )}
                </div>
                <span className="text-gray-400 text-sm">
                  {isCollapsed ? "\u25B6" : "\u25BC"}
                </span>
              </button>

              {/* Group body — collapsible */}
              {!isCollapsed && (
                <div className="border-t px-4 py-3 space-y-3">
                  {items.map((a, i) => (
                    <ActionCard
                      key={i}
                      action={a}
                      rank={i + 1}
                      isAcked={false}
                      onToggleAck={() => toggleAck(a)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {/* ── acknowledged section ───────────────────────────────── */}
        {ackedActions.length > 0 && (
          <div className="bg-gray-100 rounded-xl border border-gray-200 overflow-hidden">
            <button
              onClick={() => toggleGroup("__acked__")}
              className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-200 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg text-gray-400">&#x2713;</span>
                <span className="font-semibold text-gray-500">Acknowledged</span>
                <span className="bg-gray-300 text-gray-700 rounded-full px-2.5 py-0.5 text-xs font-bold">{ackedActions.length}</span>
              </div>
              <span className="text-gray-400 text-sm">
                {collapsedGroups.has("__acked__") ? "\u25B6" : "\u25BC"}
              </span>
            </button>
            {!collapsedGroups.has("__acked__") && (
              <div className="border-t border-gray-200 px-4 py-3 space-y-3">
                {ackedActions.map((a, i) => (
                  <ActionCard
                    key={i}
                    action={a}
                    rank={i + 1}
                    isAcked={true}
                    onToggleAck={() => toggleAck(a)}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── sub-components ─────────────────────────────────────────────────── */

function KpiCard({ label, value, color, tooltip }) {
  return (
    <div className={`${color} text-white rounded-xl shadow-md px-5 py-4`}>
      <p className="text-xs uppercase tracking-wider opacity-80">{label}{tooltip && <InfoTooltip text={tooltip} size="md" />}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
    </div>
  );
}

function ActionCard({ action, rank, isAcked, onToggleAck }) {
  const sev = SEV_STYLE[action.severity] || SEV_STYLE.info;

  return (
    <div className={`rounded-lg shadow-sm ${sev.border} p-4 transition-all ${
      isAcked ? "bg-gray-50 opacity-50" : "bg-white hover:shadow-md"
    }`}>
      <div className="flex items-start justify-between gap-4">
        {/* left: rank + content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-400 font-mono">#{rank}</span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${sev.badge}`}>
              {sev.icon} {action.severity.toUpperCase()}
            </span>
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-700">
              {TYPE_ICON[action.type]} {TYPE_LABEL[action.type] || action.type}
            </span>
          </div>
          <h3 className={`font-semibold mt-1.5 truncate ${isAcked ? "text-gray-500 line-through" : "text-gray-900"}`}>
            {action.title}
          </h3>
          <p className="text-sm text-gray-600 mt-0.5 line-clamp-2">{action.reason}</p>
        </div>

        {/* right: impact + ack button + link */}
        <div className="text-right flex-shrink-0 flex flex-col items-end gap-1">
          <p className="text-lg font-bold text-gray-900">{fmtThb(action.impact_thb)}</p>
          <p className="text-[10px] text-gray-400 uppercase">Impact</p>
          <button
            onClick={onToggleAck}
            className={`mt-1 px-3 py-1 text-xs rounded-full border transition-colors ${
              isAcked
                ? "bg-gray-200 text-gray-600 border-gray-300 hover:bg-gray-300"
                : "bg-green-50 text-green-700 border-green-300 hover:bg-green-100"
            }`}
            title={isAcked ? "Undo acknowledge" : "Mark as handled"}
          >
            {isAcked ? "Undo" : "\u2713 Done"}
          </button>
          {action.link && (
            <Link
              href={action.link}
              className="inline-block mt-1 text-xs text-[#1a3a8f] hover:underline font-medium"
            >
              View details &rarr;
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
