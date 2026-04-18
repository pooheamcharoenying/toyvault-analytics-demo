// src/app/task2/page.js
"use client";

import useTask2Data from "./hooks/useTask2Data";
import ButtonGrid from "./components/ButtonGrid";
import MonthlyMatrixTable from "./components/MonthlyMatrixTable";

const includeSnippets = ["_Sold_THB"];

export default function Task2() {
  const data = useTask2Data();

  return (
    <div className="font-sans min-h-screen bg-[var(--nichi-gray-50)] text-slate-800">
      <header className="flex items-center justify-center p-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">ToyVault Operations</h1>
        </div>
      </header>

      <main className="mx-auto max-w-[1200px] px-6 pb-24">
        {!data.dataReady && (
          <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Workbook data is not ready yet. Buttons stay disabled until the status bar shows &quot;Data ready&quot;.
          </p>
        )}

        <ButtonGrid {...data} />

        <MonthlyMatrixTable
          rows={data.rows}
          title="Sales (QTY & THB) by Month"
          indexKey="__index"
          includeSnippets={includeSnippets}
          enableColumnFilter={data.tableColFilterOn}
          viewMode={data.viewMode}
          channelColorMap={data.channelColorMap}
          brandColorMap={data.brandColorMap}
        />
      </main>
    </div>
  );
}
