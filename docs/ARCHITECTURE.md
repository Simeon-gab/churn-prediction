# Architecture

How the pieces fit together. Read this after `PROJECT_OVERVIEW.md`.

## The score → surface → act → learn loop

Every churn system that actually changes behavior follows the same
four-phase loop:

```
  [SCORE]    →    [SURFACE]    →    [ACT]    →    [LEARN]
     ↑                                                │
     └────────────────────────────────────────────────┘
              (retraining with new outcomes)
```

- **Score:** the model computes a churn probability for every account
- **Surface:** the score shows up where CSMs work (dashboard + CRM)
- **Act:** CSMs intervene (calls, discounts, training sessions)
- **Learn:** outcomes feed back into the next model retrain

Most failed churn projects stop at Score and never close the loop.
This architecture is designed so closing the loop is the default path,
not an afterthought.

## High-level component diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         RAW DATA SOURCES                         │
│   ravenstack_subscriptions.csv  ·  feature_usage.csv  ·          │
│   support_tickets.csv                                            │
│   (future: warehouse tables — Snowflake / BigQuery / Redshift)  │
└────────────────────┬─────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FEATURE ENGINEERING                           │
│                                                                  │
│   src/data/load_data.py        ← reads the 3 CSVs                │
│   src/features/build_features.py ← merges, aggregates, encodes   │
│                                                                  │
│   Output: X_encoded (model-ready) + meta (IDs for join-back)     │
└────────────────────┬─────────────────────────────────────────────┘
                     │
           ┌─────────┴─────────┐
           ▼                   ▼
┌──────────────────┐  ┌──────────────────────────────────────────┐
│   TRAINING       │  │           INFERENCE                      │
│                  │  │                                          │
│ src/models/      │  │  src/models/predict_model.py             │
│ train_model.py   │  │   predict_churn_risk(features)           │
│                  │  │   → DataFrame with churn_probability     │
│ Runs: manually,  │  │     and risk_level                       │
│ when retraining  │  │                                          │
│                  │  │  Loads: data/models/churn_model.pkl      │
│ Output:          │  │         data/models/feature_columns.json │
│  churn_model.pkl │  │                                          │
│  feature_columns │  │  Called by: Airflow DAG, FastAPI,        │
│  .json           │  │             dashboard, CRM sync          │
└──────────────────┘  └──────────────────────┬───────────────────┘
                                             │
                                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION (Step 2)                        │
│                                                                  │
│   dags/churn_scoring_dag.py — runs scripts/score_accounts.py    │
│   every night at 3am. Airflow handles retries, logging, alerts. │
└────────────────────┬─────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                 PREDICTIONS STORE (Step 3)                       │
│                                                                  │
│   Postgres table: churn_predictions                              │
│   (account_id, subscription_id, churn_probability, risk_level,   │
│    scored_at, top_factors)                                       │
│                                                                  │
│   Acts as the single source of truth. Every downstream system   │
│   reads from here, never from the model directly.               │
└────────────────────┬─────────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬────────────────┐
        ▼            ▼            ▼                ▼
┌──────────────┐ ┌─────────┐ ┌──────────┐ ┌────────────────┐
│ FASTAPI      │ │ CRM     │ │ DASHBOARD│ │ SLACK ALERTS   │
│ (Step 4)     │ │ SYNC    │ │(Step 6)  │ │ (v2)           │
│              │ │(Step 5) │ │          │ │                │
│ /score       │ │         │ │ Next.js  │ │ Triggered when │
│ /explain     │ │ HubSpot │ │ Recharts │ │ account moves  │
│ (SHAP)       │ │ or SF   │ │          │ │ to Critical    │
└──────────────┘ └─────────┘ └──────────┘ └────────────────┘
```

## Data flow — a single prediction, step by step

Walkthrough for one account, end to end:

1. **3:00am** — Airflow scheduler fires the `churn_scoring_dag`
2. **3:00:05** — DAG task `load_and_score` runs `score_accounts.py`
3. **3:00:06** — `load_data.py` reads the 3 CSVs (later: warehouse tables)
4. **3:00:08** — `build_features.py` merges them, adds the 4 engineered
   features, one-hot encodes. Output: 5000 rows × ~26 columns.
5. **3:00:09** — `predict_model.py` loads the pickled RF + feature schema.
   Reindexes the input to match training columns (fills missing with 0).
6. **3:00:10** — `model.predict_proba()` returns 5000 probabilities.
7. **3:00:10** — `risk_level()` maps each probability to Low/Medium/High/Critical.
8. **3:00:11** — Results are concatenated with the meta frame
   (subscription_id, account_id, plan_tier, seats, tenure_days).
9. **3:00:12** — DAG task `write_to_postgres` upserts into the
   `churn_predictions` table (Step 3).
10. **3:00:13** — DAG task `sync_to_crm` fires for high/critical only,
    updating Account records in HubSpot/Salesforce (Step 5).
11. **7:00am** — CSMs open the dashboard. Dashboard API calls
    `/predictions?risk_tier=critical&sort=arr_desc` → reads from Postgres.
12. **9:00am** — CSM clicks into Account A-c43359, dashboard calls
    `/explain/A-c43359` → FastAPI runs SHAP TreeExplainer on that row,
    returns the top 5 features driving the 0.78 score with plain-English
    descriptions.
13. **10:30am** — CSM calls the customer, logs outcome in CRM.
14. **28 days later** — `churn_flag` updates in the warehouse. Retraining
    DAG picks up the new labels. Model improves. Loop closes.

## Where each file fits

| File / folder | Role |
|---|---|
| `src/data/load_data.py` | Source-of-truth for reading raw inputs. Only file that knows filesystem paths for CSVs. |
| `src/features/build_features.py` | All feature logic. Used by both training and scoring — prevents training-serving skew. |
| `src/models/train_model.py` | Run manually. Produces `churn_model.pkl` + `feature_columns.json`. |
| `src/models/predict_model.py` | The `predict_churn_risk(features)` function. Imported by every downstream system. Caches the loaded model. |
| `scripts/score_accounts.py` | Glue: load → features → predict → save. The batch job. |
| `dags/churn_scoring_dag.py` | Airflow wrapper around `score_accounts.py`. Schedules, retries, alerts. (Step 2) |
| `api/main.py` | FastAPI app. `/score/{id}` returns probability. `/explain/{id}` returns SHAP. (Step 4) |
| `scripts/sync_crm.py` | Reads top-N risky accounts from Postgres, updates CRM custom fields. (Step 5) |

## Principles behind the architecture

**Single source of truth for each thing.** Raw data lives in CSVs (later:
warehouse). Trained model lives in `data/models/`. Predictions live in
Postgres. Features live in `build_features.py`. If you need to change
one of these, there's exactly one place to change it.

**Training-serving skew is the enemy.** The #1 way ML systems break in
production is that training code and scoring code compute features
differently. Here, both call the same `build_features()` function —
impossible for them to drift.

**Every service is stateless except the DB.** Airflow is stateless.
FastAPI is stateless. The CRM sync job is stateless. All state lives in
Postgres (predictions) or on disk (trained model). This makes everything
easy to restart, containerize, or horizontally scale.

**Cacheing at the right layer.** The model (28MB pickle) is cached once
per FastAPI worker process using `@lru_cache`. Feature columns are
cached the same way. Predictions are written to Postgres once per night
and read thousands of times from there — no re-scoring on every dashboard
page load.

**Predictions are append-only.** Every night we write a fresh row per
account with a `scored_at` timestamp. We never overwrite. This preserves
score history for trend analysis ("why did this account go from 0.3 to
0.7 in three weeks?").

## What's different from the "real" diagram in the research doc

The original architecture research included a feature store (Feast),
Kafka for streaming, Dagster instead of Airflow, Evidently for drift
monitoring, and multi-tenant deployment. All of that is correct for a
mid-stage SaaS company with a real ML platform team.

For a portfolio project where one person (you) builds everything, those
pieces are overkill. This architecture cuts it down to the minimum
viable production shape:

- Feature store → just `build_features.py` (good enough for one model)
- Kafka streaming → just nightly batch (good enough when churn is measured in weeks, not seconds)
- Dagster → Airflow (more common, easier to find tutorials and jobs for)
- Evidently drift monitoring → manual retraining cadence for now (v3)
- Multi-tenant → single project (v2+)

The point: every piece in this architecture is load-bearing. Nothing
here is ornamental. When you add the v2 pieces later, you add them
because they unlock a specific capability, not because they're trendy.
