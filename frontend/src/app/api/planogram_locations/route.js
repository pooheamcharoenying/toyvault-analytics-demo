import { NextResponse } from "next/server";
import axios from "axios";

export const runtime = "nodejs";

const API_BASE_URL = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "https://toyvault-analytics-demo-production.up.railway.app";
const API_BASIC_USER = process.env.API_BASIC_USER;
const API_BASIC_PASS = process.env.API_BASIC_PASS;


const _AUTH = API_BASIC_USER && API_BASIC_PASS
  ? { username: API_BASIC_USER, password: API_BASIC_PASS }
  : undefined;

function assertEnv() {
  if (!API_BASE_URL) throw new Error("Missing env var: API_BASE_URL");
}

export async function GET() {
  try {
    assertEnv();
    const targetUrl = new URL("/api/planogram_locations", API_BASE_URL);

    const response = await axios.get(targetUrl.toString(), { auth: _AUTH });
    return NextResponse.json(response.data, { status: response.status });
  } catch (err) {
    const status = err?.response?.status || 500;
    const detail = err?.response?.data?.detail || err?.response?.data?.error || err.message;
    return NextResponse.json({ error: detail }, { status });
  }
}
