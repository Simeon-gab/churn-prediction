"""
predict_model.py
----------------
The single interface every downstream system uses to get churn scores.

Airflow DAG, FastAPI /score endpoint, the Next.js dashboard API route,
the CRM sync job — they all import from here. Training lives elsewhere
(train_model.py); this module only loads the saved model and scores.

The model is loaded lazily once per process (cached) — so re-scoring
10,000 customers doesn't reload the 28MB .pkl from disk every time.

Main functions:
    predict_churn_risk(features)   -> DataFrame with churn_probability + risk_level
    risk_level(probability)        -> str: one of "Critical" / "High" / "Medium" / "Low"
"""

import json
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd


MODEL_PATH = Path("data/models/churn_model.pkl")
FEATURES_PATH = Path("data/models/feature_columns.json")


# Risk tier thresholds — matches what Customer Success agreed on.
# If you want to tune these, change them here. Every consumer picks it up.
CRITICAL_THRESHOLD = 0.40
HIGH_THRESHOLD = 0.30
MEDIUM_THRESHOLD = 0.20


def risk_level(probability: float) -> str:
    """Map a raw probability to a CS-facing risk tier."""
    if probability >= CRITICAL_THRESHOLD:
        return "Critical"     # immediate action — CSM outreach today
    elif probability >= HIGH_THRESHOLD:
        return "High"         # outreach this week
    elif probability >= MEDIUM_THRESHOLD:
        return "Medium"       # monitor and engage
    else:
        return "Low"          # no action needed


@lru_cache(maxsize=1)
def _load_model():
    """Load the trained model from disk. Cached for the process lifetime."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"No model found at {MODEL_PATH}. "
            "Run `python -m src.models.train_model` first."
        )
    return joblib.load(MODEL_PATH)


@lru_cache(maxsize=1)
def _load_feature_columns() -> list[str]:
    """Load the feature schema the model was trained on."""
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"No feature schema at {FEATURES_PATH}. "
            "Retrain the model so the schema is saved alongside it."
        )
    with open(FEATURES_PATH) as f:
        return json.load(f)


def predict_churn_risk(features: pd.DataFrame) -> pd.DataFrame:
    """Score a batch of customers.

    Parameters
    ----------
    features : pd.DataFrame
        Already-encoded feature matrix (output of build_features()).

    Returns
    -------
    pd.DataFrame
        Columns: churn_probability (float), risk_level (str).
        Index is aligned with the input features, so you can concat
        it back onto a meta dataframe that has subscription_id etc.
    """
    model = _load_model()
    expected_cols = _load_feature_columns()

    # Align columns — if training had e.g. plan_tier_Enterprise and this
    # batch is missing that category, reindex fills it with 0.
    features_aligned = features.reindex(columns=expected_cols, fill_value=0)

    probabilities = model.predict_proba(features_aligned)[:, 1]
    risk_levels = [risk_level(p) for p in probabilities]

    return pd.DataFrame(
        {
            "churn_probability": probabilities,
            "risk_level": risk_levels,
        },
        index=features.index,
    )
