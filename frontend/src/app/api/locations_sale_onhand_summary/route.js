// src/app/api/locations_sale_onhand_summary/route.js
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

    // 🔎 read ?time_frame=weekly|monthly from the client request
    // 🧭 build target URL and pass the same query param through
    const targetUrl = new URL("/api/sale_onhand_locations_summary", API_BASE_URL);


    const response = await axios.get(targetUrl.toString(), {
      auth: { username: API_BASIC_USER, password: API_BASIC_PASS },
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
