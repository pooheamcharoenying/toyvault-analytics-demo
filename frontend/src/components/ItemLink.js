import Link from "next/link";

/**
 * Clickable ItemCode that links to the Item Detail page.
 * Used across Inventory Alerts, Product Analytics, Stock Allocation, etc.
 */
export default function ItemLink({ code }) {
  if (!code) return "—";
  return (
    <Link
      href={`/dashboards/item-detail/${encodeURIComponent(code)}`}
      className="text-[var(--nichi-blue)] hover:underline font-medium"
    >
      {code}
    </Link>
  );
}
