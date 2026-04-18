/**
 * Shared CSV export utilities.
 * Replaces inline downloadCsv/downloadCSV functions duplicated across 10+ pages.
 */

function escapeCell(v) {
  const s = v == null ? "" : String(v);
  return s.includes(",") || s.includes('"') || s.includes("\n")
    ? '"' + s.replaceAll('"', '""') + '"'
    : s;
}

/**
 * Download a CSV file from explicit headers and row arrays.
 * @param {string} filename - e.g. "stockout_risk.csv"
 * @param {string[]} headers - column headers
 * @param {Array<Array<*>>} rows - array of value arrays (one per row)
 */
export function downloadCsv(filename, headers, rows) {
  const lines = [headers.map(escapeCell).join(",")];
  rows.forEach((r) => lines.push(r.map(escapeCell).join(",")));
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Download a CSV file from an array of objects (headers derived from keys).
 * @param {Object[]} rows - array of objects
 * @param {string} filename - e.g. "item_detail.csv"
 */
export function downloadCsvFromObjects(rows, filename) {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const lines = [keys.map(escapeCell).join(",")];
  rows.forEach((r) => lines.push(keys.map((k) => escapeCell(r[k])).join(",")));
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
