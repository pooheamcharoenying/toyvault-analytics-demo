"use client";

import { useCallback, useEffect, useState } from "react";
import api, { isAbortError } from "@/utils/api";
import ErrorBanner from "@/components/ErrorBanner";
import KpiCard from "@/components/KpiCard";
import { fmtThb, fmtQty } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csvExport";

const SEVERITY_STYLE = {
  high:   { badge: "bg-red-100 text-red-800",     border: "border-red-300" },
  medium: { badge: "bg-amber-100 text-amber-800", border: "border-amber-300" },
  low:    { badge: "bg-blue-100 text-blue-800",   border: "border-blue-200" },
};

function fmtDaysCover(days) {
  if (days === null || days === undefined) return "∞";
  if (days > 999) return ">999d";
  if (days < 1) return "< 1d";
  return `${Math.round(days)}d`;
}

function fmtCompact(n) {
  // 1,234 → "1.2K", 1,234,567 → "1.2M", 87 → "87"
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (abs >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K";
  return Math.round(n).toString();
}

function downloadPlanCsv(plan) {
  if (!plan?.destination_groups?.length) return;
  const headers = [
    "PhysicalLocation", "SAPCodesInGroup",
    "DestWhsName", "DestWhsCode",
    "Item", "ItemName", "Brand", "Qty",
    "From", "FromCode",
    "OnHandAtSource", "SourceDaysCover", "SourceSoldQtyLifetime",
    "OnHandAtDest", "DestDaysCover", "DestVelocityPerDay", "DestSoldQtyLifetime",
    "ShelfCap", "ShelfCapBasis", "MasterPriceTHB",
    "MarginPerUnitTHB", "TransferValueTHB", "ExpectedProfitUpliftTHB",
    "Severity", "Rationale",
  ];
  const rows = [];
  plan.destination_groups.forEach((g) => {
    const sapList = (g.sap_codes || []).join("; ");
    g.transfers.forEach((t) => {
      rows.push([
        g.physical_location || g.destination_whs_name,
        sapList,
        t.to_whs_name || "",
        t.to_whs_code || "",
        t.item_code, t.item_name, t.brand, t.qty,
        t.from_whs_name, t.from_whs_code,
        t.current_qty_at_source, t.source_days_cover ?? "", t.source_sold_qty_lifetime ?? 0,
        t.current_qty_at_destination, t.destination_days_cover ?? "",
        t.destination_velocity_per_day, t.destination_sold_qty_lifetime ?? 0,
        t.shelf_capacity_estimate, t.shelf_capacity_basis,
        t.master_price_thb, t.margin_per_unit_thb,
        t.transfer_value_thb_master, t.expected_profit_uplift_thb,
        t.severity, t.rationale,
      ]);
    });
  });
  const datestamp = (plan.as_of_data_date || "").replace(/-/g, "");
  downloadCsv(`stock_bot_transfer_plan_${datestamp || "latest"}.csv`, headers, rows);
}

function DecisionRulesCard() {
  const [open, setOpen] = useState(true);
  return (
    <section className="rounded-lg border border-blue-200 bg-blue-50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-blue-100 rounded-lg"
      >
        <div className="flex items-center gap-2">
          <span className="text-lg">{open ? "▼" : "▶"}</span>
          <span className="font-semibold text-base text-blue-900">
            How the bot decides
          </span>
          <span className="text-xs text-blue-700 ml-2">
            (the rules behind every recommendation)
          </span>
        </div>
        <span className="text-xs text-blue-700">click to {open ? "collapse" : "expand"}</span>
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-5 text-sm text-gray-800">

          {/* Sources */}
          <div>
            <h3 className="font-semibold text-blue-900 mb-2">
              1 · Where stock comes FROM (sources, ranked priority)
            </h3>
            <ol className="ml-5 list-decimal space-y-1.5">
              <li>
                <strong>Main warehouses first</strong> (D1 + other internal stock pools).
                They exist to be drawn from. If a warehouse has the item, the bot
                ships from there before touching any shop.
              </li>
              <li>
                <strong>Overstocked shops next.</strong> A shop sitting on ≥ 180 days
                of cover (≈ 6 months without selling) is treated as a product-market
                mismatch — moving the stock out frees shelf space for items that
                actually sell at that location.
              </li>
              <li>
                <strong>Healthy shops are never drained.</strong> Any shop turning
                its stock in under 6 months keeps it — full stop.
              </li>
            </ol>
            <p className="text-xs text-gray-600 mt-2 ml-5 italic">
              Internally: source scoring multiplier = 2.0 warehouse · 1.5 shop with
              dead/slow stock · 0.8 healthy shop. Higher = preferred.
            </p>
          </div>

          {/* Destinations */}
          <div>
            <h3 className="font-semibold text-blue-900 mb-2">
              2 · Where stock goes TO (destinations)
            </h3>
            <ul className="ml-5 list-disc space-y-1.5">
              <li>
                <strong>Only locations with a real deficit.</strong> A destination
                qualifies only when its current on-hand is below its shelf cap
                AND below what it would sell in the next 8 weeks. If a shop already
                has enough, no transfer is sent.
              </li>
              <li>
                <strong>Main warehouses are never destinations.</strong> They have
                no customer-facing shelves, so the bot doesn't try to "fill them
                up" — they just ship out.
              </li>
              <li>
                <strong>Flagships are slightly preferred</strong> (×1.5) over standard
                stores (×1.0) over boutiques (×0.6) for the same item-deficit, since
                higher-traffic locations turn each unit faster.
              </li>
              <li>
                <strong>Same physical store = one group.</strong> SAP splits a
                single physical location across many WhsCodes (different
                commission tiers like GP25 vs GP33, separate departments like
                Art Toy, promotional pop-ups). The bot collapses all these
                back to one group per physical store so you can review the
                full plan for that store at one time. The exact SAP destination
                is shown on every transfer row for audit.
              </li>
            </ul>
          </div>

          {/* Shelf capacity */}
          <div>
            <h3 className="font-semibold text-blue-900 mb-2">
              3 · How shelf capacity is decided (the "don't over-stock" rule)
            </h3>
            <p className="ml-5 mb-2">
              Five units of an SKU on a shelf is already a strong display presence;
              ten is very generous; twenty is only justified for a best-seller
              moving 100+/month. The cap per (product × location) is:
            </p>
            <div className="ml-5 overflow-x-auto">
              <table className="text-xs border border-blue-200 bg-white">
                <thead className="bg-blue-100">
                  <tr>
                    <th className="px-2 py-1 text-left">Monthly velocity at this shop</th>
                    <th className="px-2 py-1 text-right">Baseline cap (units)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td className="px-2 py-1">&lt; 30 / mo</td><td className="px-2 py-1 text-right">5</td></tr>
                  <tr className="bg-blue-50"><td className="px-2 py-1">30 – 100 / mo</td><td className="px-2 py-1 text-right">10</td></tr>
                  <tr><td className="px-2 py-1">100 – 500 / mo</td><td className="px-2 py-1 text-right">20</td></tr>
                  <tr className="bg-blue-50"><td className="px-2 py-1">500 – 1,000 / mo</td><td className="px-2 py-1 text-right">50</td></tr>
                  <tr><td className="px-2 py-1">&gt; 1,000 / mo</td><td className="px-2 py-1 text-right">100</td></tr>
                </tbody>
              </table>
            </div>
            <p className="ml-5 mt-2">
              Then multiplied by <strong>item size</strong> (small ×2, normal ×1,
              large ×0.5, oversized ×0.25 — derived from price tier) and{" "}
              <strong>location class</strong> (flagship ×1.5, standard ×1,
              boutique ×0.6). Main warehouses get unbounded cap.
            </p>
            <p className="ml-5 mt-2">
              <strong>Example:</strong> a 0.8 unit/day item at Grandway Riverside →
              baseline 5 (under 30/mo) × flagship 1.5 = cap 7. Even if the main warehouse
              holds 850 of that SKU, the bot only sends 6 — bringing Grandway Riverside
              up to cap. Future restocks happen as the shelf draws down.
            </p>
          </div>

          {/* Safety filters */}
          <div>
            <h3 className="font-semibold text-blue-900 mb-2">
              4 · Hard safety filters (always applied)
            </h3>
            <ul className="ml-5 list-disc space-y-1">
              <li>Never drain a source below 14 days of cover at the source.</li>
              <li>Never move loss-making items (margin per unit ≤ 0).</li>
              <li>Never move discontinued (<code>frozenFor=Y</code>) or invalid items.</li>
              <li>Minimum transfer: 3 units. Minimum profit uplift: 1,000 THB.</li>
              <li>Maximum 20 transfers per destination per plan (readability cap).</li>
            </ul>
          </div>

          {/* Math */}
          <div>
            <h3 className="font-semibold text-blue-900 mb-2">
              5 · Math verification (the MATCH badge above)
            </h3>
            <p className="ml-5">
              Every plan is solved twice — once with a fast greedy algorithm,
              once with a linear programming optimiser. They must agree on total
              expected profit for every SKU. The big <strong>MATCH</strong> badge
              up top is the proof. If it ever flips to <strong>MISMATCH</strong>,
              the rules above have an inconsistency and the bot should be paused
              until investigated.
            </p>
          </div>

          {/* Profit formula */}
          <div>
            <h3 className="font-semibold text-blue-900 mb-2">
              6 · How "expected profit uplift" is calculated
            </h3>
            <p className="ml-5">
              For each transfer:{" "}
              <code className="bg-white px-1 rounded">
                qty × (Master Price − FOB Cost − 33% GP Commission)
              </code>
              . This is the additional gross profit the company captures by moving
              those units from a location that isn't selling them to a location
              that will, over the next 90 days. Source-clearing bonuses and
              destination-quality multipliers tilt the ranking but don't change
              the raw THB figure displayed.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}


function VerdictCard({ report }) {
  if (!report) return null;
  const isMatch = report.verdict === "MATCH";
  const tone = isMatch
    ? "bg-green-50 border-green-300 text-green-900"
    : "bg-red-50 border-red-300 text-red-900";
  return (
    <div className={`rounded-lg border-2 p-4 ${tone}`}>
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-wide opacity-70">
            Math verification — greedy vs LP
          </div>
          <div className="text-2xl font-bold mt-1">
            {isMatch ? "✓ MATCH" : "✗ MISMATCH"}
          </div>
          <div className="text-sm mt-1">
            {report.items_compared} per-item subproblems compared,{" "}
            {report.divergence_count} divergence{report.divergence_count === 1 ? "" : "s"}
            {report.divergence_total_thb > 0
              ? ` (total gap ${fmtThb(report.divergence_total_thb)})`
              : ""}.
          </div>
        </div>
        <div className="text-xs text-right opacity-80">
          <div>Greedy: {report.primary_runtime_ms.toFixed(0)}ms</div>
          <div>LP:&nbsp;&nbsp;&nbsp;&nbsp; {report.secondary_runtime_ms.toFixed(0)}ms</div>
          <div>Tolerance: {report.tolerance_thb} THB</div>
        </div>
      </div>
      {!isMatch && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-medium">
            Show first {Math.min(report.divergences.length, 20)} divergences
          </summary>
          <ul className="mt-2 text-xs font-mono space-y-1">
            {report.divergences.slice(0, 20).map((d) => (
              <li key={d.item_code}>
                {d.item_code} — greedy {d.primary_value.toFixed(0)},{" "}
                LP {d.secondary_value.toFixed(0)}, gap {d.gap_thb > 0 ? "+" : ""}{d.gap_thb.toFixed(0)} THB
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function TransferRow({ t }) {
  const sev = SEVERITY_STYLE[t.severity] || SEVERITY_STYLE.low;
  const [open, setOpen] = useState(false);

  // The item-code link goes to the item AT THE DESTINATION — that's the
  // page where a manager evaluates "does this product belong here?". The
  // FROM and TO labels in the diagnostic panel below are also clickable
  // and route to the item at each respective endpoint.
  const itemAtLocHref = (whsCode) =>
    whsCode
      ? `/dashboards/item-detail/${encodeURIComponent(t.item_code)}/${encodeURIComponent(whsCode)}`
      : `/dashboards/item-detail/${encodeURIComponent(t.item_code)}`;

  return (
    <li className={`border ${sev.border} rounded-md p-3 bg-white`}>
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded font-semibold uppercase ${sev.badge}`}>
          {t.severity}
        </span>
        <span className="font-mono font-semibold text-sm">{t.qty}×</span>
        <a
          href={itemAtLocHref(t.to_whs_code)}
          title={`View ${t.item_code} at ${t.to_whs_name}`}
          className="font-mono text-sm text-blue-700 hover:underline"
        >
          {t.item_code}
        </a>
        <span className="text-sm text-gray-700 truncate max-w-md">{t.item_name}</span>
        <span className="ml-auto text-right">
          <div className="text-sm font-semibold text-green-700">
            +{fmtThb(t.expected_profit_uplift_thb)}
          </div>
          <div className="text-xs text-gray-500">cap {t.shelf_capacity_estimate}</div>
        </span>
      </div>

      {/* Source → Destination summary with on-hand, days of cover, lifetime sold.
          Both location names are clickable links to "this item at this location". */}
      <div className="mt-2 text-xs text-gray-700 grid grid-cols-1 md:grid-cols-2 gap-2 bg-gray-50 rounded p-2">
        <div>
          <span className="text-gray-500 font-semibold">FROM </span>
          <a
            href={itemAtLocHref(t.from_whs_code)}
            title={`View ${t.item_code} at ${t.from_whs_name}`}
            className="text-blue-700 hover:underline"
          >
            {t.from_whs_name}
          </a>
          <div className="text-gray-600 font-mono mt-0.5">
            {fmtQty(t.current_qty_at_source)} on-hand
            <span className="text-gray-400 mx-1.5">·</span>
            {fmtDaysCover(t.source_days_cover)} cover
            <span className="text-gray-400 mx-1.5">·</span>
            <span title={`${fmtQty(t.source_sold_qty_lifetime)} units sold lifetime at this location`}>
              {fmtCompact(t.source_sold_qty_lifetime)} sold lifetime
            </span>
          </div>
        </div>
        <div className="md:border-l md:border-gray-200 md:pl-3">
          <span className="text-gray-500 font-semibold">TO </span>
          <a
            href={itemAtLocHref(t.to_whs_code)}
            title={`View ${t.item_code} at ${t.to_whs_name}`}
            className="text-blue-700 hover:underline"
          >
            {t.to_whs_name}
          </a>
          <div className="text-gray-600 font-mono mt-0.5">
            {fmtQty(t.current_qty_at_destination)} on-hand
            <span className="text-gray-400 mx-1.5">·</span>
            {fmtDaysCover(t.destination_days_cover)} cover
            <span className="text-gray-400 mx-1.5">·</span>
            <span title={`${fmtQty(t.destination_sold_qty_lifetime)} units sold lifetime at this location`}>
              {fmtCompact(t.destination_sold_qty_lifetime)} sold lifetime
            </span>
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-blue-600 hover:underline mt-2"
      >
        {open ? "Hide" : "Why this?"}
      </button>
      {open && (
        <div className="mt-2 text-sm text-gray-700 bg-gray-50 p-3 rounded space-y-1">
          <div>{t.rationale}</div>
          <div className="text-xs text-gray-500 mt-2 font-mono">
            Shelf cap basis: <strong>{t.shelf_capacity_basis}</strong>
            {t.shelf_capacity_modifiers?.length > 0 && (
              <> — modifiers: {t.shelf_capacity_modifiers.join(", ")}</>
            )}
          </div>
          <div className="text-xs text-gray-500 font-mono">
            Source: {t.from_whs_code} · on-hand {fmtQty(t.current_qty_at_source)},
            cover {fmtDaysCover(t.source_days_cover)}
          </div>
          <div className="text-xs text-gray-500 font-mono">
            Destination: on-hand {fmtQty(t.current_qty_at_destination)},
            velocity {t.destination_velocity_per_day.toFixed(2)}/day
            ({t.destination_velocity_basis}),
            cover {fmtDaysCover(t.destination_days_cover)}
          </div>
          <div className="text-xs text-gray-500 font-mono">
            Master price {fmtThb(t.master_price_thb)} · margin/unit {fmtThb(t.margin_per_unit_thb)} ·
            transfer value {fmtThb(t.transfer_value_thb_master)}
          </div>
        </div>
      )}
    </li>
  );
}

function DestinationGroup({ group, defaultOpen }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const s = group.summary;
  return (
    <section className="rounded-lg border border-gray-200 bg-gray-50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 p-4 hover:bg-gray-100 rounded-lg text-left"
      >
        <div className="flex-1 min-w-0 pr-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{open ? "▼" : "▶"}</span>
            <span className="font-semibold text-base truncate">
              To {group.physical_location || group.destination_whs_name}
            </span>
          </div>
          {group.sap_code_count > 1 && (
            <div className="text-xs text-gray-500 ml-7 mt-0.5">
              Consolidated across <strong>{group.sap_code_count}</strong> SAP entries:{" "}
              <span className="font-mono">{group.sap_codes.join(", ")}</span>
            </div>
          )}
          {group.sap_code_count === 1 && (
            <div className="text-xs text-gray-500 ml-7 mt-0.5 font-mono">
              {group.sap_codes[0]}
            </div>
          )}
        </div>
        <div className="text-right text-sm flex-shrink-0">
          <div className="text-gray-700">
            <strong>{s.transfer_count}</strong> transfers · <strong>{fmtQty(s.total_qty)}</strong> units
          </div>
          <div className="mt-0.5">
            <span className="text-gray-700">Revenue </span>
            <span className="font-semibold">{fmtThb(s.total_transfer_value_thb_master)}</span>
            <span className="text-gray-400 mx-1.5">·</span>
            <span className="text-green-700 font-semibold">+{fmtThb(s.expected_profit_uplift_thb)}</span>
            <span className="text-gray-500 text-xs"> profit</span>
          </div>
        </div>
      </button>
      {open && (
        <ul className="space-y-2 px-4 pb-4">
          {group.transfers.map((t, idx) => (
            <TransferRow key={`${t.item_code}-${t.from_whs_code}-${idx}`} t={t} />
          ))}
        </ul>
      )}
    </section>
  );
}

export default function StockBotPage() {
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (signal) => {
    try {
      setLoading(true);
      setError(null);
      // The bot computes the full plan on first hit; give it headroom beyond
      // the shared api default (30s) so a cold start isn't cut off client-side.
      const res = await api.get("/api/stock_bot/transfer_plan", { signal, timeout: 90_000 });
      setPlan(res.data);
    } catch (e) {
      if (isAbortError(e)) return;
      setError(e?.response?.data?.details || e?.message || "Failed to load plan");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const c = new AbortController();
    load(c.signal);
    return () => c.abort();
  }, [load]);

  const summary = plan?.summary;
  const report = plan?.comparison_report;
  const groups = plan?.destination_groups || [];

  return (
    <main className="p-6 space-y-6 max-w-7xl mx-auto">
      <header>
        <h1 className="text-2xl font-bold">Stock Allocation Bot</h1>
        <p className="text-sm text-gray-600 mt-1">
          Profit-aware, shelf-cap-aware transfer recommendations grouped by destination.
          Five units of an SKU is already a strong display presence; the bot only sends
          stock where it has shelf room AND velocity to absorb it.
          {plan?.as_of_data_date && (
            <span className="ml-2 text-gray-500">
              · Data as of <strong>{plan.as_of_data_date}</strong>
            </span>
          )}
        </p>
      </header>

      {error && <ErrorBanner message={error} onRetry={() => load()} />}

      {loading && !plan && (
        <div className="text-center py-12 text-gray-500">
          Computing transfer plan… (this can take 5–15 seconds the first time)
        </div>
      )}

      {plan && (
        <>
          {/* Bottom-line revenue & profit impact, prominently */}
          <section className="rounded-lg bg-gradient-to-r from-[var(--nichi-blue)] to-[var(--nichi-blue-light)] text-white p-5 md:p-6 shadow">
            <div className="text-xs uppercase tracking-wider opacity-80">
              If all recommended transfers are executed
            </div>
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <div className="text-sm opacity-80">Revenue impact (THB @ Master Price)</div>
                <div className="text-4xl font-bold mt-1">
                  {fmtThb(summary?.total_transfer_value_thb_master)}
                </div>
                <div className="text-xs opacity-80 mt-1">
                  Gross sales value of the {fmtQty(summary?.total_qty)} units being
                  relocated, if they sell at master price at their new destinations
                </div>
              </div>
              <div className="md:border-l md:border-white/30 md:pl-5">
                <div className="text-sm opacity-80">
                  Expected gross profit (THB, 90-day horizon)
                </div>
                <div className="text-4xl font-bold mt-1 text-[var(--nichi-yellow)]">
                  {fmtThb(summary?.total_expected_profit_uplift_thb)}
                </div>
                <div className="text-xs opacity-80 mt-1">
                  After FOB cost and 33% GP commission ·
                  {summary?.total_transfer_value_thb_master > 0 && (
                    <> margin {((summary.total_expected_profit_uplift_thb / summary.total_transfer_value_thb_master) * 100).toFixed(1)}%</>
                  )}
                </div>
              </div>
            </div>
          </section>

          <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <KpiCard title="Transfers" value={fmtQty(summary?.total_proposals)} />
            <KpiCard title="Total units" value={fmtQty(summary?.total_qty)} />
            <KpiCard
              title="Revenue impact"
              value={fmtThb(summary?.total_transfer_value_thb_master)}
              sub="THB @ Master Price"
            />
            <KpiCard
              title="Expected gross profit"
              value={fmtThb(summary?.total_expected_profit_uplift_thb)}
              sub="THB · 90-day horizon"
            />
            <KpiCard
              title="Destinations reached"
              value={fmtQty(summary?.destinations_covered)}
            />
          </section>

          <VerdictCard report={report} />

          <DecisionRulesCard />

          <div className="flex items-center justify-between flex-wrap gap-3">
            <h2 className="text-lg font-semibold">Transfer Plan by Destination</h2>
            <div className="flex gap-2">
              <button
                onClick={() => downloadPlanCsv(plan)}
                disabled={!groups.length}
                className="text-sm px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
              >
                ↓ CSV
              </button>
              <button
                onClick={() => load()}
                className="text-sm px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50"
              >
                ↻ Refresh
              </button>
            </div>
          </div>

          {groups.length === 0 ? (
            <p className="text-center py-8 text-gray-500">
              No transfers recommended on the current data snapshot.
            </p>
          ) : (
            <div className="space-y-3">
              {groups.map((g, idx) => (
                <DestinationGroup
                  key={g.destination_whs_code}
                  group={g}
                  defaultOpen={idx < 3}
                />
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
