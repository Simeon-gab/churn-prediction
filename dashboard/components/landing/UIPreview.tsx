/**
 * Static UI mockup panels used in landing page scroll sections.
 * These are illustrative — styled to look like the real product.
 */

// ── Scoring output: terminal-style panel ──────────────────────────────────
export function ScoringPreview() {
  const tiers = [
    { name: "Critical", count: 273,  pct: "53.7", cls: "text-risk-critical" },
    { name: "High",     count: 3,    pct: "0.6",  cls: "text-risk-high" },
    { name: "Medium",   count: 24,   pct: "4.7",  cls: "text-risk-medium" },
    { name: "Low",      count: 210,  pct: "41.2", cls: "text-risk-low" },
  ];

  return (
    <div className="bg-surface border border-border rounded-xl p-5 font-mono text-sm shadow-lg">
      <p className="text-text-tertiary text-xs mb-3">
        $ python scripts/score_accounts.py
      </p>
      <p className="text-text-secondary text-xs mb-3">
        Scoring 5,000 subscriptions...
      </p>
      <div className="border-t border-border my-2" />
      <div className="space-y-1.5">
        {tiers.map(({ name, count, pct, cls }) => (
          <div key={name} className="flex justify-between items-center">
            <span className={`text-xs ${cls}`}>{name}</span>
            <span className="text-xs text-text-tertiary tabular-nums">
              {count}&nbsp;&nbsp;{pct}%
            </span>
          </div>
        ))}
      </div>
      <div className="border-t border-border my-2" />
      <p className="text-xs text-accent">✓ 502 accounts synced to HubSpot</p>
    </div>
  );
}

// ── SHAP explanation: mini horizontal bars ────────────────────────────────
export function SHAPPreview() {
  const increasing = [
    { label: "Days as a customer",   w: 95 },
    { label: "Product usage",        w: 72 },
    { label: "Support tickets",      w: 55 },
  ];
  const decreasing = [
    { label: "Feature adoption rate", w: 68 },
    { label: "Avg response time",     w: 44 },
  ];

  return (
    <div className="bg-surface border border-border rounded-xl p-5 shadow-lg space-y-4">
      <p className="text-xs text-text-tertiary uppercase tracking-wide">
        SHAP explanation — Account A-c43359
      </p>

      <div className="space-y-2">
        <p className="text-xs text-text-tertiary">Factors increasing risk</p>
        {increasing.map(({ label, w }) => (
          <div key={label} className="flex items-center gap-3">
            <span className="text-xs text-text-secondary w-36 truncate shrink-0">{label}</span>
            <div className="flex-1 h-1.5 bg-surface-hover rounded-full overflow-hidden">
              <div className="h-full bg-risk-critical rounded-full" style={{ width: `${w}%` }} />
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <p className="text-xs text-text-tertiary">Factors decreasing risk</p>
        {decreasing.map(({ label, w }) => (
          <div key={label} className="flex items-center gap-3">
            <span className="text-xs text-text-secondary w-36 truncate shrink-0">{label}</span>
            <div className="flex-1 h-1.5 bg-surface-hover rounded-full overflow-hidden">
              <div className="h-full bg-risk-low rounded-full" style={{ width: `${w}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── HubSpot sync: mini CRM table ──────────────────────────────────────────
export function HubSpotPreview() {
  const rows = [
    { id: "A-c43359", tier: "Critical", score: "78.0%" },
    { id: "A-712426", tier: "Critical", score: "77.8%" },
    { id: "A-e60f9d", tier: "Critical", score: "77.8%" },
    { id: "A-ab438f", tier: "High",     score: "62.4%" },
    { id: "A-d4e0d4", tier: "Medium",   score: "38.2%" },
  ];

  const tierColor: Record<string, string> = {
    Critical: "text-risk-critical",
    High:     "text-risk-high",
    Medium:   "text-risk-medium",
    Low:      "text-risk-low",
  };

  return (
    <div className="bg-surface border border-border rounded-xl p-5 shadow-lg">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs text-text-tertiary uppercase tracking-wide">
          HubSpot Companies
        </span>
        <span className="text-xs text-accent font-mono">502 synced</span>
      </div>
      <div className="space-y-0">
        {rows.map(({ id, tier, score }) => (
          <div
            key={id}
            className="flex items-center justify-between py-2 border-b border-border last:border-0"
          >
            <span className="font-mono text-xs text-text-secondary">{id}</span>
            <span className={`text-xs font-medium ${tierColor[tier]}`}>{tier}</span>
            <span className="font-mono text-xs text-text-tertiary tabular-nums">{score}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
