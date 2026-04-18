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

export async function POST(req) {
  try {
    assertEnv();

    const body = await req.json();
    const { barcodes } = body || {};
    if (!Array.isArray(barcodes)) {
      return NextResponse.json(
        { error: "Payload must be { barcodes: string[] }" },
        { status: 400 }
      );
    }

    const targetUrl = new URL("/api/barcodes", API_BASE_URL);

    const response = await axios.post(targetUrl.toString(), { barcodes }, {
      auth: {
        username: API_BASIC_USER,
        password: API_BASIC_PASS,
      },
      headers: { "Content-Type": "application/json" },
    });

    return NextResponse.json(response.data, { status: response.status });

  } catch (err) {
    return NextResponse.json(
      { error: "Server error", details: err.response?.data || err.message },
      { status: err.response?.status || 500 }
    );
  }
}
