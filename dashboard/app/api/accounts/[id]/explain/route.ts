import { NextResponse } from "next/server";

const FASTAPI = process.env.FASTAPI_BASE_URL ?? "http://127.0.0.1:8000";

// Next.js 15+ passes params as a Promise
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  try {
    const res = await fetch(`${FASTAPI}/explain/${encodeURIComponent(id)}`, {
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
