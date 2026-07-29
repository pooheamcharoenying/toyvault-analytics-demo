"use client";

import { useState } from "react";
import { useAssistant } from "./AssistantProvider";

export default function ThreadList({ onSelect }) {
  const { threads, currentId, selectThread, newChat, renameThread, deleteThread } = useAssistant();
  const [editing, setEditing] = useState(null);
  const [editTitle, setEditTitle] = useState("");

  const commitRename = (tid) => { renameThread(tid, editTitle.trim() || "Untitled"); setEditing(null); };

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <div className="p-2 shrink-0">
        <button onClick={() => { newChat(); onSelect?.(); }}
                className="w-full flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-[var(--nichi-blue)] text-white text-sm font-medium hover:bg-[var(--nichi-blue-light)]">
          + New chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {threads.length === 0 && (
          <div className="text-xs text-gray-400 px-2 py-3">No saved chats yet.</div>
        )}
        {threads.map((t) => (
          <div key={t.thread_id}
               className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm ${
                 t.thread_id === currentId ? "bg-blue-50 text-[var(--nichi-blue)]" : "hover:bg-gray-100 text-gray-700"}`}>
            {editing === t.thread_id ? (
              <input autoFocus value={editTitle}
                     onChange={(e) => setEditTitle(e.target.value)}
                     onBlur={() => commitRename(t.thread_id)}
                     onKeyDown={(e) => { if (e.key === "Enter") commitRename(t.thread_id); if (e.key === "Escape") setEditing(null); }}
                     className="flex-1 text-sm px-1 py-0.5 border border-gray-300 rounded" />
            ) : (
              <button onClick={() => { selectThread(t.thread_id); onSelect?.(); }}
                      className="flex-1 text-left truncate" title={t.title}>{t.title}</button>
            )}
            <button title="Rename" aria-label="Rename"
                    onClick={() => { setEditing(t.thread_id); setEditTitle(t.title); }}
                    className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-gray-600 text-xs px-1">✎</button>
            <button title="Delete" aria-label="Delete"
                    onClick={() => { if (window.confirm("Delete this chat?")) deleteThread(t.thread_id); }}
                    className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 text-xs px-1">✕</button>
          </div>
        ))}
      </div>
    </div>
  );
}
