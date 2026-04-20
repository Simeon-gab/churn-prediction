# CLAUDE.md

Context for Claude Code. Read this first, every session.

## Who I am

Gabriel — AI/ML engineer and design engineer, based in Lagos.

On the ML side: Walmart sales forecasting, this SaaS churn prediction
system, RAG pipelines, fine-tuning (deployed a Llama 3 8B model on
RunPod Serverless), agentic workflows. Comfortable with scikit-learn,
pandas, joblib, Hugging Face; growing into deeper neural networks
(LSTMs next). I reason about ML projects at the system level, not just
the model level — feature pipelines, training-serving skew,
orchestration, explainability, deployment.

On the engineering side: Next.js, React, Tailwind, Three.js, GSAP,
WebGL/GLSL. I ship production web apps and creative frontends.

The two sides converge in projects like this one, where ML models
need real interfaces, real APIs, and real integrations to be useful.

I learn project-first and pattern-oriented. When explaining new
concepts, use this three-layer pattern:
  1. Five-year-old analogy
  2. Plain English for a builder
  3. Full engineering depth

Copy style: no em dashes, human and storytelling-driven, concise.

## What this project is

A SaaS churn prediction **system** (not just a model). Turning a working
notebook into software a Customer Success team uses daily: flags
at-risk accounts, syncs to CRM, explains the reasons with SHAP, runs
nightly without supervision.

v1 scope is deliberately narrow:
  1. Flag high-risk customers automatically
  2. Recommend retention actions per customer
  3. Surface both in a dashboard and the CRM

Primary user: Customer Success Managers. Secondary: Product + Sales.

Read `docs/PROJECT_OVERVIEW.md` for the full scope and decisions.
Read `docs/ARCHITECTURE.md` for the component diagram and data flow.
Read `docs/data_dictionary.md` for column schemas.

## The 7-step build plan

| # | Step | Status |
|---|------|--------|
| 1 | Refactor monolithic script into modules | **done** |
| 2 | Airflow DAG for nightly scoring | **done** |
| 3 | Postgres predictions table + writer | **next** |
| 4 | FastAPI service with /score + /explain (SHAP) | pending |
| 5 | HubSpot / Salesforce CRM sync | pending |
| 6 | Next.js dashboard | pending |
| 7 | Rollout to CS team | pending |

## Where each file fits

- `src/data/load_data.py` — reads the 3 raw CSVs. Only file that knows filesystem paths for raw data.
- `src/features/build_features.py` — merge + aggregate + engineered features + one-hot encode. Used by both training and scoring, so they can't drift.
- `src/models/train_model.py` — run manually. Saves `churn_model.pkl` + `feature_columns.json`.
- `src/models/predict_model.py` — the `predict_churn_risk(features)` function. Imported by every downstream system. Model is `@lru_cache`'d.
- `scripts/score_accounts.py` — batch job. Load → features → predict → save CSVs. Verified working: scores 5000 accounts in under a minute, output looks healthy.
- `dags/churn_scoring_dag.py` — Airflow wrapper around the batch job. Production-ready; no local Airflow server needed.

## Decisions already locked in — don't re-litigate

- **Random Forest, not XGBoost/LSTM** for v1. 400 trees, `class_weight="balanced"`.
- **Class imbalance via class_weight + custom thresholds, not SMOTE.** Thresholds live in `predict_model.py`: Critical ≥ 0.40, High ≥ 0.30, Medium ≥ 0.20.
- **Hardcoded paths now, config.py later.** Don't over-engineer.
- **DAG written for production but run via cron locally (Path C).** No local Airflow server.
- **Postgres for predictions**, not BigQuery/Snowflake.
- **FastAPI over Flask** for Step 4.
- **SHAP TreeExplainer over LIME** for Step 4.
- **ROC-AUC ~0.66 is acceptable for v1.** System first, model quality second.

## How I want you to work

- Always read `docs/PROJECT_OVERVIEW.md` and `docs/ARCHITECTURE.md` before suggesting architecture changes.
- Don't regenerate files I haven't asked to change.
- When you write code, comment it heavily — I'm learning the patterns, not just shipping output.
- When explaining new concepts (Airflow, SHAP, Postgres, FastAPI), use my three-layer teaching style.
- Use the 7-step plan as the spine. Before jumping ahead to Step 5, make sure Step 3 is actually done.
- If I ask a question that has an answer in the docs, point me at the doc and quote the relevant line.
- Before making structural changes (new folders, new dependencies), show me what you plan to do and wait for confirmation.
- When something's ambiguous, ask. Don't guess and hope.

## Tech stack

ML: scikit-learn + joblib. Orchestration: Airflow. Storage: Postgres.
API: FastAPI + Pydantic. Explainability: SHAP. Frontend (Step 6):
Next.js + Recharts.

## How to run things locally

Project root: `churn_prediction/`. All commands run from there.

```bash
# Retrain the model
python -m src.models.train_model

# Run the nightly scoring pipeline (what the DAG calls)
python scripts/score_accounts.py
```

Raw CSVs live in `data/raw/`. Outputs land in `data/processed/`. Trained
model and feature schema live in `data/models/`.

## Current state of the data

- 5,000 subscriptions, ~10% churn rate (class imbalance is real)
- Last scoring run (verified): 4,522 Low / 77 Medium / 11 High / 390 Critical
- Model ROC-AUC on test set: ~0.66–0.68

## What I'm NOT asking for

- Rewriting existing modules unless broken
- New ML experiments (XGBoost, LightGBM, deep learning)
- Production Airflow deployment (Astronomer/MWAA/etc.)
- Multi-tenant / multi-environment config
- CI/CD pipeline setup
- Anything in v2+ from PROJECT_OVERVIEW.md

Focus on finishing the 7-step plan in order. One step at a time.
