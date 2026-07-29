import { NextResponse } from "next/server";
import axios from "axios";

export const runtime = "nodejs";

const API_BASE_URL = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "https://toyvault-analytics-demo-production.up.railway.app";
const API_BASIC_USER = process.env.API_BASIC_USER;
const API_BASIC_PASS = process.env.API_BASIC_PASS;
const _AUTH = API_BASIC_USER && API_BASIC_PASS ? { username: API_BASIC_USER, password: API_BASIC_PASS } : undefined;

// The user's session token, from the httpOnly cookie set at login.
const sessionToken = (req) => req.cookies.get("tv_session")?.value || "";

function fail(err) {
  const status = err?.response?.status || 500;
  return NextResponse.json({ error: err?.response?.data?.detail || err.message }, { status });
}

async function forward(method, path, req, body) {
  const url = new URL(path, API_BASE_URL).toString();
  const token = sessionToken(req);
  const headers = {};
  if (token) headers["X-Session-Token"] = token;
  return axios({ method, url, data: body, headers, auth: _AUTH, timeout: 120000 });
}

// Get a thread's messages
export async function GET(req, { params }) {
  try {
    const { tid } = await params;
    const r = await forward("get", `/api/assistant/threads/${encodeURIComponent(tid)}`, req);
    return NextResponse.json(r.data, { status: r.status });
  } catch (err) { return fail(err); }
}

// Rename a thread
export async function PATCH(req, { params }) {
  try {
    const { tid } = await params;
    const body = await req.json();
    const r = await forward("patch", `/api/assistant/threads/${encodeURIComponent(tid)}`, req, body);
    return NextResponse.json(r.data, { status: r.status });
  } catch (err) { return fail(err); }
}

// Delete a thread
export async function DELETE(req, { params }) {
  try {
    const { tid } = await params;
    const r = await forward("delete", `/api/assistant/threads/${encodeURIComponent(tid)}`, req);
    return NextResponse.json(r.data, { status: r.status });
  } catch (err) { return fail(err); }
}
