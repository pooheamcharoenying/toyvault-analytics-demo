"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";

// Fallbacks if /api/line/bot_info can't be reached — the real values come from LINE.
const FALLBACK_LINE_ID = "@toyvault";
const FALLBACK_ADD_URL = "https://line.me/R/ti/p/@toyvault";
const FALLBACK_BOT_NAME = "ToyVault AI Assist";

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

// Always-visible identity of the Team Assist LINE bot: QR + name + LINE ID.
function BotCard({ bot }) {
  const name = bot?.name || FALLBACK_BOT_NAME;
  const lineId = bot?.basic_id || FALLBACK_LINE_ID;
  const addUrl = bot?.add_url || FALLBACK_ADD_URL;
  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col sm:flex-row gap-5 items-center sm:items-start">
        <div className="shrink-0 rounded-xl border border-gray-200 p-2 bg-white">
          <QRCodeSVG value={addUrl} size={132} level="M" />
        </div>
        <div className="flex-1 min-w-0 text-sm text-gray-700 space-y-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">The LINE bot</p>
          <div className="flex items-center gap-3">
            {bot?.picture_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={bot.picture_url} alt="" className="w-10 h-10 rounded-full object-cover border border-gray-200"
                   onError={(e) => { e.currentTarget.style.display = "none"; }} />
            ) : null}
            <div className="min-w-0">
              <p className="text-base font-bold text-[var(--nichi-blue-dark)] truncate">{name}</p>
              <p className="text-sm font-mono text-gray-600">LINE ID: {lineId}</p>
            </div>
          </div>
          <p className="text-gray-600 pt-1">
            Scan the QR with the LINE app, or on your phone tap:
          </p>
          <a href={addUrl} target="_blank" rel="noreferrer"
             className="inline-flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-white"
             style={{ backgroundColor: "#06C755" }}>
            <span>＋</span> Add {name} on LINE
          </a>
          <p className="text-xs text-gray-500 pt-1">
            Or in LINE: <span className="whitespace-nowrap">Add friends → Search</span> →{" "}
            <span className="font-mono font-semibold text-gray-800">{lineId}</span>
          </p>
        </div>
      </div>
    </section>
  );
}

export default function LineSetupPage() {
  const [bot, setBot] = useState(null);
  const [linked, setLinked] = useState(null);      // null = loading, else bool
  const [boundAt, setBoundAt] = useState(null);
  const [lineUserId, setLineUserId] = useState(null);
  const [displayName, setDisplayName] = useState(null);
  const [pictureUrl, setPictureUrl] = useState(null);
  const [justLinked, setJustLinked] = useState(false);
  const [code, setCode] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const pollRef = useRef(null);

  const checkStatus = useCallback(async () => {
    try {
      const r = await fetch("/api/line/status", { cache: "no-store" });
      const j = await r.json().catch(() => ({}));
      setLinked(!!j.linked);
      setBoundAt(j.bound_at || null);
      setLineUserId(j.line_user_id || null);
      setDisplayName(j.display_name || null);
      setPictureUrl(j.picture_url || null);
      return !!j.linked;
    } catch {
      setLinked(false);
      return false;
    }
  }, []);

  useEffect(() => {
    checkStatus();
    fetch("/api/line/bot_info", { cache: "no-store" })
      .then((r) => r.json().catch(() => ({})))
      .then((j) => { if (j && j.basic_id) setBot(j); })
      .catch(() => {});
    return () => clearInterval(pollRef.current);
  }, [checkStatus]);

  const generateCode = async () => {
    setLoading(true);
    setErr(null);
    setCopied(false);
    try {
      const r = await fetch("/api/line/link_code", { method: "POST" });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || "Couldn't generate a code. Please try again.");
      setCode(j.code);
      // Watch for the link completing on LINE, then flip to the connected state.
      clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        if (await checkStatus()) {
          clearInterval(pollRef.current);
          setCode(null);
          setJustLinked(true);
        }
      }, 3000);
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

  const disconnect = async () => {
    setDisconnecting(true);
    setErr(null);
    try {
      const r = await fetch("/api/line/disconnect", { method: "POST" });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.error || "Couldn't disconnect. Please try again.");
      }
      clearInterval(pollRef.current);
      setCode(null);
      setJustLinked(false);
      await checkStatus();
    } catch (e) {
      setErr(e.message);
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <div className="bg-[var(--nichi-gray-50)] min-h-[calc(100dvh-3.5rem)]">
      <div className="max-w-2xl mx-auto px-4 py-6 space-y-4">
        <div>
          <nav className="text-xs text-gray-500 mb-1">
            <Link href="/" className="hover:underline">Home</Link>{" › "}
            <span className="text-gray-800 font-medium">Connect LINE</span>
          </nav>
          <h1 className="text-xl font-bold text-[var(--nichi-blue)]">Chat with the AI on LINE</h1>
          <p className="text-sm text-gray-600">
            Link your LINE account to ask the ToyVault AI Assist about the business right from LINE —
            same answers as the web app, on your phone.
          </p>
          <p className="text-xs text-gray-500">
            เชื่อมบัญชี LINE ของคุณเพื่อคุยกับบอท ToyVault AI Assist ได้จากมือถือ — คำตอบเหมือนในเว็บแอปทุกอย่าง
          </p>
        </div>

        {/* Always show the bot's identity + QR, connected or not. */}
        <BotCard bot={bot} />

        {linked === null ? (
          <div className="rounded-2xl border border-gray-200 bg-white p-5 text-sm text-gray-400">
            Checking your LINE connection…
          </div>
        ) : linked ? (
          /* ---- Connected: show WHICH account ---- */
          <section className="rounded-2xl border border-green-200 bg-green-50 p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <span className="shrink-0 w-8 h-8 rounded-full bg-green-500 text-white flex items-center justify-center font-bold">✓</span>
              <div className="flex-1 min-w-0">
                <h2 className="text-base font-semibold text-green-800">
                  {justLinked ? "🎉 Connected to LINE!" : "Connected to LINE"}
                </h2>
                <div className="flex items-center gap-3 mt-2">
                  {pictureUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={pictureUrl} alt="" className="w-11 h-11 rounded-full object-cover border border-green-300"
                         onError={(e) => { e.currentTarget.style.display = "none"; }} />
                  ) : null}
                  <div className="min-w-0">
                    <p className="text-sm text-green-800">
                      Connected as <span className="font-semibold">{displayName || "your LINE account"}</span>
                    </p>
                    {lineUserId ? (
                      <p className="text-xs font-mono text-green-700 break-all">LINE ID: {lineUserId}</p>
                    ) : null}
                  </div>
                </div>
                <p className="text-sm text-green-700 mt-2">
                  Linked to your ToyVault account{boundAt ? ` since ${new Date(boundAt).toLocaleDateString()}` : ""}.
                  Just message this bot on LINE.
                </p>
                <p className="text-xs text-gray-500 mt-3">
                  Only one LINE account can be connected at a time. To use a different LINE, disconnect this one first.
                  <br />เชื่อมได้ครั้งละ 1 บัญชี — หากต้องการเปลี่ยนบัญชี ให้กดยกเลิกการเชื่อมต่อก่อน
                </p>
                <button onClick={disconnect} disabled={disconnecting}
                        className="mt-3 px-4 py-2 rounded-lg border border-red-300 text-red-600 font-semibold hover:bg-red-50 disabled:opacity-50">
                  {disconnecting ? "Disconnecting…" : "Disconnect LINE"}
                </button>
                {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
              </div>
            </div>
          </section>
        ) : (
          /* ---- Not connected: link with a one-time code ---- */
          <>
            <StepCard n="1" title="Get your one-time link code"
                      thai="ขอรหัสเชื่อมบัญชี (ใช้ได้ 15 นาที)">
              <p className="text-sm text-gray-700 mb-3">
                First add the bot above, then get this code — it ties your LINE to <span className="font-medium">your</span>{" "}
                ToyVault login and expires in 15 minutes.
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
                  <p className="w-full text-xs text-gray-500 flex items-center gap-2">
                    <span className="inline-flex gap-1">
                      <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </span>
                    Waiting for you to send the code on LINE… (valid 15 min)
                  </p>
                </div>
              ) : (
                <button onClick={generateCode} disabled={loading}
                        className="px-4 py-2 rounded-lg bg-[var(--nichi-blue)] text-white font-semibold hover:bg-[var(--nichi-blue-light)] disabled:opacity-50">
                  {loading ? "Generating…" : "Generate my link code"}
                </button>
              )}
              {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
            </StepCard>

            <StepCard n="2" title="Send the code to the bot in LINE"
                      thai="ส่งรหัสไปหาบอทใน LINE">
              <p className="text-sm text-gray-700">
                Open the chat with the bot and send it the 6-character code. It replies{" "}
                <span className="font-medium">“✅ Linked to your-username”</span> — this page updates to{" "}
                <span className="font-medium">Connected</span> automatically.
              </p>
              <p className="mt-2 text-xs text-gray-500">
                เปิดแชทกับบอทแล้วส่งรหัส 6 ตัว บอทจะตอบ “✅ Linked to …” หน้านี้จะขึ้นว่าเชื่อมต่อแล้วเอง
              </p>
            </StepCard>
          </>
        )}
      </div>
    </div>
  );
}
