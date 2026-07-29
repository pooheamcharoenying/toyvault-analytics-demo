"use client";

import { downloadCsvFromObjects } from "@/utils/csvExport";
import { downloadChartAsPng } from "@/utils/chartImage";

/**
 * Two-button download toolbar for chart cards.
 *
 *   <div ref={chartRef}>
 *     <ResponsiveContainer ...><LineChart>...</LineChart></ResponsiveContainer>
 *   </div>
 *
 *   <ChartDownloadToolbar
 *     data={chartData}                  // array of objects, e.g. [{period, "Revenue (Actual)": 123, ...}]
 *     filenameBase="monthly-revenue-2026"  // .csv / .png appended automatically
 *     chartRef={chartRef}
 *     csvColumns={["period", "Revenue (Actual)", "Revenue (Master)"]}  // optional column order
 *   />
 *
 * If ``data`` is not provided the CSV button is hidden.
 * If ``chartRef`` is not provided the PNG button is hidden.
 */
export default function ChartDownloadToolbar({
  data,
  filenameBase = "chart",
  chartRef,
  csvColumns,
  className = "",
}) {
  const safeName = (filenameBase || "chart").replace(/[\\/:*?"<>|]+/g, "_");

  const handleCsv = () => {
    if (!Array.isArray(data) || data.length === 0) return;
    let rows = data;
    if (csvColumns && csvColumns.length > 0) {
      rows = data.map((r) => {
        const out = {};
        for (const c of csvColumns) out[c] = r[c];
        return out;
      });
    }
    downloadCsvFromObjects(rows, `${safeName}.csv`);
  };

  const handlePng = async () => {
    try {
      await downloadChartAsPng(chartRef, `${safeName}.png`);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("Chart PNG export failed:", e);
    }
  };

  const showCsv = Array.isArray(data) && data.length > 0;
  const showPng = !!chartRef;

  if (!showCsv && !showPng) return null;

  return (
    <div className={`inline-flex items-center gap-1 ${className}`.trim()}>
      {showCsv && (
        <button
          type="button"
          onClick={handleCsv}
          title="Download chart data as CSV (opens in Excel)"
          className="px-2 py-1 rounded text-xs font-medium border border-gray-200 bg-white text-gray-700 hover:bg-gray-100"
        >
          CSV
        </button>
      )}
      {showPng && (
        <button
          type="button"
          onClick={handlePng}
          title="Download chart as PNG image"
          className="px-2 py-1 rounded text-xs font-medium border border-gray-200 bg-white text-gray-700 hover:bg-gray-100"
        >
          PNG
        </button>
      )}
    </div>
  );
}
