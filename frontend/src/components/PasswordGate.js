"use client";

import { useState, useEffect } from "react";
import Cookies from "js-cookie";

export default function PasswordGate({ children }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [inputPassword, setInputPassword] = useState("");

  const PASSWORD = process.env.NEXT_PUBLIC_SITE_PASSWORD;
  // Public demo mode: if NEXT_PUBLIC_PUBLIC_MODE is set OR no password is configured,
  // skip the gate entirely so the app is open to anyone.
  const PUBLIC_MODE = process.env.NEXT_PUBLIC_PUBLIC_MODE === "true" || !PASSWORD;

  useEffect(() => {
    if (PUBLIC_MODE) {
      setAuthenticated(true);
      return;
    }
    const auth = Cookies.get("auth");
    if (auth === "true") {
      setAuthenticated(true);
    }
  }, [PUBLIC_MODE]);

  const handleLogin = (e) => {
    e?.preventDefault();
    if (inputPassword === PASSWORD) {
      Cookies.set("auth", "true", { expires: 1 });
      setAuthenticated(true);
    } else {
      alert("Incorrect password!");
    }
  };

  if (!authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gradient-to-br from-neutral-100 via-white to-neutral-50">
        <div className="bg-white rounded-2xl shadow-xl w-[340px] overflow-hidden border border-neutral-200">
          {/* Header band — matches the black navbar for brand consistency */}
          <div className="bg-black px-6 py-8 flex flex-col items-center">
            <h1 className="text-white font-bold text-2xl tracking-tight">
              TOY VAULT
            </h1>
            <p className="text-white/60 text-xs mt-1">Business Analytics Dashboard</p>
          </div>

          {/* Form */}
          <form onSubmit={handleLogin} className="px-6 py-6 space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-600 mb-1.5">Password</label>
              <input
                type="password"
                value={inputPassword}
                onChange={(e) => setInputPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--nichi-blue)]/30 focus:border-[var(--nichi-blue)] transition"
                placeholder="Enter password"
                autoFocus
              />
            </div>
            <button
              type="submit"
              className="w-full bg-[var(--nichi-blue)] text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-[var(--nichi-blue-dark)] transition shadow-sm"
            >
              Sign In
            </button>
          </form>
        </div>
        <p className="mt-6 text-slate-400 text-xs">ToyVault Analytics v1.0</p>
      </div>
    );
  }

  return children;
}
