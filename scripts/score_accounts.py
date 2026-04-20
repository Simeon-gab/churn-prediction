"""
score_accounts.py
-----------------
The nightly batch scoring job. Airflow will call this once per day.

It does exactly what Steps 1–9 at the bottom of the old monolithic
script did, but now it's just glue code — all the heavy lifting
lives in the src/ modules it imports.

Run manually:
    cd churn_prediction
    python scripts/score_accounts.py

Outputs two CSVs to data/processed/:
    churn_risk_predictions.csv      — all customers, sorted by risk
    high_medium_risk_customers.csv  — the CSM target list
"""

import sys
from pathlib import Path

# Make `src` importable when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.data.load_data import load_subscriptions, load_usage, load_tickets
from src.features.build_features import build_features
from src.models.predict_model import predict_churn_risk


OUTPUT_DIR = Path("data/processed")
FULL_PREDICTIONS_PATH = OUTPUT_DIR / "churn_risk_predictions.csv"
ACTION_LIST_PATH = OUTPUT_DIR / "high_medium_risk_customers.csv"


def score_accounts() -> pd.DataFrame:
    """Load, feature-engineer, score, segment, save."""

    # --- Load ---
    print("Loading raw data...")
    subs = load_subscriptions()
    usage = load_usage()
    tickets = load_tickets()

    # --- Features ---
    print("Building features...")
    X_encoded, meta = build_features(subs, usage, tickets)

    # --- Predict ---
    print(f"Scoring {len(X_encoded)} accounts...")
    predictions = predict_churn_risk(X_encoded)

    # --- Stitch meta + predictions back together ---
    risk_table = pd.concat([meta, predictions], axis=1)
    risk_table = risk_table.sort_values("churn_probability", ascending=False)

    # Keep only the columns CSMs care about for the business table
    business_cols = [
        "subscription_id",
        "account_id",
        "plan_tier",
        "seats",
        "tenure_days",
        "churn_probability",
        "risk_level",
    ]
    risk_table = risk_table[business_cols]

    # --- Save full table ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    risk_table.to_csv(FULL_PREDICTIONS_PATH, index=False)
    print(f"\nFull predictions saved: {FULL_PREDICTIONS_PATH}")

    # --- CSM action list: Medium, High, Critical only ---
    action_customers = risk_table[
        risk_table["risk_level"].isin(["Medium", "High", "Critical"])
    ].sort_values("churn_probability", ascending=False)

    action_customers.to_csv(ACTION_LIST_PATH, index=False)
    print(f"CSM action list saved:  {ACTION_LIST_PATH}")

    # --- Summary ---
    print("\nRisk tier breakdown:")
    print(risk_table["risk_level"].value_counts().to_string())

    print("\nTop 10 highest-risk customers:")
    print(risk_table.head(10).to_string(index=False))

    return risk_table


if __name__ == "__main__":
    score_accounts()
    print("\nChurn prediction pipeline completed successfully.")
