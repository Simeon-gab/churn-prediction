"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

type Status = "loading" | "ok" | "degraded" | "error";

const DOT: Record<Status, string> = {
  loading:  "bg-text-tertiary",
  ok:       "bg-risk-low",
  degraded: "bg-risk-medium",
  error:    "bg-risk-critical",
};

const LABEL: Record<Status, string> = {
  loading:  "checking...",
  ok:       "API online",
  degraded: "API degraded",
  error:    "API offline",
};

export default function HealthDot() {
  const [status, setStatus] = useState<Status>("loading");

  // Check once on mount — no polling per design decision
  useEffect(() => {
    getHealth()
      .then((data) => setStatus(data.status === "ok" ? "ok" : "degraded"))
      .catch(() => setStatus("error"));
  }, []);

  return (
    <div className="flex items-center gap-2">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${DOT[status]}`} />
      <span className="text-xs text-text-tertiary">{LABEL[status]}</span>
    </div>
  );
}
