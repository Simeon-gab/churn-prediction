"use client";

import { useEffect, useState } from "react";
import { CalendarDays, ExternalLink, Mail } from "lucide-react";
import { getExplain, getHubSpotUrl } from "@/lib/api";
import RiskBadge from "./RiskBadge";
import SHAPChart from "./SHAPChart";
import type { ExplainResponse, RiskLevel } from "@/lib/types";

interface Props {
  accountId: string;
  onClose: () => void;
}

const BOOKING_URL =
  process.env.NEXT_PUBLIC_BOOKING_URL ?? "https://calendly.com/example";

export default function DetailPanel({ accountId, onClose }: Props) {
  const [data, setData] = useState<ExplainResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hubspotUrl, setHubspotUrl] = useState<string | null>(null);
  const [hubspotReason, setHubspotReason] = useState<string>("Loading...");

  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);
    setHubspotUrl(null);
    setHubspotReason("Loading...");

    Promise.allSettled([
      getExplain(accountId),
      getHubSpotUrl(accountId),
    ]).then(([explainResult, hubspotResult]) => {
      if (explainResult.status === "fulfilled") {
        setData(explainResult.value);
      } else {
        setError((explainResult.reason as Error).message);
      }

      if (hubspotResult.status === "fulfilled") {
        setHubspotUrl(hubspotResult.value.url ?? null);
        setHubspotReason(
          hubspotResult.value.reason ?? "HubSpot URL unavailable"
        );
      } else {
        setHubspotReason("HubSpot lookup failed");
      }

      setLoading(false);
    });
  }, [accountId]);

  const emailHref = [
    `mailto:contact+${accountId}@example.com`,
    `?subject=${encodeURIComponent("Checking in on your account")}`,
    `&body=${encodeURIComponent(
      `Hi there,\n\nWe wanted to check in on your account and see how things are going. We have some insights that might be valuable for your team — would you be open to a quick 20-minute conversation?\n\nBest,\nCustomer Success`
    )}`,
  ].join("");

  return (
    <div className="w-80 shrink-0 h-full bg-surface border-l border-border flex flex-col animate-slide-in">
      {/* Header */}
      <div className="flex items-start justify-between px-5 py-4 border-b border-border">
        <div className="min-w-0">
          <p className="text-xs text-text-tertiary font-mono mb-0.5">Account</p>
          <p className="text-sm font-mono text-text-primary truncate">{accountId}</p>
        </div>
        <button
          onClick={onClose}
          className="ml-3 shrink-0 text-text-tertiary hover:text-text-primary transition-colors duration-150 text-lg leading-none mt-0.5"
          aria-label="Close panel"
        >
          ×
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {loading && (
          <p className="text-sm text-text-tertiary">Loading explanation...</p>
        )}

        {error && (
          <p className="text-sm text-risk-critical">{error}</p>
        )}

        {data && (
          <div className="space-y-5">
            {/* Score + tier */}
            <div className="flex items-center gap-3">
              <RiskBadge level={data.risk_level as RiskLevel} />
              <span className="font-mono text-2xl font-semibold text-text-primary tabular-nums">
                {(data.churn_probability * 100).toFixed(1)}%
              </span>
            </div>

            {/* Scoring timestamp */}
            <p className="text-xs text-text-tertiary font-mono">
              Scored {data.scored_at?.split("T")[0]}
              {data.explanation_source === "on_demand" && (
                <span className="ml-2 text-risk-medium">(on-demand)</span>
              )}
            </p>

            {/* SHAP explanation */}
            <div>
              <p className="text-xs text-text-tertiary uppercase tracking-wide mb-3">
                Why this score
              </p>
              <SHAPChart factors={data.top_factors} />
            </div>

            {/* Subscription list (only shown for multi-subscription accounts) */}
            {data.subscriptions.length > 1 && (
              <div>
                <p className="text-xs text-text-tertiary uppercase tracking-wide mb-2">
                  Subscriptions ({data.subscriptions.length})
                </p>
                <div className="space-y-1.5">
                  {data.subscriptions.map((sub) => (
                    <div
                      key={sub.subscription_id}
                      className="flex items-center justify-between text-xs py-1.5 border-b border-border last:border-0"
                    >
                      <span className="font-mono text-text-secondary truncate mr-2">
                        {sub.subscription_id}
                      </span>
                      <RiskBadge level={sub.risk_level as RiskLevel} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div>
              <p className="text-xs text-text-tertiary uppercase tracking-wide mb-3">
                Actions
              </p>
              <div className="flex flex-col gap-2">
                {/* View in HubSpot — primary (accent green) */}
                {hubspotUrl ? (
                  <a
                    href={hubspotUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-2 w-full py-2 px-3 rounded-md bg-accent text-bg text-xs font-semibold hover:opacity-90 transition-opacity"
                  >
                    <ExternalLink size={13} strokeWidth={2.5} />
                    View in HubSpot
                  </a>
                ) : (
                  <span title={hubspotReason} className="w-full">
                    <button
                      disabled
                      className="flex items-center justify-center gap-2 w-full py-2 px-3 rounded-md bg-accent/15 text-accent/35 text-xs font-semibold cursor-not-allowed"
                    >
                      <ExternalLink size={13} strokeWidth={2.5} />
                      View in HubSpot
                    </button>
                  </span>
                )}

                {/* Send email — outlined */}
                <a
                  href={emailHref}
                  className="flex items-center justify-center gap-2 w-full py-2 px-3 rounded-md border border-border text-text-secondary text-xs font-medium hover:border-text-tertiary hover:text-text-primary transition-colors"
                >
                  <Mail size={13} strokeWidth={2} />
                  Send email
                </a>

                {/* Book call — outlined */}
                <a
                  href={BOOKING_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 w-full py-2 px-3 rounded-md border border-border text-text-secondary text-xs font-medium hover:border-text-tertiary hover:text-text-primary transition-colors"
                >
                  <CalendarDays size={13} strokeWidth={2} />
                  Book call
                </a>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
