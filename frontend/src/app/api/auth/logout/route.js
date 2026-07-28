import { NextResponse } from "next/server";

export const runtime = "nodejs";

const COOKIE = "tv_session";

export async function POST() {
  const res = NextResponse.json({ status: "ok" });
  res.cookies.set(COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
