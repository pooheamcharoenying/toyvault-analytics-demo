import { NextResponse } from "next/server";
import axios from "axios";

export const runtime = "nodejs";

const API_BASE_URL = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_URL;
const API_BASIC_USER = process.env.API_BASIC_USER;
const API_BASIC_PASS = process.env.API_BASIC_PASS;

function assertEnv() {
  const missing = [];
  if (!API_BASE_URL) missing.push("API_BASE_URL or NEXT_PUBLIC_API_URL");
  if (!API_BASIC_USER) missing.push("API_BASIC_USER");
  if (!API_BASIC_PASS) missing.push("API_BASIC_PASS");
  if (missing.length) throw new Error("Missing env vars: " + missing.join(", "));
}

export async function GET(req) {
  try {
    assertEnv();
    const { searchParams } = new URL(req.url);
    const windowDays = searchParams.get("window_days") || "90";
    const thresholdDays = searchParams.get("threshold_days") || "30";
    const topN = searchParams.get("top_n") || "50";

    const brand = searchParams.get("brand");

    const targetUrl = new URL("/api/stockout_risk", API_BASE_URL);
    targetUrl.searchParams.set("window_days", windowDays);
    targetUrl.searchParams.set("threshold_days", thresholdDays);
    targetUrl.searchParams.set("top_n", topN);
    if (brand) targetUrl.searchParams.set("brand", brand);

    const response = await axios.get(targetUrl.toString(), {
      auth: { username: API_BASIC_USER, password: API_BASIC_PASS },
    });
    return NextResponse.json(response.data, { status: response.status });
  } catch (err) {
    return NextResponse.json(
      { error: "Server error", details: err.response?.data || err.message },
      { status: err.response?.status || 500 }
    );
  }
}
