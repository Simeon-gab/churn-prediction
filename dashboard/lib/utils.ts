import type { RiskLevel } from "./types";

/** Tailwind text-color class for each risk tier */
export const RISK_TEXT: Record<RiskLevel, string> = {
  Critical: "text-risk-critical",
  High:     "text-risk-high",
  Medium:   "text-risk-medium",
  Low:      "text-risk-low",
};

/** Tailwind classes for the colored badge chip */
export const RISK_BADGE: Record<RiskLevel, string> = {
  Critical: "bg-risk-critical/10 text-risk-critical border-risk-critical/30",
  High:     "bg-risk-high/10     text-risk-high     border-risk-high/30",
  Medium:   "bg-risk-medium/10   text-risk-medium   border-risk-medium/30",
  Low:      "bg-risk-low/10      text-risk-low      border-risk-low/30",
};

/** 0.7823 → "78.2%" */
export function formatPct(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/** "2026-04-20" → "Apr 20, 2026" */
export function formatDate(dateStr: string): string {
  return new Date(dateStr + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Delta between current and previous count.
 * Returns null when there is no prior run to compare against.
 */
export function calcDelta(
  current: number,
  previous: number | null | undefined
): { delta: number; pct: number } | null {
  if (previous == null) return null;
  const delta = current - previous;
  const pct = previous > 0 ? (delta / previous) * 100 : 0;
  return { delta, pct };
}
