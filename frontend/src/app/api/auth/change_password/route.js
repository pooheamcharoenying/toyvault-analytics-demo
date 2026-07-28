import { NextResponse } from "next/server";
import axios from "axios";

export const runtime = "nodejs";

const API_BASE_URL = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "https://toyvault-analytics-demo-production.up.railway.app";
const API_BASIC_USER = process.env.API_BASIC_USER;
const API_BASIC_PASS = process.env.API_BASIC_PASS;
const _AUTH = API_BASIC_USER && API_BASIC_PASS ? { username: API_BASIC_USER, password: API_BASIC_PASS } : undefined;

const COOKIE = "tv_session";

export async function POST(req) {
  const token = req.cookies.get(COOKIE)?.value || "";
  if (!token) return NextResponse.json({ error: "Not signed in" }, { status: 401 });
  try {
    const body = await req.json().catch(() => ({}));
    const url = new URL("/api/auth/change_password", API_BASE_URL).toString();
    const r = await axios.post(url, body, { auth: _AUTH, headers: { "X-Session-Token": token } });
    return NextResponse.json(r.data);
  } catch (err) {
    return NextResponse.json(
      { error: err.response?.data?.detail || "Could not change password" },
      { status: err.response?.status || 422 }
    );
  }
}
