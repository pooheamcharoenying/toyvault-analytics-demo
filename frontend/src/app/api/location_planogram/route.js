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
      return NextResponse.json({ error: "location parameter is required" }, { status: 400 });
    }

    const targetUrl = new URL("/api/location_planogram", API_BASE_URL);
    targetUrl.searchParams.set("location", location);
    if (searchParams.get("year")) targetUrl.searchParams.set("year", searchParams.get("year"));
    if (searchParams.get("top_n")) targetUrl.searchParams.set("top_n", searchParams.get("top_n"));
    if (searchParams.get("all_items")) targetUrl.searchParams.set("all_items", searchParams.get("all_items"));
    if (searchParams.get("months_range")) targetUrl.searchParams.set("months_range", searchParams.get("months_range"));

    const response = await axios.get(targetUrl.toString(), { auth: _AUTH });
    return NextResponse.json(response.data, { status: response.status });
  } catch (err) {
    const status = err?.response?.status || 500;
    const detail = err?.response?.data?.detail || err?.response?.data?.error || err.message;
    return NextResponse.json({ error: detail }, { status });
  }
}

export async function PUT(req) {
  try {
    assertEnv();
    const { searchParams } = new URL(req.url);
    const location = searchParams.get("location");
    if (!location) {
      return NextResponse.json({ error: "location parameter is required" }, { status: 400 });
    }

    const body = await req.json();
    const targetUrl = new URL("/api/location_planogram", API_BASE_URL);
    targetUrl.searchParams.set("location", location);

    const response = await axios.put(targetUrl.toString(), body, { auth: _AUTH });
    return NextResponse.json(response.data, { status: response.status });
  } catch (err) {
    // 422 (validation) and 503 (Mongo unavailable) carry messages the user
    // needs to see verbatim, so pass the backend's detail straight through.
    const status = err?.response?.status || 500;
    const detail = err?.response?.data?.detail || err?.response?.data?.error || err.message;
    return NextResponse.json({ error: detail }, { status });
  }
}
