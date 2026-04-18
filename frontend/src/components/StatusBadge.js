/**
 * Shared colored badge for status labels (surplus/deficit/balanced, green/yellow/red, etc).
 * Merges a default color map with any custom overrides passed via the `colors` prop.
 */

const DEFAULT_COLORS = {
  // Health / traffic light
  green: "bg-green-100 text-green-800",
  yellow: "bg-amber-100 text-amber-800",
  red: "bg-red-100 text-red-800",
  // Stock allocation
  surplus: "bg-amber-100 text-amber-800",
  deficit: "bg-red-100 text-red-800",
  balanced: "bg-green-100 text-green-800",
  // Priority
  high: "bg-red-100 text-red-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-green-100 text-green-800",
  // Severity
  critical: "bg-red-100 text-red-800",
  warning: "bg-amber-100 text-amber-800",
  watch: "bg-blue-100 text-blue-800",
  info: "bg-gray-100 text-gray-700",
};

export default function StatusBadge({ status, colors }) {
  const map = colors ? { ...DEFAULT_COLORS, ...colors } : DEFAULT_COLORS;
  const cls = map[status] || "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {status}
    </span>
  );
}
