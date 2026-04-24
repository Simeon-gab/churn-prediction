"use client";

import { useState } from "react";
import RiskBadge from "./RiskBadge";
import type { AccountListItem, RiskLevel } from "@/lib/types";

// Higher number = higher risk (used for tier-grouped sort)
const RISK_ORDER: Record<RiskLevel, number> = {
  Critical: 4, High: 3, Medium: 2, Low: 1,
};

type SortKey = "churn_probability" | "risk_level" | "account_id";

interface Props {
  accounts: AccountListItem[];
  onSelect: (id: string) => void;
  selectedId: string | null;
}

function SortIcon({ active, dir }: { active: boolean; dir: "asc" | "desc" }) {
  if (!active) return <span className="ml-1 text-text-tertiary opacity-40">↕</span>;
  return <span className="ml-1">{dir === "desc" ? "↓" : "↑"}</span>;
}

export default function AccountsTable({ accounts, onSelect, selectedId }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("churn_probability");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = [...accounts].sort((a, b) => {
    let cmp = 0;
    if (sortKey === "churn_probability") {
      cmp = a.churn_probability - b.churn_probability;
    } else if (sortKey === "risk_level") {
      cmp = RISK_ORDER[a.risk_level as RiskLevel] - RISK_ORDER[b.risk_level as RiskLevel];
    } else {
      cmp = a.account_id.localeCompare(b.account_id);
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  function Th({
    label,
    k,
    align = "left",
  }: {
    label: string;
    k: SortKey;
    align?: "left" | "right";
  }) {
    const active = sortKey === k;
    return (
      <th
        onClick={() => handleSort(k)}
        className={`px-4 py-3 text-xs font-medium text-text-tertiary cursor-pointer select-none hover:text-text-secondary transition-colors duration-150 ${
          align === "right" ? "text-right" : "text-left"
        }`}
      >
        {label}
        <SortIcon active={active} dir={sortDir} />
      </th>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            <Th label="Account ID"  k="account_id" />
            <Th label="Risk Score"  k="churn_probability" align="right" />
            <Th label="Risk Level"  k="risk_level" />
            <th className="px-4 py-3 text-xs font-medium text-text-tertiary text-left">
              Scored
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sorted.map((account) => {
            const isSelected = selectedId === account.account_id;
            return (
              <tr
                key={account.account_id}
                onClick={() => onSelect(account.account_id)}
                className={`cursor-pointer transition-colors duration-150 hover:bg-surface-hover ${
                  isSelected ? "bg-surface-hover" : ""
                }`}
              >
                <td className="px-4 py-3 font-mono text-sm text-text-primary">
                  {account.account_id}
                </td>
                <td className="px-4 py-3 font-mono text-sm text-text-secondary text-right tabular-nums">
                  {(account.churn_probability * 100).toFixed(1)}%
                </td>
                <td className="px-4 py-3">
                  <RiskBadge level={account.risk_level as RiskLevel} />
                </td>
                <td className="px-4 py-3 font-mono text-xs text-text-tertiary">
                  {account.scored_date}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {accounts.length === 0 && (
        <div className="py-12 text-center text-sm text-text-tertiary">
          No accounts found.
        </div>
      )}
    </div>
  );
}
