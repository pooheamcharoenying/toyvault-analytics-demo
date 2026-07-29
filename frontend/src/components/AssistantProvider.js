"use client";

import { createContext, useContext, useState, useCallback, useEffect, useMemo } from "react";

const Ctx = createContext(null);
export const useAssistant = () => useContext(Ctx);

// Shared assistant state: the user's threads and the active conversation. Mounted
// once (in the layout) so the floating widget and the full page share the same
// current thread and message list.
export default function AssistantProvider({ children }) {
  const [threads, setThreads] = useState([]);
  const [currentId, setCurrentId] = useState(null); // null => an unsaved new chat
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loadingThreads, setLoadingThreads] = useState(false);

  const refreshThreads = useCallback(async () => {
    setLoadingThreads(true);
    try {
      const r = await fetch("/api/assistant/threads", { cache: "no-store" });
      if (r.ok) { const j = await r.json(); setThreads(j.threads || []); }
    } catch { /* ignore */ }
    finally { setLoadingThreads(false); }
  }, []);

  useEffect(() => { refreshThreads(); }, [refreshThreads]);

  const newChat = useCallback(() => {
    setCurrentId(null);
    setMessages([]);
  }, []);

  const selectThread = useCallback(async (tid) => {
    if (tid === currentId) return;
    setBusy(false);
    try {
      const r = await fetch(`/api/assistant/threads/${encodeURIComponent(tid)}`, { cache: "no-store" });
      if (!r.ok) throw new Error();
      const j = await r.json();
      setCurrentId(tid);
      setMessages((j.messages || []).map((m) => ({
        role: m.role, content: m.content, datasets: m.data?.datasets, version: m.data?.version,
      })));
    } catch {
      // thread vanished — fall back to a new chat
      newChat();
      refreshThreads();
    }
  }, [currentId, newChat, refreshThreads]);

  const send = useCallback(async (text) => {
    const q = (text || "").trim();
    if (!q || busy) return;
    setMessages((m) => [...m, { role: "user", content: q }]);
    setBusy(true);
    const target = currentId || "new";
    try {
      const res = await fetch(`/api/assistant/threads/${encodeURIComponent(target)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q }),
      });
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || `HTTP ${res.status}`);
      if (j.thread_id && j.thread_id !== currentId) setCurrentId(j.thread_id);
      setMessages((m) => [...m, { role: "assistant", content: j.reply || "(no answer)", datasets: j.datasets, version: j.version, download: j.download }]);
      refreshThreads(); // update titles / ordering / a newly-created thread
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `Sorry — ${e.message}`, error: true }]);
    } finally {
      setBusy(false);
    }
  }, [busy, currentId, refreshThreads]);

  const renameThread = useCallback(async (tid, title) => {
    await fetch(`/api/assistant/threads/${encodeURIComponent(tid)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }).catch(() => {});
    refreshThreads();
  }, [refreshThreads]);

  const deleteThread = useCallback(async (tid) => {
    await fetch(`/api/assistant/threads/${encodeURIComponent(tid)}`, { method: "DELETE" }).catch(() => {});
    if (tid === currentId) newChat();
    refreshThreads();
  }, [currentId, newChat, refreshThreads]);

  const value = useMemo(() => ({
    threads, currentId, messages, busy, loadingThreads,
    refreshThreads, newChat, selectThread, send, renameThread, deleteThread,
  }), [threads, currentId, messages, busy, loadingThreads,
      refreshThreads, newChat, selectThread, send, renameThread, deleteThread]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
