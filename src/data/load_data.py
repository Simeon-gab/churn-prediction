"""
load_data.py
------------
Reads the three raw CSVs (subscriptions, feature usage, support tickets)
from data/raw/ and returns them as pandas DataFrames.

Every other module (features, training, scoring) starts here — this is
the one place that knows about filesystem paths for raw data.
"""

import pandas as pd


# Paths are relative to the project root (churn_prediction/)
# so scripts should be run from there, e.g.:
#   cd churn_prediction
#   python scripts/score_accounts.py
SUBSCRIPTIONS_PATH = "data/raw/ravenstack_subscriptions.csv"
USAGE_PATH = "data/raw/ravenstack_feature_usage.csv"
TICKETS_PATH = "data/raw/ravenstack_support_tickets.csv"


def load_subscriptions(path: str = SUBSCRIPTIONS_PATH) -> pd.DataFrame:
    """Load the subscriptions table. One row per subscription."""
    return pd.read_csv(path)


def load_usage(path: str = USAGE_PATH) -> pd.DataFrame:
    """Load the feature usage events. Many rows per subscription."""
    usage = pd.read_csv(path)
    usage["usage_date"] = pd.to_datetime(usage["usage_date"], dayfirst=True)
    return usage


def load_tickets(path: str = TICKETS_PATH) -> pd.DataFrame:
    """Load the support tickets. Many rows per account."""
    tickets = pd.read_csv(path)
    tickets["submitted_at"] = pd.to_datetime(tickets["submitted_at"], dayfirst=True)
    tickets["closed_at"] = pd.to_datetime(tickets["closed_at"], dayfirst=True)
    return tickets
