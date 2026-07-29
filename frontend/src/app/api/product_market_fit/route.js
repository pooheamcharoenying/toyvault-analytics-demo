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
    const location = searchParams.get("location");
    if (!location) {
      return NextResponse.json(
        { error: "Missing required query param: location" },
        { status: 400 }
      );
    }
    const targetUrl = new URL("/api/product_market_fit", API_BASE_URL);
    targetUrl.searchParams.set("location", location);
    searchParams.getAll("year_list").forEach((y) =>
      targetUrl.searchParams.append("year_list", y)
    );
    if (searchParams.get("top_n")) {
      targetUrl.searchParams.set("top_n", searchParams.get("top_n"));
    }

    const response = await axios.get(targetUrl.toString(), {
      auth: _AUTH,
      // 120s — under normal cold cache the compute finishes in ~5s, but during
      // the window right after a data upload the single-worker backend can
      // queue long-running requests past 30s.
      timeout: 120_000,
    });
    return NextResponse.json(response.data, { status: response.status });
  } catch (err) {
    return NextResponse.json(
      { error: "Server error", details: err.response?.data || err.message },
      { status: err.response?.status || 500 }
    );
  }
}
