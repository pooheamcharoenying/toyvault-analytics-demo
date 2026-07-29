"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useAssistant } from "./AssistantProvider";
import DataTable from "./DataTable";

// --- Markdown table extraction (for CSV download) ---------------------------
function extractMarkdownTables(text) {
  const lines = text.split(/\r?\n/);
  const tables = [];
  let i = 0;
  while (i < lines.length) {
    const isRow = /^\s*\|.*\|\s*$/.test(lines[i]);
    const nextIsSep = i + 1 < lines.length && /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(lines[i + 1]);
    if (isRow && nextIsSep) {
      const header = splitMdRow(lines[i]);
      let j = i + 2;
      const rows = [];
      while (j < lines.length && /^\s*\|.*\|\s*$/.test(lines[j])) { rows.push(splitMdRow(lines[j])); j++; }
      tables.push({ header, rows });
      i = j;
    } else i++;
  }
  return tables;
}
function splitMdRow(line) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}
function rowsToCsv(rows) {
  return rows
    .map((r) => r.map((c) => {
      const cleaned = c.replace(/(\d),(?=\d{3}\b)/g, "$1");
      return /[",\n]/.test(cleaned) ? `"${cleaned.replace(/"/g, '""')}"` : cleaned;
    }).join(","))
    .join("\n");
}
function downloadCsv(csv, name = "toyvault_answer.csv") {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

const MD = {
  p: (p) => <p className="mb-2 last:mb-0 break-words" {...p} />,
  strong: (p) => <strong className="font-semibold text-[var(--nichi-blue-dark)]" {...p} />,
  ul: (p) => <ul className="list-disc pl-5 mb-2 space-y-0.5" {...p} />,
  ol: (p) => <ol className="list-decimal pl-5 mb-2 space-y-0.5" {...p} />,
  li: (p) => <li className="break-words" {...p} />,
  a: (p) => <a className="text-[var(--nichi-blue)] underline" target="_blank" rel="noreferrer" {...p} />,
  code: (p) => <code className="px-1 py-0.5 rounded bg-gray-100 text-[12px] font-mono" {...p} />,
  table: (p) => <div className="overflow-x-auto rounded border border-gray-200 my-2"><table className="text-xs border-collapse w-full" {...p} /></div>,
  thead: (p) => <thead className="bg-gray-100" {...p} />,
  th: (p) => <th className="px-2 py-1 text-left border-b border-gray-200 whitespace-nowrap font-semibold" {...p} />,
  td: (p) => <td className="px-2 py-1 border-b border-gray-100 whitespace-nowrap tabular-nums" {...p} />,
};

function ReplyBody({ text }) {
  const tables = extractMarkdownTables(text);
  const csv = tables.length ? rowsToCsv([tables[0].header, ...tables[0].rows]) : null;
  return (
    <div className="text-sm leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{text}</ReactMarkdown>
      {csv && (
        <button onClick={() => downloadCsv(csv)}
                className="mt-1 text-xs px-2 py-1 rounded border border-[var(--nichi-blue)] text-[var(--nichi-blue)] hover:bg-blue-50">
          ⬇ Download CSV
        </button>
      )}
    </div>
  );
}

const SUGGESTIONS = [
  "How's the business doing overall?",
  "Which brands make the most money?",
  "What's about to run out of stock?",
  "Which locations are most efficient?",
];

// The chat surface: message list + composer. Conversation state lives in the
// shared AssistantProvider, so the widget and the full page show the same thread.
export default function AssistantChat({ variant = "panel" }) {
  const { messages, busy, send } = useAssistant();
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);
  const isPage = variant === "page";

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, busy]);

  const submit = (text) => {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    setInput("");
    send(q);
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-3 bg-[var(--nichi-gray-50)]">
        <div className={isPage ? "max-w-3xl mx-auto w-full space-y-3" : ""}>
          {messages.length === 0 && (
            <div className="text-sm text-gray-600">
              <p className="mb-3">Ask me about revenue, brands, locations, channels, or inventory — every number comes straight from your live data.</p>
              <div className={isPage ? "grid gap-2 sm:grid-cols-2" : "grid gap-2"}>
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => submit(s)}
                          className="text-left text-xs px-3 py-2 rounded-lg border border-gray-200 bg-white hover:border-[var(--nichi-blue)] hover:bg-blue-50 transition">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className={`${isPage ? "max-w-[80%]" : "max-w-[88%]"} px-3 py-2 rounded-2xl rounded-br-sm text-sm bg-[var(--nichi-blue)] text-white`}>
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={i} className="flex flex-col items-start gap-1">
                <div className={`${isPage ? "max-w-[80%]" : "max-w-[88%]"} px-3 py-2 rounded-2xl rounded-bl-sm text-sm ${
                  m.error ? "bg-red-50 text-red-800 border border-red-200" : "bg-white text-gray-800 border border-gray-200"
                }`}>
                  <ReplyBody text={m.content} />
                </div>
                {m.datasets?.map((ds, di) => (
                  <div key={di} className="w-full">
                    <DataTable title={ds.title} columns={ds.columns} rows={ds.rows} total_available={ds.total_available} />
                  </div>
                ))}
                {m.download?.url && (
                  <a href={m.download.url} target="_blank" rel="noreferrer"
                     className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-[var(--nichi-blue)] text-[var(--nichi-blue)] hover:bg-blue-50">
                    ⬇ {m.download.filename || "Download file"}
                  </a>
                )}
                {m.version && !m.error && (
                  <span className="text-[10px] text-gray-400 pl-1">ToyVault AI v{m.version}</span>
                )}
              </div>
            )
          ))}
          {busy && (
            <div className="flex justify-start">
              <div className="px-3 py-2 rounded-2xl rounded-bl-sm bg-white border border-gray-200 text-sm text-gray-500">
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); submit(); }}
            className="flex items-end gap-2 p-3 border-t border-gray-200 bg-white shrink-0">
        <div className={isPage ? "flex items-end gap-2 max-w-3xl mx-auto w-full" : "flex items-end gap-2 w-full"}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
            placeholder="Ask about your business…"
            rows={1}
            className="flex-1 resize-none max-h-28 px-3 py-2 text-sm border border-gray-300 rounded-xl focus:border-[var(--nichi-blue)] focus:outline-none"
          />
          <button type="submit" disabled={busy || !input.trim()}
                  className="shrink-0 w-10 h-10 rounded-full bg-[var(--nichi-blue)] text-white flex items-center justify-center disabled:opacity-40 hover:bg-[var(--nichi-blue-light)]">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      </form>
      <div className="px-3 pb-2 text-[10px] text-gray-400 bg-white text-center shrink-0">
        Every figure is fetched from your data, never invented.
      </div>
    </div>
  );
}
