"""
main.py
-------
FastAPI service for the churn prediction system.

Three endpoints:

    GET /health
        Real dependency check: DB connectivity, model file, feature schema.
        Returns {"status": "ok"|"degraded", "checks": {...}, "version": "..."}.
        The dashboard pings this on startup; Airflow can use it as a sensor.

    GET /score/{account_id}
        Latest churn score from the DB. Fast — no model inference at request time.
        Returns account-level summary (highest-risk subscription) + all subscriptions.

    GET /explain/{account_id}
        SHAP top-5 factors for the account.
        Fast path: reads precomputed top_factors JSON from the DB (written nightly).
        Fallback: loads CSVs and runs SHAP on-demand if top_factors is NULL.
        explanation_source field tells you which path was taken.

Run locally:
    cd churn_prediction
    uvicorn api.main:app --reload

Swagger UI: http://127.0.0.1:8000/docs
"""

import json
import sys
from pathlib import Path

# Make src/ importable when uvicorn runs from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

import src.data.db as db
from src.data.db import get_engine
from src.models.predict_model import MODEL_PATH, FEATURES_PATH
from api.schemas import (
    FactorItem,
    SubscriptionScore,
    ScoreResponse,
    ExplainResponse,
    HealthCheck,
)


API_VERSION = "0.4.0"

app = FastAPI(
    title="Churn Prediction API",
    description="Score and explain churn risk for customer accounts.",
    version=API_VERSION,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthCheck, tags=["ops"])
def health():
    """Check API dependencies.

    Returns status "ok" only if all three checks pass:
      - database: can we open a connection and run SELECT 1?
      - model_file: does churn_model.pkl exist on disk?
      - feature_schema: does feature_columns.json exist and parse cleanly?

    Returns "degraded" if any check fails, with per-check detail so you
    know exactly what's broken without having to SSH into the box.
    """
    checks: dict[str, dict] = {}

    # --- Check 1: database ---
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "detail": db.DATABASE_URL,
        }
    except Exception as exc:
        checks["database"] = {
            "status": "error",
            "detail": str(exc),
        }

    # --- Check 2: model file ---
    if MODEL_PATH.exists():
        checks["model_file"] = {
            "status": "ok",
            "detail": str(MODEL_PATH),
        }
    else:
        checks["model_file"] = {
            "status": "error",
            "detail": f"Not found: {MODEL_PATH}. Run python -m src.models.train_model first.",
        }

    # --- Check 3: feature schema ---
    if FEATURES_PATH.exists():
        try:
            with open(FEATURES_PATH) as f:
                features = json.load(f)
            checks["feature_schema"] = {
                "status": "ok",
                "detail": f"{FEATURES_PATH} ({len(features)} features)",
            }
        except Exception as exc:
            checks["feature_schema"] = {
                "status": "error",
                "detail": f"File exists but could not parse: {exc}",
            }
    else:
        checks["feature_schema"] = {
            "status": "error",
            "detail": f"Not found: {FEATURES_PATH}. Retrain the model first.",
        }

    overall = "ok" if all(c["status"] == "ok" for c in checks.values()) else "degraded"

    return HealthCheck(status=overall, version=API_VERSION, checks=checks)


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

@app.get("/score/{account_id}", response_model=ScoreResponse, tags=["predictions"])
def get_score(account_id: str):
    """Return the latest churn score for an account.

    Reads from the churn_predictions table — no model inference happens
    at request time. The score reflects the most recent nightly batch run.

    If an account has multiple subscriptions (uncommon), the top-level
    fields reflect the highest-risk subscription, and all subscriptions
    are listed in the subscriptions array.
    """
    engine = get_engine()

    with engine.connect() as conn:
        # Get all subscriptions for this account on their most recent scored_date.
        # Subquery finds the latest date; outer query fetches all subscriptions on that day.
        # Sorted by churn_probability DESC so row 0 is always the highest-risk subscription.
        rows = conn.execute(
            text("""
                SELECT subscription_id, account_id, churn_probability, risk_level,
                       scored_at, scored_date
                FROM churn_predictions
                WHERE account_id = :account_id
                  AND scored_date = (
                      SELECT MAX(scored_date)
                      FROM churn_predictions
                      WHERE account_id = :account_id
                  )
                ORDER BY churn_probability DESC
            """),
            {"account_id": account_id},
        ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No predictions found for account '{account_id}'. "
                   "Verify the account ID or run the nightly scorer first.",
        )

    # Row 0 = highest-risk subscription (drives the account-level summary)
    top = rows[0]

    return ScoreResponse(
        account_id=account_id,
        churn_probability=round(float(top.churn_probability), 4),
        risk_level=top.risk_level,
        scored_at=top.scored_at,
        scored_date=top.scored_date,
        subscriptions=[
            SubscriptionScore(
                subscription_id=row.subscription_id,
                churn_probability=round(float(row.churn_probability), 4),
                risk_level=row.risk_level,
                scored_at=row.scored_at,
                scored_date=row.scored_date,
                # top_factors is not included in /score — use /explain for that
                top_factors=None,
            )
            for row in rows
        ],
    )


# ---------------------------------------------------------------------------
# Explain
# ---------------------------------------------------------------------------

@app.get("/explain/{account_id}", response_model=ExplainResponse, tags=["predictions"])
def get_explain(account_id: str):
    """Return the churn score + SHAP top-5 explanation for an account.

    Fast path (explanation_source = "precomputed"):
        Reads top_factors JSON from the DB. Written during the nightly batch run.
        Response time ~5ms.

    Fallback path (explanation_source = "on_demand"):
        top_factors was NULL — account was scored before Step 4 was deployed,
        or the batch hasn't run since deployment.
        Loads raw CSVs, rebuilds features, runs SHAP TreeExplainer.
        Response time ~500ms–1s.

    The subscriptions array includes per-subscription top_factors so the
    dashboard can render explanation cards for each subscription without
    additional round-trips.
    """
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT subscription_id, account_id, churn_probability, risk_level,
                       scored_at, scored_date, top_factors
                FROM churn_predictions
                WHERE account_id = :account_id
                  AND scored_date = (
                      SELECT MAX(scored_date)
                      FROM churn_predictions
                      WHERE account_id = :account_id
                  )
                ORDER BY churn_probability DESC
            """),
            {"account_id": account_id},
        ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No predictions found for account '{account_id}'.",
        )

    top = rows[0]

    # --- Determine top_factors for the highest-risk subscription ---
    if top.top_factors:
        # Fast path: precomputed factors already in the DB
        top_factors_raw = json.loads(top.top_factors)
        explanation_source = "precomputed"
    else:
        # Fallback: run SHAP on-demand
        top_factors_raw = _compute_shap_on_demand(account_id, top.subscription_id)
        explanation_source = "on_demand"

    # Parse every subscription's top_factors for the subscriptions array.
    # Subscriptions without precomputed factors get None (on-demand is only
    # triggered for the highest-risk subscription above).
    def _parse_factors(raw: str | None) -> list[FactorItem] | None:
        if not raw:
            return None
        return [FactorItem(**item) for item in json.loads(raw)]

    return ExplainResponse(
        account_id=account_id,
        churn_probability=round(float(top.churn_probability), 4),
        risk_level=top.risk_level,
        scored_at=top.scored_at,
        top_factors=[FactorItem(**item) for item in top_factors_raw],
        explanation_source=explanation_source,
        subscriptions=[
            SubscriptionScore(
                subscription_id=row.subscription_id,
                churn_probability=round(float(row.churn_probability), 4),
                risk_level=row.risk_level,
                scored_at=row.scored_at,
                scored_date=row.scored_date,
                top_factors=_parse_factors(row.top_factors),
            )
            for row in rows
        ],
    )


def _compute_shap_on_demand(account_id: str, subscription_id: str) -> list[dict]:
    """On-demand SHAP fallback — only called when top_factors is NULL in the DB.

    Loads all three raw CSVs, rebuilds the full feature matrix, filters to
    this account, and runs SHAP TreeExplainer.

    We must load the full dataset (not just this account's rows) because
    build_features() computes tenure_days using:
        reference_date = subs_full["end_date"].max()
    Slicing to one account first would give wrong tenure_days for active
    customers whose end_date is NaN.
    """
    # Local imports keep the module-level namespace clean and make it obvious
    # that this is the slow, CSV-loading path.
    from src.data.load_data import load_subscriptions, load_usage, load_tickets
    from src.features.build_features import build_features
    from src.models.explain_model import compute_top_factors

    subs = load_subscriptions()
    usage = load_usage()
    tickets = load_tickets()

    X_encoded, meta = build_features(subs, usage, tickets)

    # Filter to just this account's rows for SHAP
    mask = meta["account_id"] == account_id
    X_account = X_encoded[mask]
    meta_account = meta[mask]

    if X_account.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_id}' found in DB but not in source CSVs. "
                   "Data may be out of sync.",
        )

    top_factors_map = compute_top_factors(X_account, meta_account)

    # Return factors for the specific subscription_id we need
    factors_json = top_factors_map.get(str(subscription_id))
    if factors_json is None:
        raise HTTPException(
            status_code=500,
            detail=f"SHAP computation succeeded but subscription '{subscription_id}' "
                   "was not in the result. This is a bug.",
        )

    return json.loads(factors_json)
