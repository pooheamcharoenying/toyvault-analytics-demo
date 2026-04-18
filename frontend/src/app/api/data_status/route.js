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

export async function GET() {
  try {
    assertEnv();
    const targetUrl = new URL("/api/data/status", API_BASE_URL).toString();
    const response = await axios.get(targetUrl, {
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
