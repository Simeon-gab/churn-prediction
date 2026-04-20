# Airflow DAGs

## `churn_scoring_dag.py`

Runs the nightly churn scoring pipeline. Wraps
`scripts/score_accounts.py` with scheduling, retries, alerting, and
sanity checks.

### What it does (in plain English)

Every night at 3 AM:
1. Checks the 3 raw CSVs exist (fails fast if not)
2. Runs the scoring pipeline
3. Validates the output looks reasonable (not all-Low, not all-Critical)
4. Logs that the run completed

If any step fails, Airflow retries twice with a 5-min delay. Still fails?
Email alert fires.

### How to deploy it

#### Option 1 — Astronomer / MWAA / Cloud Composer (managed Airflow)

Copy `churn_scoring_dag.py` into your deployment's `dags/` folder.
Push. Airflow auto-discovers it within 30 seconds.

Make sure the project's `src/` and `scripts/` are on the Python path
on your Airflow workers — either by pip-installing the project or
mounting it into the worker image.

#### Option 2 — Self-hosted Airflow (Docker)

```bash
# In your docker-compose.yaml, mount this project into the worker:
#   volumes:
#     - ./churn_prediction:/opt/airflow/churn_prediction
#
# Set PYTHONPATH so imports resolve:
#   environment:
#     PYTHONPATH: /opt/airflow/churn_prediction

# Then copy the DAG into the Airflow dags folder:
cp dags/churn_scoring_dag.py $AIRFLOW_HOME/dags/
```

#### Option 3 — No Airflow at all (cron)

If you want the same outcome without the infrastructure, cron is fine.
From the project root:

```bash
# Edit your crontab
crontab -e

# Add this line — runs at 3 AM daily:
0 3 * * * cd /path/to/churn_prediction && /path/to/.venv/bin/python scripts/score_accounts.py >> logs/cron.log 2>&1
```

You lose the retries, the validation task, and the web UI. You keep
the nightly schedule. Fine for personal / portfolio use.

### Development workflow

You don't need to run Airflow locally to develop the DAG. The DAG is
thin — all real work lives in `scripts/score_accounts.py`, which you
can run directly with `python scripts/score_accounts.py`.

When the script works, the DAG works. Debug in the script, ship the DAG.

### Gotchas

- **Imports inside task functions.** Notice that `_score_accounts()`
  imports `from scripts.score_accounts import score_accounts` *inside*
  the function, not at the top of the file. This is intentional: Airflow
  parses DAG files constantly to discover schedule changes, and heavy
  top-level imports slow that down. Imports inside tasks run only when
  the task actually executes.

- **XCom is small.** The `return` value of `_score_accounts()` gets
  stored in Airflow's XCom system so `_validate_predictions` can read
  it. XCom is designed for small metadata (dicts, ints, strings) — not
  for passing the full 5000-row DataFrame. That's why we return a
  summary dict, not the dataframe itself.

- **`schedule` vs `schedule_interval`.** Airflow 2.4+ uses `schedule`.
  Older code you might see online uses `schedule_interval`. Both work;
  `schedule` is preferred.
