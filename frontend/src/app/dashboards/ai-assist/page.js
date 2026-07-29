"use client";

import Link from "next/link";
import AssistantChat from "@/components/AssistantChat";
import ThreadList from "@/components/ThreadList";

export default function AiAssistPage() {
  return (
    <div className="bg-[var(--nichi-gray-50)]">
      <div className="max-w-6xl mx-auto px-4 py-4 flex flex-col" style={{ height: "calc(100dvh - 8rem)", minHeight: "500px" }}>
        <div className="mb-2 shrink-0">
          <nav className="text-xs text-gray-500">
            <Link href="/" className="hover:underline">Home</Link>{" › "}
            <span className="text-gray-800 font-medium">AI Assist</span>
          </nav>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <h1 className="text-xl font-bold text-[var(--nichi-blue)]">AI Assist</h1>
            <Link href="/dashboards/line-setup"
                  className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-[var(--nichi-blue)] hover:border-[var(--nichi-blue)] hover:bg-blue-50">
              📱 Chat with this AI on LINE →
            </Link>
          </div>
        </div>
        <div className="flex-1 min-h-0 flex gap-3">
          <aside className="hidden sm:block w-60 shrink-0 rounded-2xl border border-gray-200 bg-white overflow-hidden">
            <ThreadList />
          </aside>
          <div className="flex-1 min-h-0 rounded-2xl border border-gray-200 bg-white overflow-hidden shadow-sm">
            <AssistantChat variant="page" />
          </div>
        </div>
      </div>
    </div>
  );
}
