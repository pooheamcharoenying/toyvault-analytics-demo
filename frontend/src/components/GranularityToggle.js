"use client";

/**
 * Monthly / Weekly granularity toggle for time-series charts.
 *
 * Used across the app — every chart that fetches a backend "trend" endpoint
 * (location_trends, location_brand_trends, brand_at_location_trend, etc.)
 * accepts a ``granularity=monthly|weekly`` query parameter. This toggle is
 * the single UI for switching between the two.
 *
 * Usage in a page:
 *
 *   const [granularity, setGranularity] = useState("monthly");
 *   ...
 *   <GranularityToggle value={granularity} onChange={setGranularity} />
 *   ...
 *   api.get(`/api/location_trends?granularity=${granularity}&...`)
 */
export default function GranularityToggle({ value, onChange, className = "" }) {
  const options = [
    { k: "monthly", label: "Monthly" },
    { k: "weekly", label: "Weekly" },
  ];
  return (
    <div className={`inline-flex items-center gap-2 ${className}`.trim()}>
      <span className="text-xs text-gray-500">View:</span>
      <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden">
        {options.map(({ k, label }) => (
          <button
            key={k}
            type="button"
            onClick={() => onChange(k)}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              value === k
                ? "bg-[var(--nichi-blue)] text-white"
                : "bg-white text-gray-700 hover:bg-gray-100"
            }`}
            aria-pressed={value === k}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
