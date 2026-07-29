"use client";

import { useState } from "react";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";

// The ToyVault AI Assist LINE Official Account.
const LINE_ID = "@toyvault";
const ADD_FRIEND_URL = "https://line.me/R/ti/p/@toyvault";

function StepCard({ n, title, thai, children }) {
  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <span className="shrink-0 w-8 h-8 rounded-full bg-[var(--nichi-blue)] text-white flex items-center justify-center font-bold">
          {n}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-[var(--nichi-blue-dark)]">{title}</h2>
          {thai && <p className="text-xs text-gray-500 mb-3">{thai}</p>}
          {children}
        </div>
      </div>
    </section>
  );
}

export default function LineSetupPage() {
  const [code, setCode] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);

  const generateCode = async () => {
    setLoading(true);
    setErr(null);
    setCopied(false);
    try {
      const r = await fetch("/api/line/link_code", { method: "POST" });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || "Couldn't generate a code. Please try again.");
      setCode(j.code);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  const copyCode = () => {
    if (!code || !navigator.clipboard) return;
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  };

  return (
    <div className="bg-[var(--nichi-gray-50)] min-h-[calc(100dvh-3.5rem)]">
      <div className="max-w-2xl mx-auto px-4 py-6">
        <nav className="text-xs text-gray-500 mb-1">
          <Link href="/" className="hover:underline">Home</Link>{" › "}
          <span className="text-gray-800 font-medium">Connect LINE</span>
        </nav>
        <h1 className="text-xl font-bold text-[var(--nichi-blue)]">Chat with the AI on LINE</h1>
        <p className="text-sm text-gray-600 mb-1">
          Link your LINE account to ask the ToyVault AI Assist about the business right from LINE — same
          answers as the web app, on your phone.
        </p>
        <p className="text-xs text-gray-500 mb-5">
          เชื่อมบัญชี LINE ของคุณเพื่อคุยกับบอท ToyVault AI Assist ได้จากมือถือ — คำตอบเหมือนในเว็บแอปทุกอย่าง
        </p>

        <div className="space-y-4">
          {/* Step 1 — add the bot as a friend */}
          <StepCard n="1" title="Add the bot as a friend on LINE"
                    thai="แอดบอทเป็นเพื่อนใน LINE">
            <div className="flex flex-col sm:flex-row gap-5 items-center sm:items-start">
              <div className="shrink-0 rounded-xl border border-gray-200 p-2 bg-white">
                <QRCodeSVG value={ADD_FRIEND_URL} size={144} level="M" />
              </div>
              <div className="flex-1 text-sm text-gray-700 space-y-2">
                <p><span className="font-medium">On a computer:</span> scan this QR with the LINE app on your phone.</p>
                <p><span className="font-medium">On your phone:</span> tap the button below to open LINE and add the bot.</p>
                <a href={ADD_FRIEND_URL} target="_blank" rel="noreferrer"
                   className="inline-flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-white"
                   style={{ backgroundColor: "#06C755" }}>
                  <span>＋</span> Add ToyVault AI on LINE
                </a>
                <p className="text-xs text-gray-500">
                  Or search this LINE ID in <span className="whitespace-nowrap">Add friends → Search</span>:{" "}
                  <span className="font-mono font-semibold text-gray-800">{LINE_ID}</span>
                </p>
              </div>
            </div>
          </StepCard>

          {/* Step 2 — get a link code */}
          <StepCard n="2" title="Get your one-time link code"
                    thai="ขอรหัสเชื่อมบัญชี (ใช้ได้ 15 นาที)">
            <p className="text-sm text-gray-700 mb-3">
              This code ties your LINE to <span className="font-medium">your</span> ToyVault login. It expires in
              15 minutes — generate it right before you send it.
            </p>
            {code ? (
              <div className="flex flex-wrap items-center gap-3">
                <div className="px-6 py-3 rounded-xl bg-[var(--nichi-gray-50)] border border-gray-200 text-3xl font-bold tracking-[0.3em] text-[var(--nichi-blue)]">
                  {code}
                </div>
                <button onClick={copyCode}
                        className="text-sm px-3 py-2 rounded-lg border border-[var(--nichi-blue)] text-[var(--nichi-blue)] hover:bg-blue-50">
                  {copied ? "Copied ✓" : "Copy"}
                </button>
                <button onClick={generateCode} disabled={loading}
                        className="text-sm px-3 py-2 rounded-lg text-gray-500 hover:text-gray-700 disabled:opacity-50">
                  {loading ? "…" : "New code"}
                </button>
                <p className="w-full text-xs text-amber-600">Valid for 15 minutes.</p>
              </div>
            ) : (
              <button onClick={generateCode} disabled={loading}
                      className="px-4 py-2 rounded-lg bg-[var(--nichi-blue)] text-white font-semibold hover:bg-[var(--nichi-blue-light)] disabled:opacity-50">
                {loading ? "Generating…" : "Generate my link code"}
              </button>
            )}
            {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
          </StepCard>

          {/* Step 3 — send the code */}
          <StepCard n="3" title="Send the code to the bot in LINE"
                    thai="ส่งรหัสไปหาบอทใน LINE">
            <p className="text-sm text-gray-700">
              Open the chat with <span className="font-medium">ToyVault AI Assist</span> and send it the 6-character
              code. It replies <span className="font-medium">“✅ Linked to your-username”</span> — then just ask it
              anything about the business, in Thai or English.
            </p>
            <p className="mt-2 text-xs text-gray-500">
              เปิดแชทกับบอทแล้วส่งรหัส 6 ตัว บอทจะตอบ “✅ Linked to …” เชื่อมสำเร็จ แล้วถามเรื่องธุรกิจได้เลย
            </p>
          </StepCard>
        </div>
      </div>
    </div>
  );
}
