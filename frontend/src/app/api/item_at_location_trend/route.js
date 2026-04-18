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
    const targetUrl = new URL("/api/item_at_location_trend", API_BASE_URL);
    if (searchParams.get("item_code")) targetUrl.searchParams.set("item_code", searchParams.get("item_code"));
    if (searchParams.get("whs_code")) targetUrl.searchParams.set("whs_code", searchParams.get("whs_code"));
    const years = searchParams.getAll("year_list");
    years.forEach((y) => targetUrl.searchParams.append("year_list", y));

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
