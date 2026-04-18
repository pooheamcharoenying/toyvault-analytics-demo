// Running-rate chart helpers.
//
// The backend annotates the latest partial month with `is_partial`,
// `days_elapsed`, `days_in_month`, and `running_rate_<field>` values.
// These helpers let charts swap the partial value for the running-rate
// projection so the chart is a fair comparison against prior full months.

/**
 * Returns the value for a field — the running_rate_* value if the month
 * is partial, else the raw value.
 */
export function resolveRunningRate(monthObj, field) {
  if (!monthObj) return null;
  if (monthObj.is_partial && monthObj[`running_rate_${field}`] != null) {
    return monthObj[`running_rate_${field}`];
  }
  return monthObj[field];
}

/**
 * If the last item in an array of monthly objects is a partial month,
 * returns a short human-readable note string; otherwise null.
 */
export function buildPartialNote(months) {
  if (!Array.isArray(months) || months.length === 0) return null;
  const last = months[months.length - 1];
  if (!last?.is_partial) return null;
  return `Latest month projected from ${last.days_elapsed}/${last.days_in_month} days of data`;
}
