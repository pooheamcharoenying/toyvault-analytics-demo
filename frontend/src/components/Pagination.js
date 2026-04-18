"use client";

/**
 * Shared pagination component for large data tables.
 *
 * @param {number}   totalItems    - Total number of items
 * @param {number}   currentPage   - Current page (1-based)
 * @param {number}   pageSize      - Items per page (default 50)
 * @param {function} onPageChange  - Callback when page changes
 * @param {string}   [className]   - Additional CSS classes
 */
export default function Pagination({
  totalItems,
  currentPage,
  pageSize = 50,
  onPageChange,
  className = "",
}) {
  const safeTotalItems = totalItems != null && !Number.isNaN(totalItems) ? totalItems : 0;
  const totalPages = Math.max(1, Math.ceil(safeTotalItems / pageSize));
  if (safeTotalItems <= pageSize) return null; // No pagination needed

  const start = (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, safeTotalItems);

  return (
    <div
      className={`flex items-center justify-between text-sm text-slate-600 py-2 ${className}`}
    >
      <span>
        Showing {start}–{end} of {safeTotalItems.toLocaleString()} items
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          className="px-3 py-1 rounded border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ← Prev
        </button>
        <span className="px-2">
          Page {currentPage} of {totalPages}
        </span>
        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className="px-3 py-1 rounded border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next →
        </button>
      </div>
    </div>
  );
}

/**
 * Helper hook-like function to paginate an array.
 * @param {Array} items - Full array of items
 * @param {number} page - Current page (1-based)
 * @param {number} pageSize - Items per page
 * @returns {Array} - Slice for the current page
 */
export function paginateArray(items, page, pageSize = 50) {
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}
