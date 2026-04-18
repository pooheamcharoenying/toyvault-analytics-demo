"use client";

import { useCallback, useEffect, useState } from "react";
import api from "@/utils/api";

const SEVERITY_STYLES = {
  critical: "border-red-300 bg-red-50",
  warning: "border-amber-300 bg-amber-50",
  info: "border-blue-300 bg-blue-50",
};

const SEVERITY_ICON = {
  critical: "!",
  warning: "!",
  info: "i",
};

const SEVERITY_ICON_STYLE = {
  critical: "bg-red-500 text-white",
  warning: "bg-amber-500 text-white",
  info: "bg-blue-500 text-white",
};

function RecommendationItem({ rec }) {
  const style = SEVERITY_STYLES[rec.severity] || SEVERITY_STYLES.info;
  const iconStyle = SEVERITY_ICON_STYLE[rec.severity] || SEVERITY_ICON_STYLE.info;
  const icon = SEVERITY_ICON[rec.severity] || "i";

  return (
    <div className={`border rounded-lg p-3 ${style} flex gap-3 items-start`}>
      <span
        className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${iconStyle}`}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <p className="font-semibold text-sm text-gray-900">{rec.title}</p>
        <p className="text-sm text-gray-700 mt-0.5">{rec.text}</p>
        <p className="text-[10px] text-gray-400 mt-1">Rule: {rec.rule_id}</p>
      </div>
    </div>
  );
}

/**
 * Fetches and displays rule-based recommendations for a page context.
 *
 * Usage:
 *   <RecommendationPanel context="brand" name="Silverlit" years={[2025]} />
 *   <RecommendationPanel context="location" name="Robinson Rama9" years={[2025]} />
 *   <RecommendationPanel context="item" name="SV20725" years={[2025]} />
 */
export default function RecommendationPanel({ context, name, years }) {
  const [recs, setRecs] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchRecs = useCallback(
    (signal) => {
      if (!context || !name) return;
      setLoading(true);
      const qs = new URLSearchParams();
      qs.set("context", context);
      qs.set("name", name);
      if (years) years.forEach((y) => qs.append("year_list", String(y)));
      api
        .get(`/api/recommendations?${qs.toString()}`, { signal })
        .then((res) => {
          setRecs(res.data?.recommendations || []);
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    },
    [context, name, years]
  );

  useEffect(() => {
    const ctrl = new AbortController();
    fetchRecs(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchRecs]);

  if (loading) return null; // Don't show loading state for recommendations — they're supplementary
  if (!recs.length) return null;

  return (
    <div className="bg-white rounded-xl shadow-md p-5">
      <h3 className="text-base font-semibold text-gray-800 mb-3 flex items-center gap-2">
        <span className="text-lg">Recommendations</span>
        <span className="text-xs text-gray-400 font-normal">
          ({recs.length} insight{recs.length !== 1 ? "s" : ""})
        </span>
      </h3>
      <div className="space-y-2">
        {recs.map((rec, i) => (
          <RecommendationItem key={`${rec.rule_id}-${i}`} rec={rec} />
        ))}
      </div>
    </div>
  );
}
