"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import api, { isAbortError } from "@/utils/api";
import ErrorBanner from "@/components/ErrorBanner";
import { fmtThbShort } from "@/utils/formatters";

const SECTIONS = [
  {
    title: "Core",
    cards: [
      {
        href: "/dashboards/ai-assist",
        label: "AI Assist",
        desc: "Ask anything about the business — grounded in your live data",
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-4 4v-4z" />
          </svg>
        ),
        color: "from-[var(--nichi-blue)] to-blue-600",
      },
      {
        href: "/dashboards/actions",
        label: "Priority Actions",
        desc: "Top urgent actions ranked by severity and impact",
        statKey: "actions",
        statFn: (d) => d ? `${d.critical} Critical, ${d.warning} Warning` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
          </svg>
        ),
        color: "from-red-600 to-amber-500",
      },
      {
        href: "/dashboards/executive",
        label: "Executive Dashboard",
        desc: "KPIs, trends, margins, and concentration",
        statKey: "executive",
        statFn: (d) => d?.latest_revenue_thb ? `Revenue ${fmtThbShort(d.latest_revenue_thb)}` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
          </svg>
        ),
        color: "from-[var(--nichi-blue)] to-[var(--nichi-blue-light)]",
      },
      {
        href: "/task2",
        label: "Operations",
        desc: "Sales data by brand, channel, and product",
        statKey: "products",
        statFn: (d) => d ? `${d.brands} brands, ${d.items.toLocaleString()} items` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941" />
          </svg>
        ),
        color: "from-emerald-600 to-emerald-500",
      },
      {
        href: "/dashboards/period-comparison",
        label: "Period Comparison",
        desc: "Year-over-year and quarter-over-quarter analysis",
        statKey: "period",
        statFn: (d) => d?.yoy_pct != null ? `YoY revenue: ${d.yoy_pct >= 0 ? "+" : ""}${d.yoy_pct}%` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
          </svg>
        ),
        color: "from-violet-600 to-violet-500",
      },
    ],
  },
  {
    title: "Inventory & Stock",
    cards: [
      {
        href: "/dashboards/inventory-alerts",
        label: "Inventory Alerts",
        desc: "Stockout risk, dead stock, and reorder points",
        statKey: "stockout",
        statFn: (d) => d ? `${d.total_at_risk} items at risk` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        ),
        color: "from-red-600 to-red-500",
      },
      {
        href: "/dashboards/stock-allocation",
        label: "Stock Allocation",
        desc: "Transfer recommendations and rebalancing",
        statKey: "allocation",
        statFn: (d) => d ? `${d.transfer_recs} transfer recs` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7.5 7.5h-.75A2.25 2.25 0 004.5 9.75v7.5a2.25 2.25 0 002.25 2.25h7.5a2.25 2.25 0 002.25-2.25v-7.5a2.25 2.25 0 00-2.25-2.25h-.75m-6 3.75l3 3m0 0l3-3m-3 3V1.5m6 9h.75a2.25 2.25 0 012.25 2.25v7.5a2.25 2.25 0 01-2.25 2.25h-7.5a2.25 2.25 0 01-2.25-2.25v-.75" />
          </svg>
        ),
        color: "from-orange-600 to-orange-500",
      },
      {
        href: "/dashboards/stock-bot",
        label: "Stock Bot 🤖",
        desc: "Profit-aware transfers with shelf-cap awareness",
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
          </svg>
        ),
        color: "from-purple-600 to-indigo-500",
      },
      {
        href: "/dashboards/purchase-analytics",
        label: "Purchase Analytics",
        desc: "FOB costs, vendor analysis, working capital",
        statKey: "dead_stock",
        statFn: (d) => d?.total_thb ? `Dead stock ${fmtThbShort(d.total_thb)}` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" />
          </svg>
        ),
        color: "from-teal-600 to-teal-500",
      },
    ],
  },
  {
    title: "Products & Locations",
    cards: [
      {
        href: "/dashboards/brands",
        label: "Brands & Products",
        desc: "Brand P&L, ABCDE classification, channel fit, drill down to items",
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
          </svg>
        ),
        color: "from-[var(--nichi-blue)] to-blue-600",
      },
      {
        href: "/dashboards/locations",
        label: "Locations & Stores",
        desc: "Store performance, investment analysis, sales trends, product mix",
        statKey: "locations",
        statFn: (d) => d ? `${d.count} locations tracked` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008z" />
          </svg>
        ),
        color: "from-teal-600 to-teal-500",
      },
      {
        href: "/dashboards/planogram",
        label: "Planogram",
        desc: "Set minimum shelf quantities per SKU per location",
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 13.875c0 .621.504 1.125 1.125 1.125m0 0h7.5m-7.5 0a1.125 1.125 0 01-1.125-1.125m0 0V5.625m0 0A1.125 1.125 0 014.5 4.5h15A1.125 1.125 0 0120.625 5.625m0 0v13.875m0 0a1.125 1.125 0 01-1.125 1.125m0 0h-7.5m7.5 0c.621 0 1.125-.504 1.125-1.125M12 4.5v15" />
          </svg>
        ),
        color: "from-indigo-600 to-indigo-500",
      },
    ],
  },
  {
    title: "Analysis & Tools",
    cards: [
      {
        href: "/dashboards/seasonality-margin",
        label: "Seasonality & Margin",
        desc: "Seasonal patterns and margin waterfall",
        statKey: "margin",
        statFn: (d) => d?.blended_margin_pct != null ? `Blended margin: ${d.blended_margin_pct}%` : null,
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
          </svg>
        ),
        color: "from-pink-600 to-pink-500",
      },
      {
        href: "/task1",
        label: "Barcode Lookup",
        desc: "Match barcodes to item codes",
        icon: (
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 013.75 9.375v-4.5zM3.75 14.625c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5a1.125 1.125 0 01-1.125-1.125v-4.5zM13.5 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 0113.5 9.375v-4.5z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.5 14.625v2.625m0 3v.375m0-3.375h2.625m3.375 0h.375m-3.375 0v2.625m0 .75h3.375" />
          </svg>
        ),
        color: "from-slate-600 to-slate-500",
      },
    ],
  },
];

export default function Home() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = useCallback((signal) => {
    setLoading(true);
    setError(null);
    api
      .get("/api/home_summary", { signal })
      .then((r) => {
        if (r.data && !r.data.message) setSummary(r.data);
      })
      .catch((e) => {
        if (!isAbortError(e)) setError(e.message || "Failed to load summary data");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  return (
    <div className="min-h-[calc(100vh-7rem)] bg-[var(--nichi-gray-50)] p-6 sm:p-10">
      <div className="max-w-5xl mx-auto">
        {/* Hero section */}
        <div className="text-center mb-10">
          <h1 className="text-3xl sm:text-4xl font-bold text-[var(--nichi-gray-800)]">
            ToyVault Analytics
          </h1>
          <p className="mt-2 text-[var(--nichi-gray-600)] text-sm sm:text-base">
            Business intelligence dashboard for ToyVault operations
          </p>
          {summary?.as_of && (
            <p className="mt-1 text-xs text-gray-400">
              Data as of: <span className="font-semibold text-gray-600">{summary.as_of}</span>
            </p>
          )}
        </div>

        {/* Error banner */}
        {error && <ErrorBanner message={error} onRetry={() => loadData()} className="mb-6" />}

        {/* Sectioned card grid */}
        <div className="space-y-8">
          {SECTIONS.map(({ title, cards }) => (
            <div key={title}>
              <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 px-1">{title}</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {cards.map(({ href, label, desc, icon, color, statKey, statFn }) => {
                  const stat = summary && statKey && statFn ? statFn(summary[statKey]) : null;
                  const showPulse = loading && statKey;
                  return (
                    <Link
                      key={href}
                      href={href}
                      className="group relative rounded-xl overflow-hidden shadow-md hover:shadow-xl transition-all duration-200 hover:-translate-y-0.5"
                    >
                      <div className={`bg-gradient-to-br ${color} p-5 text-white min-h-[120px] flex flex-col justify-between`}>
                        <div className="opacity-80 group-hover:opacity-100 transition">{icon}</div>
                        <div>
                          <h3 className="text-base font-semibold mt-2">{label}</h3>
                          <p className="text-white/70 text-xs mt-0.5">{desc}</p>
                          {stat && (
                            <p className="text-white/90 text-xs font-semibold mt-1.5 bg-white/15 rounded-full px-2.5 py-0.5 inline-block">
                              {stat}
                            </p>
                          )}
                          {showPulse && !stat && (
                            <div className="mt-1.5 h-5 w-28 bg-white/20 rounded-full animate-pulse" />
                          )}
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
