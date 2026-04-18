// src/app/api/sale_channel_brand/route.js
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
    const { searchParams } = new URL(req.url);
    const timeFrame = searchParams.get("time_frame") || "monthly";
    const channelName = searchParams.get("channel_name") ?? "";
    const fileDate = searchParams.get("file_date") ?? "";

    const targetUrl = new URL("/api/sale_channel_brand", API_BASE_URL);
    targetUrl.searchParams.set("time_frame", timeFrame);
    if (channelName) targetUrl.searchParams.set("channel_name", channelName);
    if (fileDate) targetUrl.searchParams.set("file_date", fileDate);
    const yearList = searchParams.getAll("year_list");
    for (const y of yearList) targetUrl.searchParams.append("year_list", y);


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
