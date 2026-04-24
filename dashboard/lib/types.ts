/**
 * TypeScript interfaces that mirror api/schemas.py exactly.
 * When Pydantic schemas change, update these too.
 */

export type RiskLevel = "Critical" | "High" | "Medium" | "Low";

export interface FactorItem {
  feature: string;       // human-readable label
  raw_feature: string;   // model column name
  shap_value: number;    // percentage-point contribution (positive = increases risk)
  direction: "increases_risk" | "decreases_risk";
}

export interface SubscriptionScore {
  subscription_id: string;
  churn_probability: number;
  risk_level: RiskLevel;
  scored_at: string;      // ISO-8601 timestamp
  scored_date: string;    // YYYY-MM-DD
  top_factors: FactorItem[] | null;
}

export interface ScoreResponse {
  account_id: string;
  churn_probability: number;
  risk_level: RiskLevel;
  scored_at: string;
  scored_date: string;
  subscriptions: SubscriptionScore[];
}

export interface ExplainResponse {
  account_id: string;
  churn_probability: number;
  risk_level: RiskLevel;
  scored_at: string;
  top_factors: FactorItem[];
  explanation_source: "precomputed" | "on_demand";
  subscriptions: SubscriptionScore[];
}

export interface HealthCheck {
  status: "ok" | "degraded";
  version: string;
  checks: Record<string, { status: string; detail: string }>;
}

/** One row in GET /accounts — one account, highest-risk subscription wins */
export interface AccountListItem {
  account_id: string;
  subscription_id: string;
  churn_probability: number;
  risk_level: RiskLevel;
  scored_date: string;
}

export interface AccountsResponse {
  scored_date: string;
  total_accounts: number;
  tier_counts: Partial<Record<RiskLevel, number>>;
  previous_tier_counts: Partial<Record<RiskLevel, number>> | null;
  accounts: AccountListItem[];
}

/** Response for GET /accounts/{id}/hubspot_url */
export interface HubSpotUrlResponse {
  url: string | null;
  reason: string | null;
}
