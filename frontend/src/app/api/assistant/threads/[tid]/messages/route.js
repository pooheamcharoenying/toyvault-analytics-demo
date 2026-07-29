import { NextResponse } from "next/server";
import axios from "axios";

export const runtime = "nodejs";
export const maxDuration = 120;

const API_BASE_URL = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "https://toyvault-analytics-demo-production.up.railway.app";
const API_BASIC_USER = process.env.API_BASIC_USER;
const API_BASIC_PASS = process.env.API_BASIC_PASS;
const _AUTH = API_BASIC_USER && API_BASIC_PASS ? { username: API_BASIC_USER, password: API_BASIC_PASS } : undefined;

// The user's session token, from the httpOnly cookie set at login.
const sessionToken = (req) => req.cookies.get("tv_session")?.value || "";

// Send a message in a thread — the backend runs the agent and persists both the
// question and the answer. tid may be "new" to start a fresh thread.
export async function POST(req, { params }) {
  try {
    const { tid } = await params;
    const body = await req.json();
    const url = new URL(`/api/assistant/threads/${encodeURIComponent(tid)}/messages`, API_BASE_URL).toString();
    const token = sessionToken(req);
    const headers = {};
    if (token) headers["X-Session-Token"] = token;
    const r = await axios({ method: "post", url, data: body, headers, auth: _AUTH, timeout: 120000 });
    return NextResponse.json(r.data, { status: r.status });
  } catch (err) {
    const status = err?.response?.status || 500;
    return NextResponse.json({ error: err?.response?.data?.detail || err.message }, { status });
  }
}
