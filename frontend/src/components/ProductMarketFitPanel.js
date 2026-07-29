"use client";

import { useState } from "react";
import { fmtQty, fmtThb } from "@/utils/formatters";

/**
 * Render the per-location product-market fit (lift) panel.
 *
 * Expects the API response shape documented in
 * PRODUCT_MARKET_FIT_BLUEPRINT.md §3.
 *
 * Props:
 *   data    — API response (or null while loading)
 *   loading — bool
 *   error   — string / null
 */
export default function ProductMarketFitPanel({ data, loading, error }) {
  const [showDiag, setShowDiag] = useState(false);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow border p-6 my-6 text-gray-500">
        Computing product-market fit…
      </div>
    );
  }
  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 my-6 text-sm text-red-800">
        Couldn't load product-market fit: {String(error)}
      </div>
    );
  }
  if (!data) return null;

  const brandStrong = data.brand_fit?.strong || [];
  const brandWeak = data.brand_fit?.weak || [];
  const lineStrong = data.line_fit?.strong || [];
  const lineWeak = data.line_fit?.weak || [];
  const bands = data.price_band_fit || [];

  const totalsLine = data.totals
    ? `${fmtThb(data.totals.this_location_revenue_thb)} revenue · ${fmtQty(data.totals.this_location_units_sold)} units · ${fmtQty(data.totals.this_location_distinct_skus)} SKUs`
    : "";

  return (
    <section className="bg-white rounded-lg shadow border my-6">
      <header className="px-5 py-4 border-b bg-gradient-to-r from-[var(--nichi-blue)] to-[var(--nichi-blue-light)] text-white rounded-t-lg">
        <h2 className="text-lg font-semibold">
          Product-Market Fit at {data.location}
        </h2>
        <p className="text-xs opacity-90 mt-1">
          {data.period?.year_list?.length
            ? `Years: ${data.period.year_list.join(", ")}`
            : "All available history"}
          {" · "}
          Baseline: company average
          {data.period?.as_of && <> · As of {data.period.as_of}</>}
          {totalsLine && <> · {totalsLine}</>}
        </p>
      </header>

      <div className="p-5 space-y-6">
        {/* Brand fit */}
        <FitSection
          title="Brand Fit"
          subtitle="How each brand's revenue share at this location compares to its share company-wide."
          strong={brandStrong}
          weak={brandWeak}
          rowRender={(b) => (
            <BrandRow
              key={`${b.brand}-${b.lift}`}
              row={b}
              linesForBrand={[...lineStrong, ...lineWeak].filter(
                (l) => l.brand === b.brand
              )}
            />
          )}
          emptyMessage="Not enough data to identify brand fit (need at least 20 units and 3 SKUs per brand at this location)."
        />

        {/* Line fit */}
        <FitSection
          title="Product Line Fit (within brand)"
          subtitle="From SAP Cate field — granular sub-line performance within each brand."
          strong={lineStrong}
          weak={lineWeak}
          rowRender={(l) => <LineRow key={`${l.brand}-${l.line}`} row={l} />}
          emptyMessage="Not enough data to identify line fit (need at least 10 units and 2 SKUs per line)."
        />

        {/* Price band fit */}
        <div>
          <SectionHeader
            title="Price-Point Fit"
            subtitle="Which price tiers over- and under-perform at this location."
          />
          {bands.length === 0 ? (
            <p className="text-sm text-gray-500 italic">Insufficient data.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
              {bands.map((b) => (
                <PriceBandRow key={b.band_key} row={b} />
              ))}
            </div>
          )}
        </div>

        {/* Summary */}
        {data.summary && (
          <div className="bg-blue-50 border-l-4 border-blue-400 p-4 text-sm text-gray-800">
            <span className="font-semibold mr-1">📝 SUMMARY:</span>
            {data.summary}
          </div>
        )}

        {/* Diagnostics */}
        {data.diagnostics && Object.keys(data.diagnostics).length > 0 && (
          <details
            open={showDiag}
            onToggle={(e) => setShowDiag(e.target.open)}
            className="text-xs text-gray-500"
          >
            <summary className="cursor-pointer hover:text-gray-700">
              {showDiag ? "▾" : "▸"} Diagnostics (filter cutoffs + counts)
            </summary>
            <pre className="mt-2 bg-gray-50 p-3 rounded overflow-x-auto">
              {JSON.stringify(data.diagnostics, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </section>
  );
}

/* ───────────────────────── Sub-components ───────────────────────── */

function SectionHeader({ title, subtitle }) {
  return (
    <div className="mb-2">
      <h3 className="text-base font-semibold text-gray-800">{title}</h3>
      {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
    </div>
  );
}

function FitSection({ title, subtitle, strong, weak, rowRender, emptyMessage }) {
  const isEmpty = strong.length === 0 && weak.length === 0;
  return (
    <div>
      <SectionHeader title={title} subtitle={subtitle} />
      {isEmpty ? (
        <p className="text-sm text-gray-500 italic">{emptyMessage}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
          <div>
            <div className="text-xs font-semibold text-green-700 mb-1">
              ✓ STRONG FIT (overperforms)
            </div>
            {strong.length === 0 ? (
              <p className="text-sm text-gray-400 italic">None.</p>
            ) : (
              <ul className="space-y-1.5">{strong.map(rowRender)}</ul>
            )}
          </div>
          <div>
            <div className="text-xs font-semibold text-red-700 mb-1">
              ✗ WEAK FIT (underperforms)
            </div>
            {weak.length === 0 ? (
              <p className="text-sm text-gray-400 italic">None.</p>
            ) : (
              <ul className="space-y-1.5">{weak.map(rowRender)}</ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function liftBadgeColor(lift) {
  if (lift === null || lift === undefined) return "bg-gray-100 text-gray-500";
  if (lift >= 1.5) return "bg-green-100 text-green-800 border-green-200";
  if (lift >= 1.0) return "bg-blue-50 text-blue-700 border-blue-200";
  if (lift >= 0.5) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-red-100 text-red-800 border-red-200";
}

function LiftBadge({ lift }) {
  const color = liftBadgeColor(lift);
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-mono font-semibold border ${color}`}
      title="Lift = (share at this location) ÷ (share company-wide). >1 over-indexes; <1 under-indexes."
    >
      {lift != null ? `${Number(lift).toFixed(2)}×` : "—"}
    </span>
  );
}

function BrandRow({ row, linesForBrand }) {
  const [open, setOpen] = useState(false);
  const hasLines = linesForBrand && linesForBrand.length > 0;
  return (
    <li className="text-sm">
      <button
        type="button"
        onClick={() => hasLines && setOpen((v) => !v)}
        className="w-full flex items-center gap-2 hover:bg-gray-50 rounded px-2 py-1 text-left"
      >
        {hasLines && (
          <span className="text-xs text-gray-500">{open ? "▾" : "▸"}</span>
        )}
        {!hasLines && <span className="w-3" />}
        <LiftBadge lift={row.lift} />
        <span className="font-medium text-gray-900 flex-1 truncate">
          {row.brand}
        </span>
        <span className="text-xs text-gray-500 font-mono">
          {fmtThb(row.revenue_thb)} · {fmtQty(row.units)} u
        </span>
      </button>
      <div className="text-[11px] text-gray-500 ml-7">
        share {Number(row.share_loc_pct).toFixed(1)}% here vs{" "}
        {Number(row.share_company_pct).toFixed(1)}% company-wide
      </div>
      {open && hasLines && (
        <ul className="ml-7 mt-1 mb-2 space-y-0.5 border-l-2 border-gray-200 pl-3">
          {linesForBrand.map((l) => (
            <li key={`${l.brand}-${l.line}`} className="flex items-center gap-2 text-xs">
              <LiftBadge lift={l.lift} />
              <span className="text-gray-700 flex-1 truncate">{l.line}</span>
              <span className="text-gray-500 font-mono">
                {fmtThb(l.revenue_thb)} · {fmtQty(l.units)} u
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function LineRow({ row }) {
  return (
    <li className="text-sm flex items-center gap-2 px-2 py-1">
      <LiftBadge lift={row.lift} />
      <span className="text-gray-700 flex-1 truncate">
        <span className="text-gray-500">{row.brand} / </span>
        {row.line}
      </span>
      <span className="text-xs text-gray-500 font-mono">
        {fmtThb(row.revenue_thb)} · {fmtQty(row.units)} u
      </span>
    </li>
  );
}

function PriceBandRow({ row }) {
  return (
    <div className="flex items-center gap-3 border rounded px-3 py-2">
      <LiftBadge lift={row.lift} />
      <div className="flex-1">
        <div className="text-sm font-medium text-gray-800">{row.band_label}</div>
        <div className="text-[11px] text-gray-500 font-mono">
          share {Number(row.share_loc_pct).toFixed(1)}% here vs{" "}
          {Number(row.share_company_pct).toFixed(1)}% company-wide
        </div>
      </div>
      <div className="text-xs text-gray-500 font-mono text-right">
        {fmtThb(row.revenue_thb)}
        <div className="text-[11px]">{fmtQty(row.units)} units</div>
      </div>
    </div>
  );
}
