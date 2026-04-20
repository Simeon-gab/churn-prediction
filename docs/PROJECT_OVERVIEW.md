# Project Overview — Churn Prediction AI System

## What this project is

A churn prediction **system** — not just a model. The goal is to take a
working ML notebook and turn it into something a Customer Success team
uses every day: high-risk accounts flagged automatically, synced into
the CRM they already work in, explained with human-readable reasons,
and refreshed nightly without anyone babysitting it.

The ML part (loading data, training a Random Forest) is roughly 20% of
the work. The other 80% is the system around it — scheduling, APIs,
integrations, explainability, UI. That's what separates "a model in a
notebook" from "software that saves revenue."

## Who it's for

- **Primary user:** Customer Success Managers (CSMs) — they open the
  dashboard each morning, see their at-risk accounts, act on the
  recommended retention actions.
- **Secondary users:** Product (to see which features correlate with
  churn) and Sales (to catch expansion-at-risk accounts).
- **Tertiary:** Executives (quarterly revenue-at-risk reporting).

## Scope — v1

Deliberately narrow. Three things:

1. Automatically flag high-risk customers for the CS team
2. Provide recommended retention actions per customer
3. Surface both in a dashboard and in the CRM

Everything else — segment-specific thresholds, Slack alerts, A/B
testing retention strategies, next-best-action ML — is v2 or later.

## The 7-step build plan

| # | Step | Status | Deliverable |
|---|------|--------|-------------|
| 1 | Refactor monolithic notebook into modules | **done** | `src/data/`, `src/features/`, `src/models/`, `scripts/score_accounts.py` |
| 2 | Write Airflow DAG for nightly scoring | in progress | `dags/churn_scoring_dag.py` |
| 3 | Stand up Postgres predictions table + writer | pending | `src/data/write_predictions.py` |
| 4 | FastAPI service with `/score` and `/explain` (SHAP) | pending | `api/main.py` |
| 5 | HubSpot / Salesforce CRM sync job | pending | `scripts/sync_crm.py` |
| 6 | Next.js dashboard | pending | separate repo |
| 7 | Train + roll out to CS team | pending | internal docs |

Each step compounds on the previous one. Step 1 gives us a clean
`predict_churn_risk()` function; Step 2 wraps it in a scheduler; Step 4
wraps it in an API; Step 5 pushes the output into tools CSMs already
use. By Step 6, the same function is powering a dashboard, a CRM, and
a nightly batch job — all without being rewritten.

## Decisions we've made (and why)

**Random Forest over XGBoost/LSTM for v1.** Class-weighted RF with 400
trees gets us ROC-AUC ~0.66 on ~10% churn data. Not state-of-the-art,
but good enough to act on — and interpretable with SHAP. Model
improvements come in v2; system first.

**Class imbalance handled with `class_weight="balanced"` + custom
thresholds instead of SMOTE.** SMOTE creates synthetic minority samples;
`class_weight` reweights the loss function. The reweighting approach
preserves the real distribution of the data and is simpler to reason
about in production. Thresholds (`0.20 / 0.30 / 0.40`) are tuned on the
test set and live in `predict_model.py` so every consumer picks them
up consistently.

**Hardcoded paths in v1, config file in v2+.** Paths like
`data/models/churn_model.pkl` are hardcoded in `predict_model.py` and
`train_model.py`. This is fine for a single-environment project; when
we need to deploy to staging + prod + CI, we graduate to a `config.py`
or environment variables. Don't over-engineer early.

**Airflow DAG without a local Airflow server (Path C).** We write the
DAG properly, as if it were going to production, but skip running the
Airflow infrastructure locally. The DAG code is portable — Astronomer,
MWAA, or Cloud Composer can pick it up unchanged. Locally, cron + the
existing `score_accounts.py` is enough.

**Postgres for predictions, not BigQuery/Snowflake.** Predictions are
small (thousands of rows per day), read-heavy from the dashboard, and
need to be joined with CRM data. Postgres is the simplest thing that
works for the next 2 years of scale.

**FastAPI over Flask.** Async, type validation via Pydantic, automatic
OpenAPI docs, 3–5x throughput. Worth the minor learning delta.

**SHAP over LIME for explanations.** SHAP values are additive and
consistent — the same feature on the same account always contributes
the same amount. LIME is a local approximation that can give different
explanations for the same input. For CSMs who will ask "why does this
account's score differ from last week's?", SHAP gives a stable answer.

## Tech stack — final shape

```
Data warehouse (future)   →   Postgres predictions  →  FastAPI  →  Dashboard + CRM
         ↑                         ↑                      ↑
         │                         │                      │
    Raw CSVs today          Airflow nightly         SHAP explanations
```

| Layer | Choice | Reason |
|-------|--------|--------|
| ML | scikit-learn (RandomForest) | Interpretable, fast enough, ships with SHAP support |
| Orchestration | Airflow (DAG only for now) | Industry standard, portable |
| Storage | PostgreSQL | Simple, relational, good CRM-join story |
| API | FastAPI + Pydantic | Async, typed, auto-documented |
| Explainability | SHAP (TreeExplainer) | Additive, consistent per-account explanations |
| CRM | HubSpot or Salesforce | REST API, custom fields on Account object |
| Dashboard | Next.js + Recharts | React-based, matches team skillset |

## What success looks like

**For the ML system:** nightly scores land in Postgres by 4am. CRM custom
fields update by 7am. Dashboard loads in under 2 seconds. Zero manual
intervention for 30 consecutive days.

**For the business:** within 90 days of rollout, the CS team's
time-to-intervention on high-risk accounts drops from "when we notice"
to "within 48 hours." Measurable reduction in churn rate among flagged
accounts compared to unflagged baseline.

## What's out of scope

- Retention action *automation* (we recommend, CSMs act manually)
- Usage forecasting (different model, different project)
- Customer segmentation beyond the 4 risk tiers
- Multi-tenant / multi-company deployment
- Real-time streaming predictions (batch-only in v1)
- Model A/B testing (v3)

## How to navigate this repo

- `notebooks/` → exploratory work, the original story of how the model came to be
- `src/` → production code, imported by scripts and future services
- `scripts/` → entry points that glue modules together (batch scoring, future CRM sync)
- `dags/` → Airflow DAGs (Step 2+)
- `api/` → FastAPI service (Step 4+)
- `docs/` → this file, architecture, data dictionary, runbooks
- `data/raw/` → source CSVs (gitignored)
- `data/processed/` → output CSVs (gitignored)
- `data/models/` → trained model + feature schema (gitignored)
