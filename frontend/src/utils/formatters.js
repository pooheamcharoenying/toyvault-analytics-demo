/**
 * Shared number formatting utilities for consistent display across all pages.
 *
 * Standard rules:
 * - Currency (THB): "฿1,234,567" via fmtThb()
 * - Short currency:  "฿12.5M" or "฿500K" via fmtThbShort()
 * - Quantities:      "1,234,567" via fmtQty()
 * - Percentages:     "45.2%" (1 decimal) via fmtPct()
 * - Null/missing:    "—" (em dash), never blank, never "null"
 */

/** Format THB currency: "฿1,234,567" */
export function fmtThb(n) {
  if (n == null || Number.isNaN(n)) return "\u2014";
  return "\u0E3F" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/** Format THB abbreviated: "฿12.5M" or "฿500K" */
export function fmtThbShort(n) {
  if (n == null || Number.isNaN(n)) return "\u2014";
  const v = Number(n);
  if (Math.abs(v) >= 1e6) return "\u0E3F" + (v / 1e6).toFixed(1) + "M";
  if (Math.abs(v) >= 1e3) return "\u0E3F" + (v / 1e3).toFixed(0) + "K";
  return "\u0E3F" + v.toFixed(0);
}

/** Format quantity with comma separators: "1,234,567" */
export function fmtQty(n) {
  if (n == null || Number.isNaN(n)) return "\u2014";
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/** Format percentage with 1 decimal: "45.2%" */
export function fmtPct(n) {
  if (n == null || Number.isNaN(n)) return "\u2014";
  return Number(n).toFixed(1) + "%";
}

/** Format days of cover: "180d", or "∞" for very large values */
export function fmtDays(n) {
  if (n == null || Number.isNaN(n) || n >= 99999) return "\u221E";
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }) + "d";
}

/** Format ratio to 2 decimals: "1.25" or "1.25x" with optional suffix */
export function fmtRatio(n, suffix = "") {
  if (n == null || Number.isNaN(n)) return "\u2014";
  return Number(n).toFixed(2) + suffix;
}
