/**
 * Client-side fetch utilities.
 * All calls go through Next.js Route Handlers (/api/*) which proxy to FastAPI.
 * This keeps the FastAPI URL server-side and avoids CORS configuration.
 */

import type { AccountsResponse, ExplainResponse, HealthCheck, HubSpotUrlResponse } from "./types";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? ": " + body : ""}`);
  }
  return res.json() as Promise<T>;
}

export function getAccounts(limit = 50): Promise<AccountsResponse> {
  return apiFetch(`/api/accounts?limit=${limit}`);
}

export function getExplain(accountId: string): Promise<ExplainResponse> {
  return apiFetch(`/api/accounts/${encodeURIComponent(accountId)}/explain`);
}

export function getHealth(): Promise<HealthCheck> {
  return apiFetch("/api/health");
}

export function getHubSpotUrl(accountId: string): Promise<HubSpotUrlResponse> {
  return apiFetch(`/api/accounts/${encodeURIComponent(accountId)}/hubspot_url`);
}
