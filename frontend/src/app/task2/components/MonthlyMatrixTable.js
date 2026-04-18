"use client";

import { useMemo, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
} from "recharts";
import { CONSISTENT_PALETTE } from "@/utils/chartColors";
import { displayColumnName, formatPeriodLabel } from "@/utils/columnDisplayNames";
import { fmtThbShort } from "@/utils/formatters";
import { downloadCsv } from "@/utils/csvExport";

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function MonthlyMatrixTable({
  rows,
  title = "Table",
  indexKey = "__index",
  includeSnippets = [],
  enableColumnFilter = true,
  viewMode = "",
  channelColorMap = {},
  brandColorMap = {},
}) {
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState("asc");

  const handleSort = (col) => {
    if (sortCol === col) {
      if (sortDir === "asc") setSortDir("desc");
      else { setSortCol(null); setSortDir("asc"); }
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  };

  const sortIndicator = (col) => {
    if (sortCol !== col) return " \u2195";
    return sortDir === "asc" ? " \u2191" : " \u2193";
  };

  const safeRows = Array.isArray(rows) ? rows : [];

  const allKeys = useMemo(() => {
    return Array.from(
      safeRows.reduce((set, r) => {
        Object.keys(r || {}).forEach((k) => set.add(k));
        return set;
      }, new Set())
    ).filter((k) => k !== indexKey);
  }, [safeRows, indexKey]);

  const filteredColumns = useMemo(() => {
    return enableColumnFilter && includeSnippets.length > 0
      ? allKeys.filter((k) => includeSnippets.some((snip) => k.includes(snip)))
      : allKeys;
  }, [allKeys, enableColumnFilter, includeSnippets]);

  const sortedRows = useMemo(() => {
    if (!sortCol) return safeRows;
    const isLabel = sortCol === "__label";
    return [...safeRows].sort((a, b) => {
      let va = isLabel ? (a[indexKey] ?? "") : a[sortCol];
      let vb = isLabel ? (b[indexKey] ?? "") : b[sortCol];
      if (va == null) va = "";
      if (vb == null) vb = "";
      if (typeof va === "number" && typeof vb === "number") {
        return sortDir === "asc" ? va - vb : vb - va;
      }
      const sa = String(va).toLowerCase();
      const sb = String(vb).toLowerCase();
      if (sa < sb) return sortDir === "asc" ? -1 : 1;
      if (sa > sb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [safeRows, sortCol, sortDir, indexKey]);

  const isTimeSeriesView = ["sales_channel", "sales_brand", "brand_channel", "channel_brand"].includes(viewMode);

  const timeSeriesChartData = useMemo(() => {
    if (!isTimeSeriesView || !safeRows.length || !filteredColumns.length) return { data: [], entities: [] };

    const entities = safeRows
      .filter((r) => r[indexKey] && String(r[indexKey]) !== "Total")
      .map((r) => String(r[indexKey]));

    const data = filteredColumns.map((col) => {
      const rawPeriod = col.replace(/_Sold_THB$|_OnHand_THB$|_Sold_QTY$|_OnHand_QTY$/, "");
      const periodLabel = formatPeriodLabel(rawPeriod);
      const point = { period: periodLabel };
      safeRows.forEach((r) => {
        const name = String(r[indexKey] ?? "");
        if (name && name !== "Total") {
          point[name] = Number(r[col]) || 0;
        }
      });
      return point;
    });

    return { data, entities };
  }, [safeRows, filteredColumns, indexKey, isTimeSeriesView]);

  const barChartData = useMemo(() => {
    if (isTimeSeriesView || !safeRows.length || !filteredColumns.length) return [];

    const metricPriority = [
      "Tot_Sold_THB", "Total Sold Master THB", "LineTotal", "Master Sale Value",
      "Total_Sold_THB", "Sold_THB", "OnHand_THB", "Tot_OnHand_THB",
    ];
    let metricCol = metricPriority.find((m) => allKeys.includes(m));
    if (!metricCol) {
      metricCol = allKeys.find((k) => {
        const sample = safeRows.find((r) => r[k] != null);
        return sample && typeof sample[k] === "number";
      });
    }
    if (!metricCol) return [];

    return safeRows
      .filter((r) => r[indexKey] && String(r[indexKey]) !== "Total")
      .map((r) => ({
        name: String(r[indexKey] ?? ""),
        value: Number(r[metricCol]) || 0,
        _metric: metricCol,
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 15);
  }, [safeRows, filteredColumns, allKeys, indexKey, isTimeSeriesView]);

  const activeColorMap = useMemo(() => {
    if (viewMode === "sales_channel" || viewMode === "brand_channel") return channelColorMap;
    if (viewMode === "sales_brand" || viewMode === "channel_brand") return brandColorMap;
    return {};
  }, [viewMode, channelColorMap, brandColorMap]);

  const getEntityColor = (name, idx) => {
    return activeColorMap[name] || CONSISTENT_PALETTE[idx % CONSISTENT_PALETTE.length];
  };

  const nfInt = useMemo(
    () => new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }),
    []
  );
  const nfTHB = useMemo(
    () => new Intl.NumberFormat(undefined, { style: "currency", currency: "THB" }),
    []
  );
  const nfFloat = useMemo(
    () => new Intl.NumberFormat(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 }),
    []
  );

  if (safeRows.length === 0) {
    return (
      <div className="w-full rounded-2xl border border-gray-200 p-6 text-center text-gray-500">
        No data to display
      </div>
    );
  }

  if (!filteredColumns.length) {
    return (
      <div className="w-full rounded-2xl border border-gray-200 p-6 text-center text-gray-500">
        No columns matched the selected filters.
      </div>
    );
  }

  const chartMetricLabel = displayColumnName(barChartData[0]?._metric || "Value");

  const formatCell = (key, value) => {
    if (value === null || value === undefined) return "";
    if (typeof value === "number") {
      if (/_THB$/.test(key) || /THB/.test(key)) return nfTHB.format(value);
      if (/_QTY$/.test(key) || /QTY/.test(key)) return nfInt.format(value);
      return nfFloat.format(value);
    }
    return String(value);
  };

  const exportCSV = () => {
    const headers = ["Label"].concat(filteredColumns.map(displayColumnName));
    const csvRows = sortedRows.map((row) =>
      [row?.[indexKey] ?? ""].concat(filteredColumns.map((c) => row?.[c]))
    );
    downloadCsv(`${title.replace(/\s+/g, "_")}.csv`, headers, csvRows);
  };

  return (
    <div className="w-full">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCSV}
            className="rounded-xl border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-100 active:scale-[0.98]"
          >
            Download CSV
          </button>
        </div>
      </div>

      {isTimeSeriesView && timeSeriesChartData.data.length > 0 && (
        <div className="mb-4 w-full rounded-2xl border border-gray-200 p-4 bg-white" style={{ minHeight: 360 }}>
          <p className="text-sm font-medium mb-2 text-gray-700">
            Sales Trend Over Time
          </p>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={timeSeriesChartData.data} margin={{ left: 8, right: 16, bottom: 40 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-zinc-200" />
              <XAxis dataKey="period" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" />
              <YAxis tickFormatter={fmtThbShort} />
              <Tooltip formatter={(v) => [Number(v).toLocaleString(), undefined]} />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
              {timeSeriesChartData.entities.map((entity, i) => (
                <Line
                  key={entity}
                  type="monotone"
                  dataKey={entity}
                  stroke={getEntityColor(entity, i)}
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  activeDot={{ r: 4 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {!isTimeSeriesView && barChartData.length > 0 && (
        <div className="mb-4 h-72 w-full rounded-2xl border border-gray-200 p-4 bg-white">
          <p className="text-sm font-medium mb-2 text-gray-700">
            Top by {chartMetricLabel}
          </p>
          <ResponsiveContainer width="100%" height="90%">
            <BarChart
              data={[...barChartData].reverse()}
              layout="vertical"
              margin={{ left: 8, right: 16 }}
            >
              <CartesianGrid strokeDasharray="3 3" className="stroke-zinc-200" />
              <XAxis type="number" tickFormatter={fmtThbShort} />
              <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 10 }} />
              <Tooltip formatter={(v) => [Number(v).toLocaleString(), chartMetricLabel]} />
              <Legend />
              <Bar dataKey="value" name={chartMetricLabel} radius={[0, 4, 4, 0]}>
                {barChartData.map((entry, i) => (
                  <Cell key={i} fill={getEntityColor(entry.name, i)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="overflow-auto rounded-2xl border border-gray-200">
        <table className="min-w-[900px] table-auto border-collapse">
          <thead>
            <tr className="bg-gray-50 text-left text-sm">
              <th
                className="sticky left-0 z-10 bg-gray-50 px-3 py-2 font-medium text-gray-700 cursor-pointer select-none hover:bg-gray-100"
                onClick={() => handleSort("__label")}
              >
                Label{sortIndicator("__label")}
              </th>
              {filteredColumns.map((c) => (
                <th
                  key={c}
                  className="px-3 py-2 font-medium text-gray-700 whitespace-nowrap cursor-pointer select-none hover:bg-gray-100"
                  title={c}
                  onClick={() => handleSort(c)}
                >
                  {displayColumnName(c)}{sortIndicator(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, idx) => (
              <tr
                key={idx}
                className={
                  idx % 2
                    ? "bg-white"
                    : "bg-gray-50/50"
                }
              >
                <td className="sticky left-0 z-10 bg-white px-3 py-2 text-sm text-gray-600">
                  {row?.[indexKey] ?? ""}
                </td>
                {filteredColumns.map((c) => (
                  <td key={c} className="px-3 py-2 text-sm tabular-nums">
                    {formatCell(c, row?.[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-2 text-xs text-gray-500">
        {enableColumnFilter
          ? "Showing Sold (THB) columns. "
          : "Showing all columns. "}
        Click column headers to sort.
      </p>
    </div>
  );
}
