// src/app/api/sale_brand_channel/route.js
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
    const brandName = searchParams.get("brand_name") ?? "";
    const fileDate = searchParams.get("file_date") ?? "";

    const targetUrl = new URL("/api/sale_brand_channel", API_BASE_URL);
    targetUrl.searchParams.set("time_frame", timeFrame);
    if (brandName) targetUrl.searchParams.set("brand_name", brandName);
    if (fileDate) targetUrl.searchParams.set("file_date", fileDate);
    const yearList = searchParams.getAll("year_list");
    for (const y of yearList) targetUrl.searchParams.append("year_list", y);


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
