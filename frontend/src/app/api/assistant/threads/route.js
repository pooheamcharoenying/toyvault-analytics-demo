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

// Forward to the backend with the service Basic auth and the user's session
// (so the backend scopes threads to the logged-in user).
async function forward(method, path, req, body) {
  const url = new URL(path, API_BASE_URL).toString();
  const token = sessionToken(req);
  const headers = {};
  if (token) headers["X-Session-Token"] = token;
  return axios({ method, url, data: body, headers, auth: _AUTH, timeout: 120000 });
}

// List the current user's threads
export async function GET(req) {
  try {
    const r = await forward("get", "/api/assistant/threads", req);
    return NextResponse.json(r.data, { status: r.status });
  } catch (err) { return fail(err); }
}

// Create an empty thread
export async function POST(req) {
  try {
    const body = await req.json().catch(() => ({}));
    const r = await forward("post", "/api/assistant/threads", req, body);
    return NextResponse.json(r.data, { status: r.status });
  } catch (err) { return fail(err); }
}
