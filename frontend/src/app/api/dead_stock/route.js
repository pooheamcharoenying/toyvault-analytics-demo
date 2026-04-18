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

export async function GET(req) {
  try {
    assertEnv();
    const { searchParams } = new URL(req.url);
    const windowDays = searchParams.get("window_days") || "180";
    const topN = searchParams.get("top_n") || "100";

    const brand = searchParams.get("brand");

    const targetUrl = new URL("/api/dead_stock", API_BASE_URL);
    targetUrl.searchParams.set("window_days", windowDays);
    targetUrl.searchParams.set("top_n", topN);
    if (brand) targetUrl.searchParams.set("brand", brand);

    const response = await axios.get(targetUrl.toString(), {
      auth: _AUTH,
    });
    return NextResponse.json(response.data, { status: response.status });
  } catch (err) {
    return NextResponse.json(
      { error: "Server error", details: err.response?.data || err.message },
      { status: err.response?.status || 500 }
    );
  }
}
