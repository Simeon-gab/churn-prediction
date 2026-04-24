"use client";

import { useEffect, useState } from "react";
import { calcDelta } from "@/lib/utils";
import type { AccountsResponse, RiskLevel } from "@/lib/types";

/** Smoothly counts from 0 to `target` over `durationMs` on mount */
function useCountUp(target: number, durationMs = 800): number {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (target === 0) { setValue(0); return; }
    const start = performance.now();

    const tick = (now: number) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / durationMs, 1);
      // ease-out: decelerate as progress → 1
      const eased = 1 - Math.pow(1 - progress, 2);
      setValue(Math.round(eased * target));
      if (progress < 1) requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
  }, [target, durationMs]);

  return value;
}

function KPICard({
  label,
  delay,
  children,
}: {
  label: string;
  delay: number;
  children: React.ReactNode;
}) {
  return (
    <div
      className="bg-surface border border-border rounded-lg px-5 py-4 flex flex-col gap-2 animate-fade-up"
      style={{ animationDelay: `${delay}ms` }}
    >
      <p className="text-xs text-text-tertiary font-medium uppercase tracking-wide">
        {label}
      </p>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

// Maps tier names to static Tailwind classes (must be static strings for JIT)
const TIER_TEXT: Record<RiskLevel, string> = {
  Critical: "text-risk-critical",
  High:     "text-risk-high",
  Medium:   "text-risk-medium",
  Low:      "text-risk-low",
};

export default function KPIStrip({ data }: { data: AccountsResponse }) {
  const totalCount    = useCountUp(data.total_accounts);
  const criticalCount = data.tier_counts["Critical"] ?? 0;
  const critDisplayed = useCountUp(criticalCount);

  const avgScore =
    data.accounts.length > 0
      ? data.accounts.reduce((s, a) => s + a.churn_probability, 0) /
        data.accounts.length
      : 0;

  const prevCritical = data.previous_tier_counts?.["Critical"] ?? null;
  const delta = calcDelta(criticalCount, prevCritical);

  return (
    <div className="grid grid-cols-4 gap-4 px-6 py-5">
      {/* Card 1: Total accounts */}
      <KPICard label="Total Accounts" delay={0}>
        <span className="text-3xl font-semibold font-mono text-text-primary tabular-nums">
          {totalCount.toLocaleString()}
        </span>
        <span className="text-xs text-text-tertiary">scored accounts</span>
      </KPICard>

      {/* Card 2: Critical tier change vs last run */}
      <KPICard label="Critical Accounts" delay={80}>
        <span className="text-3xl font-semibold font-mono text-risk-critical tabular-nums">
          {critDisplayed.toLocaleString()}
        </span>
        {delta === null ? (
          <span className="text-xs font-mono text-text-tertiary">— no prior run</span>
        ) : delta.delta === 0 ? (
          <span className="text-xs font-mono text-text-tertiary">no change vs last run</span>
        ) : (
          <span
            className={`text-xs font-mono ${
              delta.delta > 0 ? "text-risk-medium" : "text-risk-low"
            }`}
          >
            {delta.delta > 0 ? "+" : ""}
            {delta.delta} ({delta.delta > 0 ? "+" : ""}
            {delta.pct.toFixed(1)}%) vs last run
          </span>
        )}
      </KPICard>

      {/* Card 3: Average risk score */}
      <KPICard label="Avg Risk Score" delay={160}>
        <span className="text-3xl font-semibold font-mono text-text-primary tabular-nums">
          {(avgScore * 100).toFixed(1)}%
        </span>
        <span className="text-xs text-text-tertiary">mean churn probability</span>
      </KPICard>

      {/* Card 4: Risk tier distribution */}
      <KPICard label="Risk Distribution" delay={240}>
        <div className="space-y-1.5 pt-0.5">
          {(["Critical", "High", "Medium", "Low"] as RiskLevel[]).map((tier) => (
            <div key={tier} className="flex items-center justify-between text-xs gap-2">
              <span className="text-text-secondary w-14">{tier}</span>
              {/* Mini bar */}
              <div className="flex-1 h-1 bg-surface-hover rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${TIER_TEXT[tier].replace("text-", "bg-")}`}
                  style={{
                    width: `${
                      data.total_accounts > 0
                        ? (((data.tier_counts[tier] ?? 0) / data.total_accounts) * 100).toFixed(1)
                        : 0
                    }%`,
                  }}
                />
              </div>
              <span className={`font-mono font-medium w-8 text-right tabular-nums ${TIER_TEXT[tier]}`}>
                {data.tier_counts[tier] ?? 0}
              </span>
            </div>
          ))}
        </div>
      </KPICard>
    </div>
  );
}
