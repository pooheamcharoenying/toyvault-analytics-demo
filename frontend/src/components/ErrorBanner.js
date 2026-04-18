"use client";

import { useState } from "react";

/**
 * Shared error banner with optional retry button.
 *
 * @param {string}   message  - Error message to display
 * @param {function} [onRetry] - Callback to retry the failed operation
 * @param {string}   [className] - Additional CSS classes
 */
export default function ErrorBanner({ message, onRetry, className = "" }) {
  const [retrying, setRetrying] = useState(false);

  if (!message) return null;

  const handleRetry = async () => {
    if (!onRetry) return;
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div
      className={`rounded-lg bg-red-50 border border-red-200 text-red-700 px-4 py-3 text-sm flex items-center justify-between gap-3 ${className}`}
      role="alert"
    >
      <span>
        <strong>Error:</strong> {message}
      </span>
      {onRetry && (
        <button
          onClick={handleRetry}
          disabled={retrying}
          className="shrink-0 px-3 py-1 rounded bg-red-600 text-white text-xs font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {retrying ? "Retrying…" : "Retry"}
        </button>
      )}
    </div>
  );
}
