"use client";

import { useState, useEffect } from "react";

export default function LinkLineModal({ onClose }) {
  const [code, setCode] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch("/api/line/link_code", { method: "POST" })
      .then((r) => r.json().catch(() => ({})))
      .then((j) => { if (j.code) setCode(j.code); else setErr(j.error || "Couldn't generate a code."); })
      .catch((e) => setErr(e.message));
  }, []);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-[var(--nichi-blue)]">Link your LINE</h2>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>
        <p className="text-sm text-gray-600 mb-3">
          Open the ToyVault LINE Official Account and send it this code within 15 minutes to link your account:
        </p>
        <div className="text-center my-4">
          {code ? (
            <div className="inline-block px-6 py-3 rounded-xl bg-[var(--nichi-gray-50)] border border-gray-200 text-3xl font-bold tracking-[0.3em] text-[var(--nichi-blue)]">
              {code}
            </div>
          ) : err ? (
            <div className="text-sm text-red-600">{err}</div>
          ) : (
            <div className="text-sm text-gray-400">Generating…</div>
          )}
        </div>
        <ol className="text-xs text-gray-500 space-y-1 list-decimal pl-5">
          <li>Add / open the ToyVault AI Assist LINE account.</li>
          <li>Send it the code above.</li>
          <li>You&apos;ll get a confirmation, then you can chat with the bot on LINE.</li>
        </ol>
        <button onClick={onClose}
                className="mt-5 w-full py-2 rounded-lg bg-[var(--nichi-blue)] text-white font-semibold hover:bg-[var(--nichi-blue-light)]">
          Done
        </button>
      </div>
    </div>
  );
}
