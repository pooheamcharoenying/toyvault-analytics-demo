/**
 * Reusable ABCDE tier badge for products and locations.
 *
 * Renders a small colored pill showing the ABCDE class with a tooltip
 * explaining the tier meaning. Used on brands, locations, and item detail pages.
 *
 * Colors: A=green, B=blue, C=amber, D=orange, E=red
 */

const CLASS_CONFIG = {
  A: {
    bg: "bg-green-100 text-green-800 border-green-300",
    tooltip: "Class A — Star performer, top 50% of revenue",
  },
  B: {
    bg: "bg-blue-100 text-blue-800 border-blue-300",
    tooltip: "Class B — Strong performer, top 80% of revenue",
  },
  C: {
    bg: "bg-amber-100 text-amber-800 border-amber-300",
    tooltip: "Class C — Average, top 95% of revenue",
  },
  D: {
    bg: "bg-orange-100 text-orange-800 border-orange-300",
    tooltip: "Class D — Weak, top 99% of revenue. Consider markdown or promotion.",
  },
  E: {
    bg: "bg-red-100 text-red-800 border-red-300",
    tooltip: "Class E — Bottom 1% of revenue. Consider discontinuation or liquidation.",
  },
};

/** Numeric sort value so SortableTable can sort A→E or E→A */
export const ABCDE_SORT_VALUE = { A: 1, B: 2, C: 3, D: 4, E: 5 };

export default function AbcdeBadge({ tier, context }) {
  const cls = tier ? String(tier).toUpperCase() : "";
  const cfg = CLASS_CONFIG[cls];
  if (!cfg) return <span className="text-gray-400">—</span>;

  const title = context ? `${cfg.tooltip} (${context})` : cfg.tooltip;

  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold border ${cfg.bg} cursor-default`}
      title={title}
    >
      {cls}
    </span>
  );
}
