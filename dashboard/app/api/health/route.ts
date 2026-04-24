import { NextResponse } from "next/server";

const FASTAPI = process.env.FASTAPI_BASE_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  try {
    const res = await fetch(`${FASTAPI}/health`, { cache: "no-store" });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { status: "degraded", version: "unknown", checks: {}, error: "FastAPI unreachable" },
      { status: 502 }
    );
  }
}
