import { NextResponse } from "next/server";
import axios from "axios";

export const runtime = "nodejs";

const API_BASE_URL = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "https://toyvault-analytics-demo-production.up.railway.app";
const API_BASIC_USER = process.env.API_BASIC_USER;
const API_BASIC_PASS = process.env.API_BASIC_PASS;
const _AUTH = API_BASIC_USER && API_BASIC_PASS ? { username: API_BASIC_USER, password: API_BASIC_PASS } : undefined;

const COOKIE = "tv_session";
const MAX_AGE = 60 * 60 * 24; // 24h

export async function POST(req) {
  try {
    const body = await req.json().catch(() => ({}));
    const url = new URL("/api/auth/login", API_BASE_URL).toString();
    const r = await axios.post(url, body, { auth: _AUTH });
    const { token, user } = r.data || {};
    const res = NextResponse.json({ user });
    res.cookies.set(COOKIE, token || "", {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: MAX_AGE,
    });
    return res;
  } catch (err) {
    return NextResponse.json(
      { error: err.response?.data?.detail || "Invalid username or password" },
      { status: err.response?.status || 401 }
    );
  }
}
