import DashboardShell from "@/components/dashboard/DashboardShell";
import type { AccountsResponse } from "@/lib/types";

/**
 * Server Component — fetches the initial account list directly from FastAPI
 * at render time. The browser never waits for a client-side fetch on first load.
 * Client refreshes go through /api/accounts (the Next.js proxy route).
 */
async function fetchAccounts(): Promise<AccountsResponse> {
  const base = process.env.FASTAPI_BASE_URL ?? "http://127.0.0.1:8000";
  const res = await fetch(`${base}/accounts?limit=50`, { cache: "no-store" });

  if (!res.ok) {
    throw new Error(
      `FastAPI returned ${res.status}. Make sure uvicorn is running on port 8000.`
    );
  }
  return res.json() as Promise<AccountsResponse>;
}

export default async function DashboardPage() {
  let data;
  try {
    data = await fetchAccounts();
  } catch (err) {
    return (
      <div className="flex h-full items-center justify-center bg-bg">
        <div className="max-w-sm text-center space-y-3">
          <p className="text-risk-critical font-semibold">FastAPI is not reachable</p>
          <p className="text-sm text-text-secondary">
            Start the API server and refresh:
          </p>
          <code className="block text-xs font-mono bg-surface border border-border rounded px-3 py-2 text-text-secondary">
            uvicorn api.main:app --host 127.0.0.1 --port 8000
          </code>
          <p className="text-xs text-text-tertiary font-mono">
            {String(err).slice(0, 120)}
          </p>
        </div>
      </div>
    );
  }
  return <DashboardShell initialData={data} />;
}
