import { RISK_BADGE } from "@/lib/utils";
import type { RiskLevel } from "@/lib/types";

export default function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span
      className={`inline-flex px-2 py-0.5 text-xs font-medium rounded border ${RISK_BADGE[level]}`}
    >
      {level}
    </span>
  );
}
