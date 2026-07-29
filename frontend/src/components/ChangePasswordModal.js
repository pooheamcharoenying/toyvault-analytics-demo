"use client";

import { useState } from "react";

function Field({ label, value, onChange, autoFocus }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <input type="password" value={value} autoFocus={autoFocus}
             onChange={(e) => onChange(e.target.value)} autoComplete="new-password"
             className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:border-[var(--nichi-blue)] focus:outline-none" />
    </div>
  );
}

export default function ChangePasswordModal({ onClose }) {
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [cf, setCf] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (nw !== cf) { setMsg({ kind: "err", text: "New passwords don't match." }); return; }
    if (nw.length < 8) { setMsg({ kind: "err", text: "New password must be at least 8 characters." }); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await fetch("/api/auth/change_password", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: cur, new_password: nw }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || "Failed to change password");
      setMsg({ kind: "ok", text: "Password changed successfully." });
      setTimeout(onClose, 900);
    } catch (err) {
      setMsg({ kind: "err", text: err.message });
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-[var(--nichi-blue)]">Change password</h2>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Current password" value={cur} onChange={setCur} autoFocus />
          <Field label="New password (min 8 chars)" value={nw} onChange={setNw} />
          <Field label="Confirm new password" value={cf} onChange={setCf} />
          {msg && <div className={`text-sm ${msg.kind === "ok" ? "text-green-700" : "text-red-600"}`}>{msg.text}</div>}
          <button type="submit" disabled={busy || !cur || !nw || !cf}
                  className="w-full py-2 rounded-lg bg-[var(--nichi-blue)] text-white font-semibold hover:bg-[var(--nichi-blue-light)] disabled:opacity-40">
            {busy ? "Saving…" : "Change password"}
          </button>
        </form>
      </div>
    </div>
  );
}
