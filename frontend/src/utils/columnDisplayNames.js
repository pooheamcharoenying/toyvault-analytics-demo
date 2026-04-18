/**
 * Column Display Name Mapping
 * Transforms coded backend column names into human-readable display names.
 * Rules: No underscores, no coded prefixes, include units, title case.
 *
 * Shared across Operations page (/task2) and all dashboard pages.
 */

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const STATIC_MAP = {
  // Brand/Channel matrix totals
  "Tot_Sold_QTY": "Total Sold (Qty)",
  "Tot_Sold_THB": "Total Sold (THB)",
  "Tot_OnHand_QTY": "Total On-Hand (Qty)",
  "Tot_OnHand_THB": "Total On-Hand (THB @ Master Price)",
  // Average columns
  "LT_Avg_Sold_QTY": "Lifetime Avg Sold (Qty)",
  "LT_Avg_Sold_THB": "Lifetime Avg Sold (THB)",
  "Prev2_Avg_Sold_QTY": "Prev 2-Period Avg Sold (Qty)",
  "Prev2_Avg_Sold_THB": "Prev 2-Period Avg Sold (THB)",
  // Brand Health columns
  "Purchased_Units": "Purchased (Units)",
  "Purchased_FOB_THB": "Purchased FOB (THB)",
  "Purchased_Master_THB": "Purchased Master (THB)",
  "Sold_Units": "Sold (Units)",
  "Sold_THB_Master": "Sold Master (THB)",
  "OnHand_Units": "On-Hand (Units)",
  "OnHand_THB_Master": "On-Hand (THB @ Master Price)",
  "Stock_FOB_THB": "Stock FOB (THB)",
  "Stock_Master_THB": "Stock (THB @ Master Price)",
  // Brand Product P/L columns
  "Brought_QTY": "Purchased (Qty)",
  "Sold_QTY": "Sold (Qty)",
  "OnHand_QTY": "On-Hand (Qty)",
  "FOB_Price": "FOB Price",
  "Exchange_Rate": "Exchange Rate",
  "FOB_Price_THB": "FOB Price (THB)",
  "OnHand_Value_FOB_THB": "On-Hand FOB Value (THB)",
  "Master_Price": "Master Price (THB)",
  "Sale_Value_Master_Price": "Sales at Master Price (THB)",
  "Avg_Sold_Price": "Avg Selling Price (THB)",
  "Sale_Value_Avg_Price": "Sales at Avg Price (THB)",
  "Total_Cost_THB": "Total Cost (THB)",
  "Total_Revenue_THB": "Total Revenue (THB)",
  "Profit_Loss_THB": "Profit / Loss (THB)",
  "Profit_Margin_%": "Profit Margin (%)",
  // Item location/channel columns
  "Total Purchased Units": "Total Purchased (Units)",
  "Total Sold Units": "Total Sold (Units)",
  "Total OnHand Units": "Total On-Hand (Units)",
  "Total OnHand Landed Cost": "On-Hand Landed Cost (THB)",
  "Total Sold Master THB": "Total Sold (THB)",
  "Total OnHand Master THB": "Total On-Hand (THB)",
  "Ratio Units": "Sell-Through Ratio (Units)",
  "Ratio THB": "Sell-Through Ratio (THB)",
  "Purchased Units": "Purchased (Units)",
  "Sold Units": "Sold (Units)",
  "OnHand Units": "On-Hand (Units)",
  "FOB Price THB": "FOB Price (THB)",
  "Landed Cost THB": "Landed Cost (THB)",
  "FOB Price in Currency": "FOB Price (Foreign)",
  "Purchase Currency": "Currency",
  "Purchase Exchange Rate": "Exchange Rate",
  // Location summary columns
  "Lifetime Master Sale Value": "Lifetime Sales (THB)",
  "Onhand Master Value": "On-Hand Value (THB)",
  // Description columns
  "Dscription": "Description",
  "ItemCode": "Item Code",
  "ItemName": "Item Name",
  "Customer Name": "Customer / Channel",
  "Location": "Location",
};

const METRIC_MAP = {
  "Sold_QTY": "Sold (Qty)",
  "Sold_THB": "Sold (THB)",
  "OnHand_QTY": "On-Hand (Qty)",
  "OnHand_THB": "On-Hand (THB)",
  "Sale_Ratio": "Sale Ratio",
  "Total_Sold_QTY": "Total Sold (Qty)",
  "Total_Sold_THB": "Total Sold (THB)",
  "Total_OnHand_QTY": "Total On-Hand (Qty)",
  "Total_Sale_Ratio": "Total Sale Ratio",
};

function displayMetricSuffix(metric) {
  if (METRIC_MAP[metric]) return METRIC_MAP[metric];
  const locMetric = metric.match(/^(.+?)_(Sold_QTY|Sold_THB|OnHand_QTY|Sale_Ratio)$/);
  if (locMetric) {
    const locName = locMetric[1].replace(/_/g, " ");
    const metricName = METRIC_MAP[locMetric[2]] || locMetric[2];
    return `${locName} ${metricName}`;
  }
  return metric.replace(/_/g, " ");
}

export function displayColumnName(col) {
  if (!col || typeof col !== "string") return col;

  if (STATIC_MAP[col]) return STATIC_MAP[col];

  // Date-prefixed: "2024-01-01_Sold_THB" -> "Jan 2024 Sold (THB)"
  const dateMetric = col.match(/^(\d{4})-(\d{2})-\d{2}_(.+)$/);
  if (dateMetric) {
    const [, year, monthStr, metric] = dateMetric;
    const monthIdx = parseInt(monthStr, 10) - 1;
    const monthName = MONTH_NAMES[monthIdx] || monthStr;
    const metricDisplay = displayMetricSuffix(metric);
    return `${monthName} ${year} ${metricDisplay}`;
  }

  // "Master Sale Value 2024" -> "Sales 2024 (THB)"
  const masterSaleYear = col.match(/^Master Sale Value (\d{4})$/);
  if (masterSaleYear) return `Sales ${masterSaleYear[1]} (THB)`;

  // "Avg Sale Value 2024" -> "Avg Monthly Sales 2024 (THB)"
  const avgSaleYear = col.match(/^Avg Sale Value (\d{4})$/);
  if (avgSaleYear) return `Avg Monthly Sales ${avgSaleYear[1]} (THB)`;

  // "Stock Ratio 2024" -> "Stock Ratio 2024"
  const stockRatio = col.match(/^Stock Ratio (\d{4})$/);
  if (stockRatio) return `Stock Ratio ${stockRatio[1]}`;

  // Per-warehouse/channel columns
  const onhandWhs = col.match(/^OnHand (.+)$/);
  if (onhandWhs) return `On-Hand: ${onhandWhs[1]}`;
  const soldWhs = col.match(/^Sold (.+)$/);
  if (soldWhs) return `Sold: ${soldWhs[1]}`;
  const chOnhand = col.match(/^(.+) OnHand Units$/);
  if (chOnhand) return `${chOnhand[1]} On-Hand (Units)`;
  const chSold = col.match(/^(.+) Sold Units$/);
  if (chSold) return `${chSold[1]} Sold (Units)`;

  // Fallback: replace underscores with spaces
  return col.replace(/_/g, " ");
}

/** Format a short human-readable period from "YYYY-MM-DD" -> "Jan 2024" */
export function formatPeriodLabel(dateStr) {
  const m = dateStr.match(/^(\d{4})-(\d{2})/);
  if (!m) return dateStr;
  const monthIdx = parseInt(m[2], 10) - 1;
  return `${MONTH_NAMES[monthIdx] || m[2]} ${m[1]}`;
}

/** Format number for table cells based on column name */
export function formatCellValue(key, value) {
  if (value === null || value === undefined) return "\u2014";
  if (typeof value !== "number") return String(value);
  if (/_THB$/.test(key) || /THB/.test(key) || /Value/.test(key) || /Cost/.test(key) || /Revenue/.test(key) || /Profit/.test(key)) {
    return "\u0E3F" + value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  if (/_QTY$/.test(key) || /QTY/.test(key) || /Units/.test(key)) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  if (/%$/.test(key) || /Ratio/.test(key) || /pct/.test(key)) {
    return value.toFixed(1) + "%";
  }
  return value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}
