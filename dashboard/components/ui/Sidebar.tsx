"use client";

import Link from "next/link";
import HealthDot from "./HealthDot";

interface SidebarProps {
  onRefresh?: () => void;
  refreshing?: boolean;
}

export default function Sidebar({ onRefresh, refreshing }: SidebarProps) {
  return (
    <aside className="w-52 shrink-0 h-full bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-border">
        <span className="text-accent font-semibold text-sm tracking-wide">
          Churn AI
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <Link
          href="/dashboard"
          className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text-primary bg-surface-hover transition-colors duration-150 hover:bg-surface-hover"
        >
          <svg
            width="14" height="14" viewBox="0 0 14 14" fill="none"
            className="shrink-0 text-text-secondary"
          >
            <rect x="1" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
            <rect x="8" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
            <rect x="1" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
            <rect x="8" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" />
          </svg>
          Accounts
        </Link>
      </nav>

      {/* Bottom: health + refresh */}
      <div className="px-4 py-4 border-t border-border space-y-3">
        <HealthDot />
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="w-full text-xs text-text-secondary hover:text-text-primary px-3 py-1.5 rounded border border-border hover:border-text-tertiary disabled:opacity-40 disabled:cursor-not-allowed transition-colors duration-150"
          >
            {refreshing ? "Refreshing..." : "Refresh data"}
          </button>
        )}
      </div>
    </aside>
  );
}
