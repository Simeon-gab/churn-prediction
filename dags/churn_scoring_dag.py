"""
churn_scoring_dag.py
--------------------
Airflow DAG that runs the nightly churn scoring pipeline.

Schedule: every day at 3:00 AM (before CSMs start their day)
Tasks:
    1. check_raw_data       — verify the 3 raw CSVs exist and aren't empty
    2. score_accounts       — run the batch scoring pipeline
    3. validate_predictions — sanity-check the output (not all Low, etc.)
    4. notify_completion    — log that the pipeline finished (stub for Slack later)

If any task fails, Airflow retries it up to 2 times with a 5-minute delay
between attempts. If it still fails, email_on_failure fires.

NOTE: This DAG is written to be production-ready but does NOT require
a running Airflow server locally. It's designed to drop into Astronomer,
MWAA, Cloud Composer, or a self-hosted Airflow instance unchanged.

To deploy: copy this file into your Airflow DAGs folder. Airflow will
auto-discover it within ~30 seconds.
"""

from datetime import datetime, timedelta
from pathlib import Path
import sys

# Airflow imports — these only resolve inside a real Airflow environment.
# Local linters may complain; that's fine.
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

# Make the project's `src/` and `scripts/` importable from inside the DAG.
# In production Airflow, you'd instead install this project as a package
# (pip install -e .) or mount it into the Airflow worker container.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------
# Default arguments — apply to every task in this DAG unless overridden
# ---------------------------------------------------------------------
#
# These are Airflow's knobs for "what happens when things go wrong."
# Every production DAG sets these. The defaults below are sensible for
# a nightly batch job where speed isn't critical but reliability is.
default_args = {
    # Who owns this DAG — shows up in the Airflow UI, paged if it fails
    "owner": "data_science",

    # Don't wait for yesterday's run to finish before running today's.
    # Set to True if runs MUST be sequential (e.g., cumulative aggregates).
    "depends_on_past": False,

    # Who gets emailed when things fail
    "email": ["data-alerts@example.com"],
    "email_on_failure": True,
    "email_on_retry": False,

    # If a task fails, try again up to 2 more times with a 5-minute pause
    "retries": 2,
    "retry_delay": timedelta(minutes=5),

    # Fail the task if it runs longer than 30 minutes (scoring 5k accounts
    # should take ~30 seconds; 30 min is a generous safety net)
    "execution_timeout": timedelta(minutes=30),
}


# ---------------------------------------------------------------------
# The DAG itself
# ---------------------------------------------------------------------
#
# A DAG is just metadata: when to run, how often, what its ID is. The
# actual work happens in the tasks we attach to it below.
with DAG(
    dag_id="churn_scoring_daily",
    description="Nightly churn risk scoring for all active accounts",
    default_args=default_args,

    # Run once a day at 3:00 AM UTC. This is standard cron syntax:
    #   "0 3 * * *" = minute 0, hour 3, any day of month, any month, any day of week
    schedule="0 3 * * *",

    # When the DAG first became active. Airflow won't backfill runs before this.
    start_date=datetime(2026, 1, 1),

    # If the scheduler misses a run (say, Airflow was down), don't try
    # to catch up by running every missed day. Just run the next scheduled one.
    catchup=False,

    # Tags show up in the Airflow UI for filtering
    tags=["churn", "ml", "customer-success"],

    # How long a DAG run can take from kickoff to completion
    dagrun_timeout=timedelta(hours=1),
) as dag:

    # -----------------------------------------------------------------
    # Task 1 — Pre-flight check: do the raw CSVs exist?
    # -----------------------------------------------------------------
    #
    # This is a "fail fast" guard. If the raw data isn't where we
    # expect, there's no point running the full pipeline. We catch
    # the problem in 0.1 seconds instead of 30.
    def _check_raw_data():
        """Verify the 3 raw CSVs exist and have content."""
        raw_dir = PROJECT_ROOT / "data" / "raw"
        required_files = [
            "ravenstack_subscriptions.csv",
            "ravenstack_feature_usage.csv",
            "ravenstack_support_tickets.csv",
        ]

        for filename in required_files:
            filepath = raw_dir / filename
            if not filepath.exists():
                raise FileNotFoundError(f"Missing raw data: {filepath}")
            if filepath.stat().st_size == 0:
                raise ValueError(f"Raw data is empty: {filepath}")

        print(f"All 3 raw CSVs present in {raw_dir}")

    check_raw_data = PythonOperator(
        task_id="check_raw_data",
        python_callable=_check_raw_data,
    )


    # -----------------------------------------------------------------
    # Task 2 — Run the batch scoring pipeline
    # -----------------------------------------------------------------
    #
    # This is the meat of the DAG. It calls the EXACT SAME function
    # you run manually today: scripts/score_accounts.py::score_accounts().
    # No duplicated logic. If the function works locally, it works here.
    def _score_accounts():
        """Load, feature-engineer, score, save the predictions."""
        # Import here (not at the top of the file) so Airflow's DAG
        # parser doesn't choke on project imports when it's just
        # trying to read DAG metadata.
        from scripts.score_accounts import score_accounts
        risk_table = score_accounts()
        print(f"Scored {len(risk_table)} accounts")
        # Return a small summary dict. Airflow stores this in XCom,
        # which lets downstream tasks read it.
        return {
            "total_accounts": len(risk_table),
            "critical": int((risk_table["risk_level"] == "Critical").sum()),
            "high": int((risk_table["risk_level"] == "High").sum()),
            "medium": int((risk_table["risk_level"] == "Medium").sum()),
            "low": int((risk_table["risk_level"] == "Low").sum()),
        }

    score_accounts_task = PythonOperator(
        task_id="score_accounts",
        python_callable=_score_accounts,
    )


    # -----------------------------------------------------------------
    # Task 3 — Validate the predictions look reasonable
    # -----------------------------------------------------------------
    #
    # ML systems fail silently. The batch script might "succeed" (no
    # Python errors) but output garbage — every account marked Low,
    # or every account Critical, or all probabilities exactly 0.5.
    # This task catches those failures before they poison the CRM.
    def _validate_predictions(**context):
        """Sanity-check: did the model actually produce a reasonable distribution?"""
        # Read the summary from the previous task via XCom
        summary = context["ti"].xcom_pull(task_ids="score_accounts")

        total = summary["total_accounts"]
        critical = summary["critical"]
        high = summary["high"]

        # Red flag 1: no accounts scored
        if total == 0:
            raise ValueError("No accounts were scored — pipeline output empty")

        # Red flag 2: everyone is Critical (model broke)
        if critical / total > 0.5:
            raise ValueError(
                f"Over 50% of accounts flagged Critical ({critical}/{total}). "
                "Likely a model or feature pipeline regression."
            )

        # Red flag 3: nobody is Critical or High (model also broke)
        if (critical + high) == 0:
            raise ValueError(
                "Zero accounts flagged Critical or High. "
                "Model is not producing actionable signal."
            )

        print(f"Predictions look healthy: {summary}")

    validate_predictions = PythonOperator(
        task_id="validate_predictions",
        python_callable=_validate_predictions,
    )


    # -----------------------------------------------------------------
    # Task 4 — Notify that the pipeline finished
    # -----------------------------------------------------------------
    #
    # For now, just logs. In Step 5+ this becomes a Slack webhook and
    # a "trigger CRM sync" signal.
    notify_completion = BashOperator(
        task_id="notify_completion",
        bash_command='echo "[$(date)] Churn scoring pipeline completed successfully"',
    )


    # -----------------------------------------------------------------
    # Task dependencies — who runs before who
    # -----------------------------------------------------------------
    #
    # Airflow lets you express this as a left-to-right arrow chain.
    # Reads as: "check_raw_data runs first, then score_accounts, then
    # validate, then notify." If any task fails, downstream tasks are
    # skipped — so we don't notify "complete" on a broken run.
    check_raw_data >> score_accounts_task >> validate_predictions >> notify_completion
