"use client";

import { useEffect, useState } from "react";
import type { FactorItem } from "@/lib/types";

/** Strip parenthetical units: "Days as a customer (days)" → "Days as a customer" */
function stripUnits(label: string): string {
  return label.split(" (")[0];
}

function impactLabel(shapValue: number): string {
  const abs = Math.abs(shapValue);
  if (abs >= 0.1)  return "strong";
  if (abs >= 0.05) return "moderate";
  return "mild";
}

function FactorBar({
  factor,
  maxAbs,
  index,
  color,
}: {
  factor: FactorItem;
  maxAbs: number;
  index: number;
  color: string;
}) {
  const targetWidth = (Math.abs(factor.shap_value) / Math.max(maxAbs, 0.001)) * 100;
  const [width, setWidth] = useState(0);

  // Animate bar from 0 → target width with a per-index stagger
  useEffect(() => {
    const id = setTimeout(() => setWidth(targetWidth), index * 55);
    return () => clearTimeout(id);
  }, [targetWidth, index]);

  return (
    <div className="flex items-center gap-3 group">
      <span className="text-xs text-text-secondary w-40 truncate shrink-0 group-hover:text-text-primary transition-colors duration-150">
        {stripUnits(factor.feature)}
      </span>
      <div className="flex-1 h-1.5 bg-surface-hover rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ease-out ${color}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="text-xs text-text-tertiary w-14 text-right shrink-0 tabular-nums">
        {impactLabel(factor.shap_value)}
      </span>
    </div>
  );
}

export default function SHAPChart({ factors }: { factors: FactorItem[] }) {
  const increasing = [...factors]
    .filter((f) => f.direction === "increases_risk")
    .sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value));

  const decreasing = [...factors]
    .filter((f) => f.direction === "decreases_risk")
    .sort((a, b) => Math.abs(b.shap_value) - Math.abs(a.shap_value));

  const maxAbs = Math.max(...factors.map((f) => Math.abs(f.shap_value)), 0.001);

  return (
    <div className="space-y-5">
      {increasing.length > 0 && (
        <div className="space-y-2.5">
          <p className="text-xs text-text-tertiary uppercase tracking-wide">
            Factors increasing risk
          </p>
          <div className="space-y-2">
            {increasing.map((f, i) => (
              <FactorBar
                key={f.raw_feature}
                factor={f}
                maxAbs={maxAbs}
                index={i}
                color="bg-risk-critical"
              />
            ))}
          </div>
        </div>
      )}

      {decreasing.length > 0 && (
        <div className="space-y-2.5">
          <p className="text-xs text-text-tertiary uppercase tracking-wide">
            Factors decreasing risk
          </p>
          <div className="space-y-2">
            {decreasing.map((f, i) => (
              <FactorBar
                key={f.raw_feature}
                factor={f}
                maxAbs={maxAbs}
                index={increasing.length + i}
                color="bg-risk-low"
              />
            ))}
          </div>
        </div>
      )}

      {factors.length === 0 && (
        <p className="text-xs text-text-tertiary">No explanation available.</p>
      )}
    </div>
  );
}
