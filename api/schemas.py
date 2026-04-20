"""
schemas.py
----------
Pydantic response models for the churn prediction API.

Pydantic does two things for us here:
  1. Validates that the data we're returning matches the shape we promised.
  2. Auto-generates the OpenAPI/Swagger docs at /docs.

SubscriptionScore is reused in both ScoreResponse and ExplainResponse.
top_factors is None in /score (not the right endpoint for it) and
populated in /explain.
"""

from typing import Optional
from pydantic import BaseModel


class FactorItem(BaseModel):
    """One SHAP feature contribution for a single account."""
    feature: str          # Human-readable label, e.g. "Support tickets submitted (count)"
    raw_feature: str      # Model column name, e.g. "total_tickets"
    shap_value: float     # How much this feature moved the probability (percentage points)
    direction: str        # "increases_risk" | "decreases_risk"


class SubscriptionScore(BaseModel):
    """Scores and optional explanation for one subscription."""
    subscription_id: str
    churn_probability: float
    risk_level: str        # "Critical" | "High" | "Medium" | "Low"
    scored_at: str         # ISO-8601 timestamp of when this was scored
    scored_date: str       # YYYY-MM-DD, the scoring day key
    top_factors: Optional[list[FactorItem]] = None  # None in /score, populated in /explain


class ScoreResponse(BaseModel):
    """Response for GET /score/{account_id}.

    Top-level fields reflect the highest-risk subscription for this account.
    subscriptions lists every subscription with its own score.
    """
    account_id: str
    churn_probability: float   # highest-risk subscription's probability
    risk_level: str
    scored_at: str
    scored_date: str
    subscriptions: list[SubscriptionScore]


class ExplainResponse(BaseModel):
    """Response for GET /explain/{account_id}.

    Top-level fields and top_factors reflect the highest-risk subscription.
    subscriptions includes per-subscription top_factors for multi-subscription accounts.
    """
    account_id: str
    churn_probability: float
    risk_level: str
    scored_at: str
    top_factors: list[FactorItem]       # highest-risk subscription's explanation
    explanation_source: str             # "precomputed" | "on_demand"
    subscriptions: list[SubscriptionScore]


class HealthCheck(BaseModel):
    """Response for GET /health."""
    status: str         # "ok" | "degraded"
    version: str
    checks: dict        # {"database": {...}, "model_file": {...}, "feature_schema": {...}}
