"use client";

import { useState } from "react";
import { getAccounts } from "@/lib/api";
import Sidebar from "@/components/ui/Sidebar";
import KPIStrip from "./KPIStrip";
import AccountsTable from "./AccountsTable";
import DetailPanel from "./DetailPanel";
import type { AccountsResponse } from "@/lib/types";

interface Props {
  initialData: AccountsResponse;
}

export default function DashboardShell({ initialData }: Props) {
  const [data, setData] = useState(initialData);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      const fresh = await getAccounts(50);
      setData(fresh);
      // Keep selected account open if it still exists in the refreshed data
      if (selectedId && !fresh.accounts.find((a) => a.account_id === selectedId)) {
        setSelectedId(null);
      }
    } finally {
      setRefreshing(false);
    }
  }

  function handleSelect(id: string) {
    // Clicking the already-selected row closes the panel
    setSelectedId((prev) => (prev === id ? null : id));
  }

  return (
    <div className="flex h-full bg-bg overflow-hidden">
      <Sidebar onRefresh={handleRefresh} refreshing={refreshing} />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Page header */}
        <div className="px-6 py-4 border-b border-border shrink-0">
          <h1 className="text-sm font-semibold text-text-primary">
            At-Risk Accounts
          </h1>
          <p className="text-xs text-text-tertiary font-mono mt-0.5">
            Scored {data.scored_date} · {data.total_accounts.toLocaleString()} accounts
          </p>
        </div>

        {/* KPI strip */}
        <div className="shrink-0">
          <KPIStrip data={data} />
        </div>

        {/* Table + slide-in detail panel */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto">
            <AccountsTable
              accounts={data.accounts}
              onSelect={handleSelect}
              selectedId={selectedId}
            />
          </div>

          {selectedId && (
            <DetailPanel
              accountId={selectedId}
              onClose={() => setSelectedId(null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
