"use client";

import { useState } from "react";
import AssistantChat from "./AssistantChat";
import ThreadList from "./ThreadList";
import { useAssistant } from "./AssistantProvider";

export default function AssistantWidget() {
  const { newChat } = useAssistant();
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const panelClass = fullscreen
    ? "fixed inset-3 sm:inset-6 z-[60] flex flex-col rounded-2xl bg-white shadow-2xl border border-gray-200 overflow-hidden"
    : "fixed bottom-5 right-5 z-[60] flex flex-col w-[min(400px,calc(100vw-2.5rem))] h-[min(620px,calc(100vh-2.5rem))] rounded-2xl bg-white shadow-2xl border border-gray-200 overflow-hidden";

  const iconBtn = "p-1.5 rounded hover:bg-white/10";

  return (
    <div className="no-print">
      {!open && (
        <button
          onClick={() => setOpen(true)}
          aria-label="Open AI Assist"
          className="fixed bottom-5 right-5 z-[60] flex items-center gap-2 pl-4 pr-5 h-14 rounded-full bg-[var(--nichi-blue)] text-white shadow-xl hover:bg-[var(--nichi-blue-light)] transition-all"
        >
          <svg className="w-6 h-6 text-[var(--nichi-yellow)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-4 4v-4z" />
          </svg>
          <span className="text-sm font-semibold">AI Assist</span>
        </button>
      )}

      {open && (
        <div className={panelClass}>
          <div className="flex items-center justify-between px-3 py-3 bg-[var(--nichi-blue)] text-white shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="w-2 h-2 rounded-full bg-green-400 shrink-0" />
              <div className="min-w-0">
                <div className="text-sm font-semibold leading-tight truncate">ToyVault AI Assist</div>
                <div className="text-[11px] text-white/70 leading-tight">Grounded in your live data</div>
              </div>
            </div>
            <div className="flex items-center gap-0.5 shrink-0">
              <button onClick={() => setShowHistory((s) => !s)} title="Chat history"
                      aria-label="Chat history" className={iconBtn}>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>
              <button onClick={() => { newChat(); setShowHistory(false); }} title="New chat"
                      aria-label="New chat" className={iconBtn}>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
              </button>
              <button onClick={() => setFullscreen((f) => !f)}
                      aria-label={fullscreen ? "Exit full screen" : "Full screen"} title={fullscreen ? "Exit full screen" : "Full screen"}
                      className={iconBtn}>
                {fullscreen ? (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9L4 4m0 0v4m0-4h4m7 5l5-5m0 0v4m0-4h-4M9 15l-5 5m0 0v-4m0 4h4m7-5l5 5m0 0v-4m0 4h-4" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-5v4m0-4h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
                  </svg>
                )}
              </button>
              <button onClick={() => setOpen(false)} aria-label="Close" className={iconBtn}>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {showHistory ? (
            <ThreadList onSelect={() => setShowHistory(false)} />
          ) : (
            <AssistantChat variant={fullscreen ? "page" : "panel"} />
          )}
        </div>
      )}
    </div>
  );
}
