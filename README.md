# Churn Prediction — SaaS Streamline

Predicts which SaaS customers are likely to churn, so Customer Success
can act before they cancel. This repo is the ML foundation for a full
AI system (Airflow + FastAPI + CRM sync + dashboard) — see `docs/` for
the roadmap.

## Project structure

```
churn_prediction/
├── data/
│   ├── raw/               # source CSVs (subs, usage, tickets)
│   ├── processed/         # scored output CSVs
│   └── models/            # trained .pkl + feature schema
├── src/
│   ├── data/              # load_data.py
│   ├── features/          # build_features.py
│   └── models/            # train_model.py, predict_model.py
├── scripts/
│   └── score_accounts.py  # the batch job (Airflow calls this)
├── notebooks/             # exploratory work
├── tests/
├── docs/
├── requirements.txt
└── README.md
```

## Setup

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Put the raw CSVs in data/raw/
#    ravenstack_subscriptions.csv
#    ravenstack_feature_usage.csv
#    ravenstack_support_tickets.csv
```

## How to use it

**Train the model** (run once, or when retraining):
```bash
python -m src.models.train_model
```
Outputs `data/models/churn_model.pkl` and `data/models/feature_columns.json`.

**Score all accounts** (what Airflow runs nightly):
```bash
python scripts/score_accounts.py
```
Outputs:
- `data/processed/churn_risk_predictions.csv` — all customers ranked
- `data/processed/high_medium_risk_customers.csv` — the CSM action list

## Risk tiers

| Tier     | Probability | Action                          |
|----------|-------------|---------------------------------|
| Critical | ≥ 0.40      | Immediate CSM outreach          |
| High     | ≥ 0.30      | Outreach this week              |
| Medium   | ≥ 0.20      | Monitor and engage              |
| Low      | < 0.20      | No action needed                |

Thresholds live in `src/models/predict_model.py` — tune there and every
consumer picks up the change.

## What's next

This is **Step 1** of a 7-step build:

1. **[done]** Refactor monolithic script into modules
2. Set up Airflow to orchestrate nightly scoring
3. Write scoring DAG → Postgres
4. FastAPI service with `/score` and `/explain` endpoints (SHAP)
5. HubSpot / Salesforce CRM sync
6. Next.js dashboard
7. Roll out to Customer Success team
