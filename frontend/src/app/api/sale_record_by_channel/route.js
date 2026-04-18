// src/app/api/sale_record_by_channel/route.js
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

    // 🔎 read ?time_frame=weekly|monthly from the client request
    const { searchParams } = new URL(req.url);
    const timeFrame = searchParams.get("time_frame") || "monthly";

    // 🧭 build target URL and pass the same query param through
    const targetUrl = new URL("/api/sales_data_monthly_by_channel", API_BASE_URL);
    targetUrl.searchParams.set("time_frame", timeFrame);


    const response = await axios.get(targetUrl.toString(), {
      auth: _AUTH,
      // responseType: "text",
    });

    return NextResponse.json(response.data, { status: response.status });
  } catch (err) {
    return NextResponse.json(
      { error: "Server error", details: err.response?.data || err.message },
      { status: err.response?.status || 500 }
    );
  }
}
