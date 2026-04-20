"""
build_features.py
-----------------
Turns the three raw tables into the feature matrix X the model expects.

Pipeline:
    1. Aggregate feature usage per subscription
    2. Aggregate support tickets per account
    3. Merge everything into one wide table (subs_full)
    4. Fill NaNs from left-joins with 0
    5. Parse dates and compute tenure_days
    6. Add the 4 engineered features:
         revenue_per_seat, usage_per_seat, error_rate, usage_per_day
    7. Drop ID / date / target columns
    8. One-hot encode categoricals

The main entry point is build_features(subs, usage, tickets).
It returns two things:
    X_encoded   — the model-ready feature matrix
    meta        — the dropped ID columns (subscription_id, account_id, etc.)
                  kept separately so scoring scripts can attach
                  probabilities back to customers.
"""

import pandas as pd


# Columns we fill with 0 after the left-joins
# (if a subscription has no usage rows, its usage stats should be 0, not NaN)
USAGE_FILL_COLS = [
    "total_usage_count",
    "total_usage_duration",
    "avg_usage_duration",
    "total_errors",
    "beta_feature_usage_rate",
    "unique_features_used",
]

TICKET_FILL_COLS = [
    "total_tickets",
    "avg_resolution_time",
    "avg_first_response_time",
    "avg_satisfaction_score",
    "escalation_rate",
]

# Columns we drop before training/scoring (IDs, dates, target)
DROP_COLS = [
    "subscription_id",
    "account_id",
    "start_date",
    "end_date",
    "churn_flag",
]


def _aggregate_usage(usage: pd.DataFrame) -> pd.DataFrame:
    """Collapse many usage rows per subscription into one summary row."""
    return (
        usage.groupby("subscription_id")
        .agg(
            total_usage_count=("usage_count", "sum"),
            total_usage_duration=("usage_duration_secs", "sum"),
            avg_usage_duration=("usage_duration_secs", "mean"),
            total_errors=("error_count", "sum"),
            beta_feature_usage_rate=("is_beta_feature", "mean"),
            unique_features_used=("feature_name", "nunique"),
        )
        .reset_index()
    )


def _aggregate_tickets(tickets: pd.DataFrame) -> pd.DataFrame:
    """Collapse many ticket rows per account into one summary row."""
    return (
        tickets.groupby("account_id")
        .agg(
            total_tickets=("ticket_id", "count"),
            avg_resolution_time=("resolution_time_hours", "mean"),
            avg_first_response_time=("first_response_time_minutes", "mean"),
            avg_satisfaction_score=("satisfaction_score", "mean"),
            escalation_rate=("escalation_flag", "mean"),
        )
        .reset_index()
    )


def _add_tenure(subs_full: pd.DataFrame) -> pd.DataFrame:
    """Compute tenure_days = days between start_date and end_date.

    For active customers (end_date is NaN), we use the max observed
    end_date in the dataset as a reference snapshot date.
    """
    subs_full["start_date"] = pd.to_datetime(subs_full["start_date"], dayfirst=True)
    subs_full["end_date"] = pd.to_datetime(subs_full["end_date"], dayfirst=True)

    reference_date = subs_full["end_date"].max()
    subs_full["tenure_days"] = (
        subs_full["end_date"].fillna(reference_date) - subs_full["start_date"]
    ).dt.days
    return subs_full


def _add_engineered_features(subs_full: pd.DataFrame) -> pd.DataFrame:
    """The 4 engineered features that capture 'intensity' per customer."""
    # Revenue efficiency — how much each seat is worth
    subs_full["revenue_per_seat"] = subs_full["mrr_amount"] / subs_full["seats"]

    # Adoption depth — how much each seat actually uses the product
    subs_full["usage_per_seat"] = subs_full["total_usage_count"] / subs_full["seats"]

    # Product friction — errors as a fraction of usage (+1 to avoid div by zero)
    subs_full["error_rate"] = subs_full["total_errors"] / (subs_full["total_usage_count"] + 1)

    # Engagement intensity — usage normalized by account age
    subs_full["usage_per_day"] = subs_full["total_usage_count"] / (subs_full["tenure_days"] + 1)

    return subs_full


def build_features(
    subs: pd.DataFrame,
    usage: pd.DataFrame,
    tickets: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Turn raw tables into a model-ready feature matrix.

    Parameters
    ----------
    subs    : subscriptions dataframe
    usage   : feature usage events dataframe
    tickets : support tickets dataframe

    Returns
    -------
    X_encoded : pd.DataFrame
        One-hot encoded feature matrix ready for model.predict().
    meta : pd.DataFrame
        subscription_id, account_id, plan_tier, seats, tenure_days,
        and churn_flag (if present). Index-aligned with X_encoded so
        scoring scripts can attach probabilities back to customers.
    """
    # Step 1 & 2 — aggregate the child tables
    usage_agg = _aggregate_usage(usage)
    tickets_agg = _aggregate_tickets(tickets)

    # Step 3 — merge everything into one wide table
    subs_full = subs.merge(usage_agg, on="subscription_id", how="left")
    subs_full = subs_full.merge(tickets_agg, on="account_id", how="left")

    # Step 4 — fill NaNs from the left-joins
    subs_full[USAGE_FILL_COLS] = subs_full[USAGE_FILL_COLS].fillna(0)
    subs_full[TICKET_FILL_COLS] = subs_full[TICKET_FILL_COLS].fillna(0)

    # Step 5 — tenure_days (needs dates parsed)
    subs_full = _add_tenure(subs_full)

    # Step 6 — engineered features
    subs_full = _add_engineered_features(subs_full)

    # Step 7 — preserve meta columns, then drop before encoding
    meta_cols = ["subscription_id", "account_id", "plan_tier", "seats", "tenure_days"]
    if "churn_flag" in subs_full.columns:
        meta_cols = meta_cols + ["churn_flag"]
    meta = subs_full[meta_cols].copy()

    existing_drops = [c for c in DROP_COLS if c in subs_full.columns]
    X = subs_full.drop(existing_drops, axis=1)

    # Step 8 — one-hot encode categoricals
    X_encoded = pd.get_dummies(X, drop_first=True)

    return X_encoded, meta
