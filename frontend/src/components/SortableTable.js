"use client";
import { useState } from "react";
import Link from "next/link";
import InfoTooltip from "@/components/InfoTooltip";

/**
 * Shared SortableTable component — one definition for all dashboard pages.
 *
 * Column definition shape:
 *   { key: string, label: string, tooltip?: ReactNode,
 *     render?: (value, row) => ReactNode,
 *     fmt?: (value, row?) => string|ReactNode,
 *     linkFn?: (row) => string }
 *
 * - `render` takes priority over `fmt` and `linkFn`
 * - `linkFn` wraps the cell in a <Link>; formatted by `fmt` if also present
 * - `fmt` is a simple value formatter when neither `render` nor `linkFn` are set
 */
export default function SortableTable({
  columns,
  data,
  defaultSort,
  defaultDir = "desc",
  totalCount,
  pageSize = 50,
  paginate = true,
}) {
  const safeColumns = Array.isArray(columns) ? columns : [];
  const safeData = Array.isArray(data) ? data : [];

  const [sortKey, setSortKey] = useState(defaultSort || safeColumns[0]?.key);
  const [sortDir, setSortDir] = useState(defaultDir);
  const [page, setPage] = useState(1);

  if (!safeColumns.length) return null;

  const sorted = [...safeData].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "number" && typeof vb === "number")
      return sortDir === "asc" ? va - vb : vb - va;
    return sortDir === "asc"
      ? String(va).localeCompare(String(vb))
      : String(vb).localeCompare(String(va));
  });

  const toggle = (key) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(defaultDir); }
    setPage(1);
  };

  const showingCount = sorted.length;
  const total = totalCount != null ? totalCount : showingCount;
  const shouldPaginate = paginate && showingCount > pageSize;
  const totalPages = shouldPaginate ? Math.max(1, Math.ceil(showingCount / pageSize)) : 1;
  const safePage = Math.min(page, totalPages);
  const rows = shouldPaginate
    ? sorted.slice((safePage - 1) * pageSize, safePage * pageSize)
    : sorted;

  const renderCell = (col, row) => {
    const val = row[col.key];
    if (col.render) return col.render(val, row);
    const display = col.fmt ? col.fmt(val, row) : (val ?? "\u2014");
    if (col.linkFn) {
      return (
        <Link href={col.linkFn(row)} className="text-[var(--nichi-blue)] hover:underline font-medium">
          {display}
        </Link>
      );
    }
    return display;
  };

  return (
    <div className="overflow-x-auto">
      {showingCount > 0 && (
        <p className="text-xs text-gray-500 mb-1 px-1">
          {total !== showingCount
            ? `Showing ${showingCount} of ${total} items`
            : `${showingCount} items`}
        </p>
      )}
      <table className="min-w-full text-sm border-collapse">
        <thead>
          {/* Headers freeze during vertical scroll. First-column header
              gets a higher z-index than other headers so the row+column
              intersection paints on top of everything. */}
          <tr className="bg-gray-50 border-b">
            {safeColumns.map((col, idx) => {
              const isFirstColumn = idx === 0;
              const stickyClasses = isFirstColumn
                ? "sticky top-0 left-0 z-30 bg-gray-50"
                : "sticky top-0 z-20 bg-gray-50";
              // Columns opt OUT with `sortable: false` — used for action
              // columns (buttons/links) whose key maps to no real field, where
              // a sort arrow would invite a click that does nothing. Defaults
              // to sortable so every existing column is unaffected.
              const isSortable = col.sortable !== false;
              return (
                <th
                  key={col.key}
                  role="columnheader"
                  aria-sort={
                    !isSortable
                      ? undefined
                      : sortKey === col.key
                        ? sortDir === "asc" ? "ascending" : "descending"
                        : "none"
                  }
                  tabIndex={isSortable ? 0 : undefined}
                  onClick={isSortable ? () => toggle(col.key) : undefined}
                  onKeyDown={
                    isSortable
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggle(col.key);
                          }
                        }
                      : undefined
                  }
                  className={`px-3 py-2 text-left font-semibold text-gray-700 whitespace-nowrap select-none border-b ${
                    isSortable ? "cursor-pointer hover:bg-gray-100" : ""
                  } ${stickyClasses}`}
                >
                  {col.label}
                  {col.tooltip && <InfoTooltip text={col.tooltip} />}
                  {isSortable && (
                    <>
                      {" "}
                      {sortKey === col.key ? (sortDir === "asc" ? "↑" : "↓") : "↕"}
                    </>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            // Alternating row backgrounds — explicit (not bg-inherit) so the
            // sticky first column also gets the right colour. bg-inherit can
            // misbehave on sticky cells in some browsers.
            const rowBg = i % 2 === 0 ? "bg-white" : "bg-gray-50";
            return (
              <tr key={i} className={rowBg}>
                {safeColumns.map((col, idx) => {
                  const isFirstColumn = idx === 0;
                  const stickyClasses = isFirstColumn
                    ? `sticky left-0 z-10 ${rowBg}`
                    : "";
                  return (
                    <td
                      key={col.key}
                      className={`px-3 py-2 border-b whitespace-nowrap ${stickyClasses}`}
                    >
                      {renderCell(col, row)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={safeColumns.length} className="px-3 py-8 text-center text-gray-400">
                No data
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {shouldPaginate && (
        <div className="flex items-center justify-between text-sm text-slate-600 py-2 px-1">
          <span>Page {safePage} of {totalPages} ({showingCount} items)</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(safePage - 1)}
              disabled={safePage <= 1}
              className="px-3 py-1 rounded border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed text-xs"
            >
              ← Prev
            </button>
            <button
              onClick={() => setPage(safePage + 1)}
              disabled={safePage >= totalPages}
              className="px-3 py-1 rounded border border-slate-200 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed text-xs"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
