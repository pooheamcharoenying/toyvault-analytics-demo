"use client";

import { useState, useEffect, useCallback, createContext, useContext } from "react";

const AuthContext = createContext(null);
// value: { user: {username, role, display_name}, logout: fn }
export const useAuthUser = () => useContext(AuthContext);

function LoginScreen({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.error || "Invalid username or password");
      onSuccess();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--nichi-blue)] px-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-2xl p-8">
        <div className="text-center mb-6">
          <div className="text-2xl font-bold text-[var(--nichi-blue)] tracking-wide">TOYVAULT</div>
          <div className="text-sm text-gray-500 mt-1">Business Analytics Dashboard</div>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus
                   autoComplete="username"
                   className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:border-[var(--nichi-blue)] focus:outline-none" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   autoComplete="current-password"
                   className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:border-[var(--nichi-blue)] focus:outline-none" />
          </div>
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button type="submit" disabled={busy || !username || !password}
                  className="w-full py-2 rounded-lg bg-[var(--nichi-blue)] text-white font-semibold hover:bg-[var(--nichi-blue-light)] disabled:opacity-40">
            {busy ? "Signing in…" : "Sign In"}
          </button>
        </form>
        <div className="text-center text-[11px] text-gray-400 mt-6">ToyVault Analytics · authorised users only</div>
      </div>
    </div>
  );
}

export default function AuthGate({ children }) {
  const [status, setStatus] = useState("checking"); // checking | authed | anon
  const [user, setUser] = useState(null);

  const check = useCallback(async () => {
    try {
      const res = await fetch("/api/auth/me", { cache: "no-store" });
      if (res.ok) {
        const j = await res.json();
        setUser(j.user);
        setStatus("authed");
      } else {
        setStatus("anon");
      }
    } catch {
      setStatus("anon");
    }
  }, []);

  const logout = useCallback(async () => {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch {}
    setUser(null);
    setStatus("anon");
  }, []);

  useEffect(() => { check(); }, [check]);

  if (status === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-8 h-8 border-2 border-[var(--nichi-blue)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (status === "anon") return <LoginScreen onSuccess={check} />;
  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
}
