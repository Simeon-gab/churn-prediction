"""
write_predictions.py
--------------------
Persists scored predictions to the churn_predictions table.

Callers (score_accounts.py, future Airflow tasks) are responsible for
calling create_table_if_not_exists() once before the first write.
This module never auto-runs DDL on import — imports must be side-effect-free.

Public API:
    create_table_if_not_exists(engine)  -- idempotent DDL; call once at startup
    write_predictions(risk_table, engine) -- upserts one row per account per day

The upsert key is (subscription_id, scored_date).  Running the scorer
twice on the same day overwrites the earlier run for each account rather
than creating duplicate rows.

top_factors is left NULL here — it will be populated in Step 4 when
SHAP explanations are wired in.
"""

from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

# SQLite has no native DATE type, so scored_date is stored as TEXT (YYYY-MM-DD).
# The UNIQUE constraint on (subscription_id, scored_date) is what enforces
# "one row per account per day" and makes the upsert safe.
#
# When promoting to Postgres, replace scored_date TEXT with a generated column:
#   scored_date DATE GENERATED ALWAYS AS (scored_at::date) STORED
# and keep the UNIQUE constraint as-is.  No application code changes.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS churn_predictions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id   TEXT    NOT NULL,
    account_id        TEXT    NOT NULL,
    plan_tier         TEXT,
    seats             INTEGER,
    tenure_days       INTEGER,
    churn_probability REAL    NOT NULL,
    risk_level        TEXT    NOT NULL,
    scored_at         TEXT    NOT NULL,
    scored_date       TEXT    NOT NULL,
    top_factors       TEXT,
    UNIQUE (subscription_id, scored_date)
)
"""

# Index makes the two most common read patterns fast:
#   1. "Give me all accounts scored on date X" (dashboard load)
#   2. "Give me the latest score for account Y" (CRM sync, explain endpoint)
_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_churn_predictions_account_date
    ON churn_predictions (account_id, scored_date)
"""


def create_table_if_not_exists(engine: Engine) -> None:
    """Create the churn_predictions table and index if they don't exist.

    Idempotent — safe to call every time the scoring job starts.
    Intentionally NOT called on module import; the caller decides when
    to run DDL.
    """
    with engine.begin() as conn:
        conn.execute(text(_CREATE_TABLE_SQL))
        conn.execute(text(_CREATE_INDEX_SQL))


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

# The upsert runs as a single SQL statement per row using executemany.
# ON CONFLICT targets the unique key; every mutable column is refreshed
# so a same-day re-run produces exactly the same final state.
_UPSERT_SQL = """
INSERT INTO churn_predictions (
    subscription_id,
    account_id,
    plan_tier,
    seats,
    tenure_days,
    churn_probability,
    risk_level,
    scored_at,
    scored_date,
    top_factors
) VALUES (
    :subscription_id,
    :account_id,
    :plan_tier,
    :seats,
    :tenure_days,
    :churn_probability,
    :risk_level,
    :scored_at,
    :scored_date,
    :top_factors
)
ON CONFLICT (subscription_id, scored_date) DO UPDATE SET
    account_id        = excluded.account_id,
    plan_tier         = excluded.plan_tier,
    seats             = excluded.seats,
    tenure_days       = excluded.tenure_days,
    churn_probability = excluded.churn_probability,
    risk_level        = excluded.risk_level,
    scored_at         = excluded.scored_at,
    top_factors       = excluded.top_factors
"""


def write_predictions(risk_table: pd.DataFrame, engine: Engine) -> int:
    """Upsert a scored DataFrame into churn_predictions.

    Parameters
    ----------
    risk_table : pd.DataFrame
        Output of score_accounts() — must contain columns:
        subscription_id, account_id, plan_tier, seats, tenure_days,
        churn_probability, risk_level.

    engine : Engine
        SQLAlchemy engine from get_engine() or any compatible engine.

    Returns
    -------
    int
        Number of rows upserted.

    Each row gets a scored_at timestamp (UTC, ISO-8601) and a scored_date
    (YYYY-MM-DD) derived from it.  Both are set once here so all rows in
    a single batch share the exact same timestamp — consistent and easy
    to query by run date.
    """
    # One timestamp for the whole batch so every row in this run is
    # queryable as a single scoring event.
    now_utc: datetime = datetime.now(timezone.utc)
    scored_at: str = now_utc.isoformat()          # e.g. "2026-04-20T03:00:10+00:00"
    scored_date: str = now_utc.date().isoformat()  # e.g. "2026-04-20"

    # Build a list of plain dicts — SQLAlchemy's executemany expects this.
    # None becomes SQL NULL for top_factors (populated in Step 4).
    rows = [
        {
            "subscription_id":   row["subscription_id"],
            "account_id":        row["account_id"],
            "plan_tier":         row.get("plan_tier"),
            "seats":             row.get("seats"),
            "tenure_days":       row.get("tenure_days"),
            "churn_probability": float(row["churn_probability"]),
            "risk_level":        row["risk_level"],
            "scored_at":         scored_at,
            "scored_date":       scored_date,
            "top_factors":       None,
        }
        for _, row in risk_table.iterrows()
    ]

    with engine.begin() as conn:
        # executemany sends all rows in one round-trip.
        conn.execute(text(_UPSERT_SQL), rows)

    return len(rows)
