/**
 * Shared chart color palette and utilities.
 * Ensures the same entity always gets the same color across all charts.
 */

export const CONSISTENT_PALETTE = [
  "#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed",
  "#0891b2", "#be185d", "#4f46e5", "#0d9488", "#b45309",
  "#9333ea", "#0369a1", "#e11d48", "#15803d", "#c2410c",
  "#1d4ed8", "#a21caf", "#0f766e", "#6366f1", "#7c2d12",
];

export function buildColorMap(names) {
  const map = {};
  (names || []).forEach((name, i) => {
    map[name] = CONSISTENT_PALETTE[i % CONSISTENT_PALETTE.length];
  });
  return map;
}
