"use client";

import { useState, useRef, useEffect, useId } from "react";

/**
 * InfoTooltip — a small ⓘ icon that shows an explanatory tooltip on hover/click.
 * Used across all dashboards to explain technical metrics to non-technical managers.
 *
 * Usage:
 *   <InfoTooltip text="Days of Cover = on-hand qty ÷ avg daily sales. Lower means leaner inventory." />
 *
 * Props:
 *   text  — The tooltip explanation string (required)
 *   size  — Icon size: "sm" (12px, for table headers) or "md" (14px, for KPI cards) — default "sm"
 */
export default function InfoTooltip({ text, size = "sm" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const tooltipRef = useRef(null);
  const tooltipId = useId();

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Reposition tooltip to stay within viewport
  useEffect(() => {
    if (!open || !tooltipRef.current) return;
    const el = tooltipRef.current;
    const rect = el.getBoundingClientRect();
    // If tooltip goes off right edge, shift left
    if (rect.right > window.innerWidth - 8) {
      el.style.left = "auto";
      el.style.right = "0";
    }
    // If tooltip goes off left edge, shift right
    if (rect.left < 8) {
      el.style.left = "0";
      el.style.right = "auto";
    }
  }, [open]);

  const iconSize = size === "md" ? 14 : 12;

  return (
    <span
      ref={ref}
      className="relative inline-flex items-center ml-1"
      style={{ verticalAlign: "middle" }}
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(!open);
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="inline-flex items-center justify-center rounded-full text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition-colors focus:outline-none"
        style={{
          width: iconSize + 4,
          height: iconSize + 4,
          fontSize: iconSize,
          lineHeight: 1,
        }}
        aria-label="More info"
        aria-describedby={open ? tooltipId : undefined}
      >
        <svg
          width={iconSize}
          height={iconSize}
          viewBox="0 0 16 16"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
          <text
            x="8"
            y="12"
            textAnchor="middle"
            fill="currentColor"
            fontSize="10"
            fontWeight="600"
            fontFamily="serif"
          >
            i
          </text>
        </svg>
      </button>
      {open && (
        <span
          ref={tooltipRef}
          id={tooltipId}
          role="tooltip"
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 max-w-[90vw] px-3 py-2 rounded-lg bg-slate-800 text-white text-xs leading-relaxed shadow-lg pointer-events-none"
          style={{ fontWeight: 400 }}
        >
          {text}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800" />
        </span>
      )}
    </span>
  );
}

/**
 * METRIC_TOOLTIPS — Central registry of all metric explanations.
 * Organized by dashboard/context. Import and use with InfoTooltip.
 *
 * Usage:
 *   import { METRIC_TOOLTIPS } from "@/components/InfoTooltip";
 *   <InfoTooltip text={METRIC_TOOLTIPS.executive.ttm_revenue} />
 */
export const METRIC_TOOLTIPS = {
  // === Executive Dashboard ===
  executive: {
    lifetime_sold_thb:
      "Total revenue from all sales ever recorded in the system, in Thai Baht.",
    lifetime_sold_qty:
      "Total number of units sold across all products, all time.",
    onhand_thb:
      "Total value of current inventory across all warehouses, calculated as on-hand quantity × list price (THB).",
    onhand_qty:
      "Total number of units currently in stock across all warehouses.",
    ttm_revenue:
      "Trailing Twelve Months Revenue — total revenue for the most recent 12-month period. Smooths out seasonality to show the true growth trend.",
    mom_pct:
      "Month-over-Month % change — how much revenue changed compared to the previous month. Positive = growth, negative = decline.",
    yoy_pct:
      "Year-over-Year % change — revenue this month compared to the same month last year. Removes seasonal effects from the comparison.",
    revenue_thb:
      "Total sales revenue in Thai Baht for the selected period.",
    cogs_thb:
      "Cost of Goods Sold — the total FOB (landed) cost of products sold, calculated from GRPO purchase records. Revenue minus COGS = Gross Margin.",
    gross_margin_pct:
      "Gross Margin % = (Revenue - COGS) ÷ Revenue × 100. Shows what percentage of revenue is profit after product costs. Higher is better. Below 20% is a warning sign for a distributor.",
    hhi:
      "Herfindahl-Hirschman Index — measures revenue concentration. Ranges from 0 (perfectly diversified) to 10,000 (single brand/channel). Below 1,500 = diversified, 1,500-2,500 = moderate concentration, above 2,500 = high concentration risk.",
    top_n_share:
      "Percentage of total revenue from the top brands/channels. High concentration means the business is vulnerable if a key brand or channel is lost.",
  },

  // === Inventory Alerts ===
  inventory: {
    days_of_cover:
      "Days of Cover = on-hand qty ÷ average daily sales. Estimates how many days current stock will last at the current sales rate. Below 14 days = stockout risk. Above 180 days = slow-moving.",
    sell_through_rate:
      "Sell-Through Rate = sold qty ÷ (sold qty + on-hand qty) × 100. Shows what percentage of available stock has been sold. Higher = faster selling. Below 10% = very slow.",
    avg_per_day:
      "Average units sold per day, calculated over the analysis window (e.g., last 90 days). Used to estimate stockout dates and reorder quantities.",
    avg_per_week:
      "Average units sold per week, calculated over the analysis window. Easier to interpret than daily rates for slower-moving items.",
    projected_stockout:
      "Estimated date when this item will run out of stock at the current sales rate. Calculated as today + (on-hand qty ÷ avg daily sales) days.",
    suggested_reorder_qty:
      "Recommended quantity to order, based on: (target weeks of cover × weekly sales rate) - current on-hand. Ensures enough stock to last until the next delivery.",
    severity:
      "Risk severity level. Critical = stockout within 7 days. Warning = stockout within 14 days. Watch = stockout within 30 days.",
    dead_stock_value:
      "Total THB value of items with zero sales in the analysis period but positive on-hand quantity. This capital is effectively frozen.",
    months_no_sale:
      "Number of months since this item last had any sales. Longer = higher risk of being permanently unsellable.",
    reorder_point:
      "The on-hand quantity level at which a reorder should be placed. Calculated based on sales velocity and desired safety stock buffer.",
  },

  // === Stock Allocation ===
  allocation: {
    days_cover:
      "Days of Cover at this specific location = on-hand qty at location ÷ average daily sales at location. Shows how long stock will last at each place.",
    priority_score:
      "Priority Score combines severity (how urgent) × THB impact (how much money is at stake). Higher score = act on this first.",
    surplus_deficit:
      "Positive = surplus (more stock than needed at current sales rate). Negative = deficit (not enough stock). Units relative to optimal level.",
    rebalanceable:
      "Whether this item can be rebalanced by transferring stock between locations. Items that only exist in one location cannot be rebalanced.",
    transfer_from:
      "Location with excess stock (high days of cover, low sales rate) — stock should move FROM here.",
    transfer_to:
      "Location with insufficient stock (low days of cover, high sales rate) — stock should move TO here.",
    transfer_qty:
      "Recommended number of units to transfer. Calculated to equalize days-of-cover across locations without over-correcting.",
  },

  // === Location Analytics ===
  location: {
    health_score:
      "Composite Health Score (0-100) combining: Revenue per THB Inventory (40%), Stock Turnover (25%), Sales Growth (20%), Dead Stock % inverse (15%). Higher = healthier location.",
    revenue_per_thb_inv:
      "Revenue per THB of Inventory = total sales ÷ on-hand value. Measures how efficiently a location converts its stock into revenue. A location with 2.0 generates ฿2 of revenue for every ฿1 of stock held. Higher is better.",
    stock_turnover:
      "Stock Turnover = annual revenue ÷ average inventory value. How many times inventory 'cycles through' per year. Higher = faster-moving, healthier inventory. Below 1.0 = stock sits for over a year on average.",
    dead_stock_pct:
      "Dead Stock % = value of items with zero sales (in analysis period) ÷ total on-hand value × 100. Lower is better. Above 30% means a third of the location's stock isn't selling.",
    efficiency_trend:
      "How Revenue per THB of Inventory has changed over time. Upward trend = location is becoming more efficient. Downward = stock is growing faster than sales.",
    product_location_fit:
      "Shows how well each product matches each location. High sales + low stock = needs more. Low sales + high stock = wrong placement, consider transferring.",
    sell_through:
      "Sell-Through Rate at this location = sold qty ÷ on-hand qty. Shows what fraction of stock actually sells here. Compare across locations to find misallocated inventory.",
  },

  // === Product Analytics ===
  product: {
    abc_class:
      "ABC Classification ranks products by revenue contribution. A-class = top 80% of revenue (your critical few products). B-class = next 15%. C-class = bottom 5%. Focus management attention on A-class items.",
    cumulative_pct:
      "Cumulative % of total revenue — shows how much of total revenue this product and all higher-ranked products account for. When this reaches 80%, you've identified your A-class items.",
    product_channel_fit:
      "Shows which products sell well in which channels. Helps allocate the right products to the right sales channels. A product strong in Pinnacle but weak Online needs different handling in each channel.",
  },

  // === Purchase Analytics ===
  purchase: {
    ps_ratio:
      "Purchase-to-Sales Ratio = purchased qty ÷ sold qty. Above 1.0 = buying more than selling (stock building up). Below 1.0 = selling more than buying (stock depleting). Ideal is close to 1.0 for stable inventory.",
    fob_cost:
      "FOB (Free On Board) Cost — the landed cost of goods in THB, calculated as foreign currency price × exchange rate from GRPO records. This is the true cost of purchasing.",
    turnover_rate:
      "Inventory Turnover Rate = cost of goods sold ÷ average inventory value. How fast inventory converts to sales. Higher = more efficient use of capital.",
    stock_to_sales:
      "Stock-to-Sales Ratio = current inventory value ÷ monthly revenue. Shows how many months of sales are sitting as stock. Lower = leaner. Above 6 = significant capital tied up.",
    working_capital:
      "Working Capital in Inventory = total on-hand value (THB). Represents cash that is tied up in unsold stock. Track the trend — rising working capital without rising sales is a warning sign.",
  },

  // === Seasonality & Margin ===
  seasonality: {
    seasonal_index:
      "Seasonal Index compares each month's average sales to the overall monthly average. Index of 1.2 = that month typically has 20% more sales than average. Below 0.8 = weak month.",
    seasonality_strength:
      "Measures how strongly seasonal a product or brand is. Higher values = more pronounced peaks and valleys. Low values = steady sales year-round.",
    margin_contribution:
      "How much each brand contributes to the company's overall gross margin in THB. A brand with high revenue but low margin contributes less than a brand with moderate revenue but high margin.",
    blended_margin:
      "Overall company gross margin % — the weighted average of all brands' margins. Shifts in product mix (selling more of low-margin brands) will pull this down even if individual brand margins stay flat.",
  },

  // === Period Comparison ===
  period: {
    gross_margin_pct:
      "Gross Margin % for the selected period = (Revenue - FOB Cost) ÷ Revenue × 100. Compare across periods to see if profitability is improving or declining.",
    change_pct:
      "Percentage change between the two selected periods. Green/positive = improvement, red/negative = decline. Helps spot significant shifts quickly.",
    period_revenue:
      "Total sales revenue for the selected time period in THB.",
  },

  // === Actions Dashboard ===
  actions: {
    priority_score:
      "Priority Score = severity level × estimated THB impact. Actions with the highest scores need attention first. Critical items with high financial impact appear at the top.",
    impact_thb:
      "Estimated financial impact in THB — how much money is at risk or could be saved by acting on this recommendation.",
    severity:
      "Urgency level. Critical = needs action within days (stockout imminent, major capital at risk). Warning = needs action within weeks. Info = worth monitoring.",
    action_type:
      "Type of action needed: Reorder (buy more stock), Transfer (move stock between locations), Markdown (reduce price on slow items), Investigate (look into anomalies).",
  },

  // === Store Scorecard ===
  stores: {
    sold_qty:
      "Total units sold at this location during the selected period.",
    sold_thb:
      "Total sales revenue in THB at this location during the selected period.",
    onhand_qty:
      "Current number of units in stock at this location.",
    onhand_thb:
      "Current inventory value at this location = on-hand qty × list price (THB).",
    sale_ratio:
      "Sale Ratio = sold qty ÷ on-hand qty. Shows how many times the current stock level has been 'sold through'. Higher = faster selling location.",
  },

  // === Item Detail ===
  item: {
    lifetime_sold:
      "Total units of this item ever sold across all locations and time periods.",
    total_onhand:
      "Total units of this item currently in stock across all warehouses.",
    onhand_vs_sold:
      "Compares on-hand quantity (blue) vs. lifetime sold quantity (yellow) per location. Locations with high on-hand but low sold = stock sitting idle. Locations with high sold but low on-hand = strong seller, may need restocking.",
  },
};
