import { NextResponse } from "next/server";

const FASTAPI = process.env.FASTAPI_BASE_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limit = searchParams.get("limit") ?? "50";

  try {
    const res = await fetch(`${FASTAPI}/accounts?limit=${limit}`, {
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "FastAPI unreachable — is uvicorn running on port 8000?" },
      { status: 502 }
    );
  }
}
