"""
explain_model.py
----------------
SHAP-based explainability for the churn model.

SHAP (SHapley Additive exPlanations) answers the question:
"How much did each feature push this account's score up or down?"

The value of 0.14 for total_tickets means:
"The number of support tickets this account submitted moved their churn
probability 14 percentage points higher than the model's baseline."
That's the number a CSM can act on.

Public API:
    compute_top_factors(X_encoded, meta) -> dict[subscription_id -> JSON str]

Used by:
    scripts/score_accounts.py  -- batch precompute at scoring time
    api/main.py                -- on-demand fallback for NULL top_factors
"""

import json
from functools import lru_cache

import numpy as np
import pandas as pd
import shap

from src.models.predict_model import _load_model, _load_feature_columns


# How many top features to surface per account.
# 5 is enough for a CSM to act on; more creates noise.
TOP_N = 5


# Human-readable labels for every feature the model knows about.
# Units are included so CSMs can anchor the numbers mentally --
# "14 support tickets" means more than "total_tickets = 14".
# 26 entries, one per column in feature_columns.json.
FEATURE_LABELS: dict[str, str] = {
    # --- Subscription shape ---
    "seats":                     "Number of seats (count)",
    "mrr_amount":                "Monthly recurring revenue (USD)",
    "arr_amount":                "Annual recurring revenue (USD)",
    "tenure_days":               "Days as a customer (days)",

    # --- Subscription state flags (1 = yes, 0 = no) ---
    "is_trial":                  "Account is on a free trial (1 = yes)",
    "upgrade_flag":              "Recent plan upgrade (1 = yes)",
    "downgrade_flag":            "Recent plan downgrade (1 = yes)",
    "auto_renew_flag":           "Auto-renewal is enabled (1 = yes)",

    # --- Product usage ---
    "total_usage_count":         "Total product usage events (count)",
    "total_usage_duration":      "Total time in product (seconds)",
    "avg_usage_duration":        "Average session length (seconds per session)",
    "total_errors":              "Total errors encountered (count)",
    "beta_feature_usage_rate":   "Beta feature adoption rate (0-1 proportion)",
    "unique_features_used":      "Distinct product features used (count)",

    # --- Support tickets ---
    "total_tickets":             "Support tickets submitted (count)",
    "avg_resolution_time":       "Average ticket resolution time (hours)",
    "avg_first_response_time":   "Average first response time (minutes)",
    "avg_satisfaction_score":    "Average support satisfaction score (1–5 scale)",
    "escalation_rate":           "Ticket escalation rate (0-1 proportion)",

    # --- Engineered intensity features ---
    "revenue_per_seat":          "Revenue per seat (USD per seat)",
    "usage_per_seat":            "Product usage per seat (events per seat)",
    "error_rate":                "Error rate (errors per usage event)",
    "usage_per_day":             "Product usage frequency (events per day)",

    # --- Plan tier one-hot (baseline category dropped by get_dummies) ---
    "plan_tier_Enterprise":      "Account is on Enterprise plan (1 = yes)",
    "plan_tier_Pro":             "Account is on Pro plan (1 = yes)",

    # --- Billing frequency one-hot ---
    "billing_frequency_monthly": "Billed monthly rather than annually (1 = yes)",
}


@lru_cache(maxsize=1)
def get_explainer() -> shap.TreeExplainer:
    """Return a cached SHAP TreeExplainer built from the trained RF model.

    tree_path_dependent is the right perturbation strategy for tree models.
    It uses the tree structure itself to model feature interactions, rather
    than needing a separate background dataset to estimate them.
    Only ever built once per process (lru_cache), same as the model itself.
    """
    model = _load_model()
    return shap.TreeExplainer(model, feature_perturbation="tree_path_dependent")


def _extract_top_factors(shap_row: np.ndarray, feature_names: list[str]) -> list[dict]:
    """Build a top-N factor list for one account from its SHAP value row.

    Each item says: "This feature moved the score X points in this direction."
    We sort by absolute value so the most influential features come first
    regardless of whether they increase or decrease churn risk.
    """
    pairs = list(zip(feature_names, shap_row))
    # Sort by absolute SHAP value descending -- biggest movers first
    pairs.sort(key=lambda x: abs(x[1]), reverse=True)

    return [
        {
            "feature":     FEATURE_LABELS.get(name, name),  # raw name as fallback for unknown features
            "raw_feature": name,
            "shap_value":  round(float(val), 4),
            "direction":   "increases_risk" if val > 0 else "decreases_risk",
        }
        for name, val in pairs[:TOP_N]
    ]


def compute_top_factors(
    X_encoded: pd.DataFrame,
    meta: pd.DataFrame,
) -> dict[str, str]:
    """Compute SHAP top-5 factors for a batch of accounts.

    Runs SHAP on the full feature matrix in one vectorized pass --
    much faster than row-by-row because all 400 trees are traversed once.

    Parameters
    ----------
    X_encoded : pd.DataFrame
        Feature matrix output of build_features(). Can be the full 5000-row
        batch or a filtered subset (e.g., one account for on-demand path).
        Will be reindexed to match the model's training columns internally.
    meta : pd.DataFrame
        Index-aligned with X_encoded. Must contain a subscription_id column.

    Returns
    -------
    dict[str, str]
        Maps subscription_id -> JSON string of top-5 factor list.
        JSON is pre-serialized so it can be inserted directly into the
        top_factors TEXT column without an extra json.dumps() at the call site.
    """
    feature_names: list[str] = _load_feature_columns()
    explainer = get_explainer()

    # Reindex to match training columns exactly.
    # If a category (e.g., plan_tier_Enterprise) is absent from this batch,
    # fill_value=0 gives it the "not Enterprise" encoding -- correct behavior.
    X_aligned = X_encoded.reindex(columns=feature_names, fill_value=0)

    # shap_values() on a binary RandomForestClassifier returns a list of two
    # arrays: [class_0_values, class_1_values], each shape (n_samples, n_features).
    # Newer SHAP versions may return a 3D array (n_samples, n_features, n_classes).
    # We handle both.
    raw = explainer.shap_values(X_aligned)
    if isinstance(raw, list):
        # Legacy API: list[class_0_array, class_1_array]
        churn_shap: np.ndarray = raw[1]
    else:
        # New API: 3D array (n_samples, n_features, n_classes)
        churn_shap = raw[:, :, 1]

    result: dict[str, str] = {}
    for i, sub_id in enumerate(meta["subscription_id"].values):
        factors = _extract_top_factors(churn_shap[i], feature_names)
        result[str(sub_id)] = json.dumps(factors)

    return result
