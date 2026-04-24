"""
main.py
-------
FastAPI service for the churn prediction system.

Endpoints:

    GET /health
        Real dependency check: DB connectivity, model file, feature schema.
        Returns {"status": "ok"|"degraded", "checks": {...}, "version": "..."}.
        The dashboard pings this on startup; Airflow can use it as a sensor.

    GET /accounts
        Top N accounts by churn risk on the latest scoring date. One row per
        account (deduped). Powers the dashboard KPI strip and accounts table.

    GET /accounts/{account_id}/hubspot_url
        Reads hubspot_company_id from the local hubspot_account_map table and
        returns a fully-formed HubSpot Company record URL. No live HubSpot API
        call — populated by scripts/sync_to_hubspot.py.

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
import os
import sys
from pathlib import Path

# Make src/ importable when uvicorn runs from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# Load .env for local dev. On Render, env vars are injected directly so
# .env won't exist — guard prevents a UnicodeDecodeError on the absent file.
if Path(".env").exists():
    load_dotenv(encoding="utf-16")

import src.data.db as db
from src.data.db import get_engine
from src.models.predict_model import MODEL_PATH, FEATURES_PATH
from api.schemas import (
    FactorItem,
    SubscriptionScore,
    ScoreResponse,
    ExplainResponse,
    HealthCheck,
    AccountListItem,
    AccountsResponse,
    HubSpotUrlResponse,
)


API_VERSION = "0.4.0"

app = FastAPI(
    title="Churn Prediction API",
    description="Score and explain churn risk for customer accounts.",
    version=API_VERSION,
)

# Allow all origins for now — tighten to the Vercel domain after deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
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
# Accounts list (used by the dashboard KPI strip + table)
# ---------------------------------------------------------------------------

@app.get("/accounts", response_model=AccountsResponse, tags=["predictions"])
def get_accounts(limit: int = Query(default=50, ge=1, le=500)):
    """Return top N accounts by churn risk on the most recent scoring date.

    One row per account (deduped with ROW_NUMBER — same logic as the HubSpot
    sync). tier_counts and previous_tier_counts cover all accounts (not just
    the top N) so the dashboard KPI strip doesn't under-count.

    previous_tier_counts comes from the second-most-recent scored_date and
    powers the 'Critical tier change' delta KPI. None when only one scoring
    run exists.
    """
    engine = get_engine()

    with engine.connect() as conn:
        # The two most-recent distinct scoring dates
        dates = conn.execute(text("""
            SELECT DISTINCT scored_date FROM churn_predictions
            ORDER BY scored_date DESC LIMIT 2
        """)).fetchall()

        if not dates:
            raise HTTPException(status_code=404, detail="No predictions found in DB.")

        latest_date = dates[0].scored_date
        prev_date = dates[1].scored_date if len(dates) > 1 else None

        # Top-N accounts: one row per account, highest-risk subscription wins,
        # subscription_id as tiebreaker so results are deterministic.
        rows = conn.execute(text("""
            WITH ranked AS (
                SELECT account_id, subscription_id, churn_probability, risk_level, scored_date,
                       ROW_NUMBER() OVER (
                           PARTITION BY account_id
                           ORDER BY churn_probability DESC, subscription_id ASC
                       ) AS rn
                FROM churn_predictions
                WHERE scored_date = :latest_date
            )
            SELECT account_id, subscription_id, churn_probability, risk_level, scored_date
            FROM ranked
            WHERE rn = 1
            ORDER BY churn_probability DESC
            LIMIT :limit
        """), {"latest_date": latest_date, "limit": limit}).fetchall()

        # Total distinct account count on the latest date (may exceed limit)
        total = conn.execute(text("""
            SELECT COUNT(DISTINCT account_id) FROM churn_predictions
            WHERE scored_date = :latest_date
        """), {"latest_date": latest_date}).scalar() or 0

        # Current tier distribution (all accounts, not just top N)
        tier_rows = conn.execute(text("""
            WITH ranked AS (
                SELECT risk_level,
                       ROW_NUMBER() OVER (
                           PARTITION BY account_id ORDER BY churn_probability DESC
                       ) AS rn
                FROM churn_predictions WHERE scored_date = :latest_date
            )
            SELECT risk_level, COUNT(*) AS cnt FROM ranked WHERE rn = 1 GROUP BY risk_level
        """), {"latest_date": latest_date}).fetchall()
        tier_counts = {r.risk_level: r.cnt for r in tier_rows}

        # Previous tier distribution for the delta KPI
        previous_tier_counts = None
        if prev_date:
            prev_rows = conn.execute(text("""
                WITH ranked AS (
                    SELECT risk_level,
                           ROW_NUMBER() OVER (
                               PARTITION BY account_id ORDER BY churn_probability DESC
                           ) AS rn
                    FROM churn_predictions WHERE scored_date = :prev_date
                )
                SELECT risk_level, COUNT(*) AS cnt FROM ranked WHERE rn = 1 GROUP BY risk_level
            """), {"prev_date": prev_date}).fetchall()
            previous_tier_counts = {r.risk_level: r.cnt for r in prev_rows}

    accounts = [
        AccountListItem(
            account_id=row.account_id,
            subscription_id=row.subscription_id,
            churn_probability=round(float(row.churn_probability), 4),
            risk_level=row.risk_level,
            scored_date=row.scored_date,
        )
        for row in rows
    ]

    return AccountsResponse(
        scored_date=latest_date,
        total_accounts=int(total),
        tier_counts=tier_counts,
        previous_tier_counts=previous_tier_counts,
        accounts=accounts,
    )


# ---------------------------------------------------------------------------
# HubSpot URL lookup
# ---------------------------------------------------------------------------

@app.get("/accounts/{account_id}/hubspot_url", response_model=HubSpotUrlResponse, tags=["predictions"])
def get_hubspot_url(account_id: str):
    """Return the HubSpot Company record URL for an account.

    Reads from hubspot_account_map — populated by scripts/sync_to_hubspot.py.
    No live HubSpot API call is made at request time.

    Returns url=None with a human-readable reason when:
      - HUBSPOT_PORTAL_ID env var is not set
      - the account hasn't been synced yet
      - the table doesn't exist (sync has never run)
    """
    portal_id = os.getenv("HUBSPOT_PORTAL_ID")
    if not portal_id:
        return HubSpotUrlResponse(url=None, reason="HUBSPOT_PORTAL_ID not configured")

    engine = get_engine()
    with engine.connect() as conn:
        try:
            row = conn.execute(
                text("SELECT hubspot_company_id FROM hubspot_account_map WHERE account_id = :aid"),
                {"aid": account_id},
            ).fetchone()
        except Exception:
            return HubSpotUrlResponse(url=None, reason="Not yet synced — run sync_to_hubspot.py first")

    if not row:
        return HubSpotUrlResponse(url=None, reason="Not yet synced to HubSpot — run sync_to_hubspot.py first")

    url = f"https://app.hubspot.com/contacts/{portal_id}/record/0-2/{row.hubspot_company_id}"
    return HubSpotUrlResponse(url=url)


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

    if top.top_factors:
        top_factors_raw = json.loads(top.top_factors)
        explanation_source = "precomputed"
    else:
        top_factors_raw = _compute_shap_on_demand(account_id, top.subscription_id)
        explanation_source = "on_demand"

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
    from src.data.load_data import load_subscriptions, load_usage, load_tickets
    from src.features.build_features import build_features
    from src.models.explain_model import compute_top_factors

    subs = load_subscriptions()
    usage = load_usage()
    tickets = load_tickets()

    X_encoded, meta = build_features(subs, usage, tickets)

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

    factors_json = top_factors_map.get(str(subscription_id))
    if factors_json is None:
        raise HTTPException(
            status_code=500,
            detail=f"SHAP computation succeeded but subscription '{subscription_id}' "
                   "was not in the result. This is a bug.",
        )

    return json.loads(factors_json)
