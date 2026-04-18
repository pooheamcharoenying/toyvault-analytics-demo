"use client";

import { useEffect, useState } from "react";
import api, { isAbortError } from "@/utils/api";

const STALE_THRESHOLD_DAYS = 2;

/**
 * Shows a dismissible amber banner at the top of every page when the data
 * file is more than STALE_THRESHOLD_DAYS old. Fetches /api/get_file_date once
 * per session (cached in sessionStorage).
 */
export default function DataFreshnessBanner() {
  const [info, setInfo] = useState(null); // { dateStr, daysAgo }
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    // Check sessionStorage first to avoid repeat calls
    const cached = sessionStorage.getItem("data_file_date");
    if (cached) {
      const parsed = JSON.parse(cached);
      setInfo(parsed);
      return;
    }

    api
      .get("/api/get_file_date", { signal: controller.signal })
      .then((res) => {
        const raw = res.data;
        const dateStr =
          raw?.extracted_date || raw?.file_date || raw?.date || null;
        if (!dateStr) return;

        // Parse date — try common formats
        const fileDate = new Date(dateStr);
        if (isNaN(fileDate.getTime())) return;

        const now = new Date();
        const diffMs = now - fileDate;
        const daysAgo = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        const result = { dateStr, daysAgo };
        sessionStorage.setItem("data_file_date", JSON.stringify(result));
        setInfo(result);
      })
      .catch((err) => {
        if (!isAbortError(err)) {
          // Silently fail — don't block the app for a freshness check
        }
      });

    return () => controller.abort();
  }, []);

  if (!info || info.daysAgo <= STALE_THRESHOLD_DAYS || dismissed) return null;

  return (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 text-sm text-amber-800 flex items-center justify-between">
      <span>
        Data was last updated on <strong>{info.dateStr}</strong> — {info.daysAgo} days
        ago. Contact operations to upload the latest file.
      </span>
      <button
        onClick={() => setDismissed(true)}
        className="ml-4 text-amber-600 hover:text-amber-800 font-bold text-lg leading-none"
        aria-label="Dismiss stale data warning"
      >
        ×
      </button>
    </div>
  );
}
