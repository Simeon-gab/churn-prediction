"""
sync_to_hubspot.py
------------------
Syncs the latest churn predictions from the DB to HubSpot Companies.

What it does in order:
    1. Bootstrap: creates the "Churn Predictions" property group and 5 custom
       properties on the Company object (idempotent — safe to run every time).
    2. Loads one row per account from the DB (highest-risk subscription per
       account, most recent scoring date).
    3. Builds a HubSpot batch upsert payload for each account.
    4. Sends batches of 100 to HubSpot, with rate-limit handling and retries.

Identity mapping:
    We use HubSpot's idProperty upsert feature. The `churn_account_id` custom
    property (created at bootstrap, hasUniqueValue=True) acts as our foreign key.
    HubSpot does the find-or-create automatically — no manual seeding required.

Run modes:
    python scripts/sync_to_hubspot.py             # live sync
    python scripts/sync_to_hubspot.py --dry-run   # verify payload without calling HubSpot

Environment:
    HUBSPOT_ACCESS_TOKEN  required — set in .env (already in .gitignore)
    DATABASE_URL          optional — defaults to sqlite:///data/churn.db
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make src/ importable when running this script directly from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv
from sqlalchemy import text

import src.data.db as db
from src.data.db import get_engine


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HUBSPOT_API_BASE = "https://api.hubapi.com"

# All 5 custom properties live under this group in the Company sidebar.
PROPERTY_GROUP_NAME = "churn_predictions"
PROPERTY_GROUP_LABEL = "Churn Predictions"

# Batch upsert sends at most 100 records per request (HubSpot hard limit).
BATCH_SIZE = 100

# Sleep between batches to stay comfortably under the 100 req/10s rate limit.
# 150 ms → ~6.7 calls/sec, well within budget.
INTER_BATCH_SLEEP_S = 0.15

# Retry config for transient failures.
MAX_RETRIES = 3
RETRY_BACKOFF_S = [1, 2, 4]  # sleep durations for attempts 1, 2, 3


# ---------------------------------------------------------------------------
# SHAP factor formatting
# ---------------------------------------------------------------------------

def _impact_label(shap_value: float) -> str:
    """Convert a raw SHAP value to a CSM-readable impact tier.

    Thresholds were agreed in the Step 5 plan:
      >= 0.10 → strong impact   (moves the score 10+ percentage points)
      >= 0.05 → moderate impact (moves the score 5–9 percentage points)
      <  0.05 → mild impact     (moves the score < 5 percentage points)
    """
    abs_val = abs(shap_value)
    if abs_val >= 0.10:
        return "strong impact"
    elif abs_val >= 0.05:
        return "moderate impact"
    else:
        return "mild impact"


def _strip_units(label: str) -> str:
    """Remove the parenthetical units from a FEATURE_LABELS string.

    "Days as a customer (days)"  ->  "Days as a customer"
    "Product usage frequency (events per day)"  ->  "Product usage frequency"
    """
    # Split on " (" and take everything before it.
    # If there's no " (", the label is returned unchanged.
    return label.split(" (")[0]


def format_top_factors(top_factors_json: str | None, scored_date: str) -> str:
    """Convert SHAP top-factors JSON to a human-readable HubSpot textarea string.

    Output groups factors by direction (increasing / decreasing risk),
    sorted by magnitude within each group. Raw SHAP values are replaced
    with plain-English impact labels so CSMs can act without needing to
    understand what a SHAP value is.

    NULL top_factors → explicit placeholder with the scoring date so
    CSMs know the explanation is missing for a specific run, not forever.

    Example output:
        Factors increasing churn risk:
        1. Days as a customer          (strong impact)
        2. Product usage frequency     (strong impact)

        Factors decreasing churn risk:
        1. Average first response time   (moderate impact)
        2. Average ticket resolution time (moderate impact)
        3. Beta feature adoption rate    (mild impact)
    """
    if not top_factors_json:
        return f"Explanation not available for the {scored_date} scoring run."

    factors = json.loads(top_factors_json)

    # Split into two groups and sort each by absolute SHAP value (largest first)
    increasing = sorted(
        [f for f in factors if f["direction"] == "increases_risk"],
        key=lambda f: abs(f["shap_value"]),
        reverse=True,
    )
    decreasing = sorted(
        [f for f in factors if f["direction"] == "decreases_risk"],
        key=lambda f: abs(f["shap_value"]),
        reverse=True,
    )

    lines = []

    if increasing:
        lines.append("Factors increasing churn risk:")
        for i, f in enumerate(increasing, 1):
            name = _strip_units(f["feature"])
            lines.append(f"{i}. {name}  ({_impact_label(f['shap_value'])})")

    if increasing and decreasing:
        lines.append("")  # blank line between sections

    if decreasing:
        lines.append("Factors decreasing churn risk:")
        for i, f in enumerate(decreasing, 1):
            name = _strip_units(f["feature"])
            lines.append(f"{i}. {name}  ({_impact_label(f['shap_value'])})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_company_payload(row: dict) -> dict:
    """Build a single HubSpot batch upsert input for one account.

    The `idProperty` field tells HubSpot to use churn_account_id as the
    lookup key instead of its internal company ID. This enables find-or-create
    without us needing to store HubSpot IDs anywhere.

    All property values are sent as strings — HubSpot converts to the
    appropriate type server-side based on the property definition.

    churn_risk_score is scaled to 0–100 for HubSpot display (the DB stores
    the raw 0–1 probability; only this field is converted).
    """
    account_id = row["account_id"]
    score_pct = round(float(row["churn_probability"]) * 100, 2)
    factors_text = format_top_factors(row["top_factors"], row["scored_date"])

    return {
        "idProperty": "churn_account_id",
        "id": account_id,          # the value HubSpot looks up in churn_account_id
        "properties": {
            "name":               f"Account {account_id}",
            "churn_account_id":   account_id,
            "churn_risk_score":   str(score_pct),
            "churn_risk_level":   row["risk_level"],
            "churn_risk_factors": factors_text,
            "churn_scored_date":  row["scored_date"],
        },
    }


# ---------------------------------------------------------------------------
# DB loader
# ---------------------------------------------------------------------------

def load_latest_predictions(engine) -> list[dict]:
    """Load one row per account from the DB: highest-risk subscription per account,
    on the most recent scoring date.

    Why "highest-risk subscription per account"?
    An account can have multiple subscriptions. We sync the one that represents
    the greatest churn risk — that's what a CSM should act on first.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            -- ROW_NUMBER() breaks ties deterministically (lowest subscription_id wins)
            -- so each account_id appears exactly once. Without this, two subscriptions
            -- with identical max churn_probability produce duplicate account rows,
            -- which HubSpot's batch upsert rejects with a 400.
            WITH ranked AS (
                SELECT
                    account_id,
                    subscription_id,
                    churn_probability,
                    risk_level,
                    scored_at,
                    scored_date,
                    top_factors,
                    ROW_NUMBER() OVER (
                        PARTITION BY account_id
                        ORDER BY churn_probability DESC, subscription_id ASC
                    ) AS rn
                FROM churn_predictions
                WHERE scored_date = (SELECT MAX(scored_date) FROM churn_predictions)
            )
            SELECT account_id, subscription_id, churn_probability,
                   risk_level, scored_at, scored_date, top_factors
            FROM ranked
            WHERE rn = 1
            ORDER BY churn_probability DESC
        """)).fetchall()

    # Convert SQLAlchemy Row objects to plain dicts for easier access
    return [dict(row._mapping) for row in rows]


# ---------------------------------------------------------------------------
# HubSpot bootstrap (idempotent property setup)
# ---------------------------------------------------------------------------

def _hs_post(url: str, payload: dict, token: str) -> requests.Response:
    """POST to HubSpot with auth header. Returns the response object."""
    return requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )


def ensure_property_group(token: str) -> None:
    """Create the 'Churn Predictions' property group on Company, if not already present.

    A property group is just a collapsible section label in the HubSpot
    Company sidebar. It has no data of its own — it just organises the 5
    custom properties so CSMs can find them quickly.

    409 Conflict means the group already exists → safe to ignore.
    """
    resp = _hs_post(
        f"{HUBSPOT_API_BASE}/crm/v3/properties/companies/groups",
        # HubSpot requires "label" (not "displayName") for property group creation
        {"name": PROPERTY_GROUP_NAME, "label": PROPERTY_GROUP_LABEL},
        token,
    )
    if resp.status_code == 409:
        print(f"  Property group '{PROPERTY_GROUP_NAME}' already exists — skipping.")
    elif resp.status_code == 201:
        print(f"  Created property group '{PROPERTY_GROUP_NAME}'.")
    else:
        # Unexpected — surface the error so we know what went wrong
        resp.raise_for_status()


def ensure_custom_properties(token: str) -> None:
    """Create the 5 custom properties on the Company object, if not already present.

    Property definitions are the schema — they tell HubSpot what type of
    data each field holds. Once created, they persist on the portal forever
    (you'd delete them manually in HubSpot settings if needed).

    hasUniqueValue=True on churn_account_id is load-bearing: it's what makes
    the idProperty batch upsert work. Without it, HubSpot can't use this
    field as a lookup key.
    """
    properties = [
        # --- Identity key (must be unique) ---
        {
            "name":         "churn_account_id",
            "label":        "Churn Account ID",
            "type":         "string",
            "fieldType":    "text",
            "groupName":    PROPERTY_GROUP_NAME,
            "hasUniqueValue": True,
            "description":  "Internal account ID from the churn prediction system (e.g. A-c43359).",
        },
        # --- Numeric score (0–100 scale for HubSpot display) ---
        {
            "name":      "churn_risk_score",
            "label":     "Churn Risk Score",
            "type":      "number",
            "fieldType": "number",
            "groupName": PROPERTY_GROUP_NAME,
            "description": "Churn probability expressed as 0–100. 78 means 78% predicted churn probability.",
        },
        # --- Risk tier (enum so HubSpot can filter/segment by it) ---
        {
            "name":      "churn_risk_level",
            "label":     "Churn Risk Level",
            "type":      "enumeration",
            "fieldType": "select",
            "groupName": PROPERTY_GROUP_NAME,
            "options": [
                {"label": "Low",      "value": "Low",      "displayOrder": 0, "hidden": False},
                {"label": "Medium",   "value": "Medium",   "displayOrder": 1, "hidden": False},
                {"label": "High",     "value": "High",     "displayOrder": 2, "hidden": False},
                {"label": "Critical", "value": "Critical", "displayOrder": 3, "hidden": False},
            ],
            "description": "Risk tier assigned by the churn model: Low / Medium / High / Critical.",
        },
        # --- Human-readable SHAP explanation ---
        {
            "name":      "churn_risk_factors",
            "label":     "Top Churn Factors",
            "type":      "string",
            "fieldType": "textarea",
            "groupName": PROPERTY_GROUP_NAME,
            "description": "Top drivers of this account's churn risk, grouped by direction and labeled by impact strength.",
        },
        # --- Date of last score ---
        {
            "name":      "churn_scored_date",
            "label":     "Churn Scored Date",
            "type":      "string",
            "fieldType": "text",
            "groupName": PROPERTY_GROUP_NAME,
            "description": "Date (YYYY-MM-DD) of the most recent nightly scoring run for this account.",
        },
    ]

    for prop in properties:
        resp = _hs_post(
            f"{HUBSPOT_API_BASE}/crm/v3/properties/companies",
            prop,
            token,
        )
        if resp.status_code == 409:
            print(f"  Property '{prop['name']}' already exists — skipping.")
        elif resp.status_code == 201:
            print(f"  Created property '{prop['name']}'.")
        else:
            resp.raise_for_status()


# ---------------------------------------------------------------------------
# Batch upsert (with retry)
# ---------------------------------------------------------------------------

def _send_batch_with_retry(batch: list[dict], token: str, batch_num: int) -> tuple[int, list[str], list[dict]]:
    """POST one batch of up to 100 company upserts to HubSpot.

    Returns (success_count, failed_account_ids, hs_result_objects).
    hs_result_objects are the raw HubSpot response objects (each has an "id"
    field — the HubSpot internal company ID) and are zipped with the input
    batch to build the hubspot_account_map write-back.

    Retry logic:
      429 → sleep Retry-After seconds (default 10s), retry up to MAX_RETRIES times.
      5xx → exponential backoff (1s / 2s / 4s), retry up to MAX_RETRIES times.
      4xx (not 429) → fail fast, no retry (bad payload/token — retrying won't help).
    """
    url = f"{HUBSPOT_API_BASE}/crm/v3/objects/companies/batch/upsert"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    failed_ids = [item["id"] for item in batch]  # assume failure until we succeed

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json={"inputs": batch}, timeout=30)
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
                print(f"  Batch {batch_num}: network error ({exc}), retry {attempt + 1} in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  Batch {batch_num}: failed after {MAX_RETRIES} retries (network error).")
            return 0, failed_ids, []

        if resp.status_code in (200, 201):
            # HubSpot returns {"status": "COMPLETE", "results": [...]}
            results = resp.json().get("results", [])
            return len(results), [], results

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            if attempt < MAX_RETRIES:
                print(f"  Batch {batch_num}: rate limited — sleeping {retry_after}s, retry {attempt + 1}...")
                time.sleep(retry_after)
                continue
            print(f"  Batch {batch_num}: rate limit exceeded after {MAX_RETRIES} retries.")
            return 0, failed_ids, []

        if resp.status_code >= 500:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)]
                print(f"  Batch {batch_num}: server error {resp.status_code}, retry {attempt + 1} in {wait}s...")
                time.sleep(wait)
                continue
            print(f"  Batch {batch_num}: server error after {MAX_RETRIES} retries: {resp.text[:200]}")
            return 0, failed_ids, []

        # Any other 4xx — bad request or bad token, retrying won't help
        print(f"  Batch {batch_num}: fatal error {resp.status_code}: {resp.text[:300]}")
        return 0, failed_ids, []

    return 0, failed_ids, []  # exhausted retries


# ---------------------------------------------------------------------------
# HubSpot ID mapping write-back
# ---------------------------------------------------------------------------

def write_hubspot_map(engine, paired: list[tuple[dict, dict]]) -> None:
    """Upsert (account_id, hubspot_company_id) pairs into hubspot_account_map.

    Called once after all sync batches complete. paired is a list of
    (input_payload, hs_result) tuples — the input's "id" field is the
    account_id (set in build_company_payload), and the result's "id" is
    the HubSpot internal company ID. Results come back in input order.
    """
    now = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hubspot_account_map (
                account_id      TEXT PRIMARY KEY,
                hubspot_company_id TEXT NOT NULL,
                last_synced_at  TEXT NOT NULL
            )
        """))

        written = 0
        for inp, result in paired:
            account_id = inp.get("id")
            hs_id = result.get("id")
            if not account_id or not hs_id:
                continue
            conn.execute(text("""
                INSERT INTO hubspot_account_map (account_id, hubspot_company_id, last_synced_at)
                VALUES (:aid, :hid, :ts)
                ON CONFLICT(account_id) DO UPDATE SET
                    hubspot_company_id = excluded.hubspot_company_id,
                    last_synced_at     = excluded.last_synced_at
            """), {"aid": account_id, "hid": hs_id, "ts": now})
            written += 1

    print(f"  HubSpot ID map: {written} rows written to hubspot_account_map.")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def sync_to_hubspot(dry_run: bool = False) -> None:
    """Main sync flow: bootstrap → load → build payloads → upsert.

    In dry-run mode, all steps up to "upsert" run normally (including the DB
    load and payload build), but no HTTP requests reach HubSpot. This lets
    you verify the exact payload shape before spending any rate-limit budget.
    """
    # --- Load credentials ---
    # .env is UTF-16 LE with BOM (written by Windows Notepad/VS Code on this machine).
    # Passing encoding='utf-16' tells Python to detect the BOM and decode correctly.
    load_dotenv(encoding="utf-16")
    import os
    token = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not token:
        sys.exit("ERROR: HUBSPOT_ACCESS_TOKEN not set. Add it to .env and retry.")

    if dry_run:
        print("=" * 60)
        print("DRY RUN -- no HubSpot API calls will be made.")
        print("=" * 60)

    # --- Bootstrap: create property group + custom properties ---
    if not dry_run:
        print("\nBootstrapping HubSpot properties...")
        ensure_property_group(token)
        ensure_custom_properties(token)
        print("Bootstrap complete.\n")
    else:
        print("\n[Skipping bootstrap in dry-run mode]\n")

    # --- Load predictions from DB ---
    engine = get_engine()
    print("Loading latest predictions from DB...")
    records = load_latest_predictions(engine)

    if not records:
        sys.exit("ERROR: No predictions found in DB. Run score_accounts.py first.")

    scored_date = records[0]["scored_date"]  # all rows share the same date (latest run)
    print(f"  Scoring date : {scored_date}")
    print(f"  Accounts     : {len(records)}")

    # Risk tier counts for the summary header
    tier_counts = {}
    for r in records:
        tier_counts[r["risk_level"]] = tier_counts.get(r["risk_level"], 0) + 1

    print("\n  Risk tier breakdown:")
    for tier in ["Critical", "High", "Medium", "Low"]:
        count = tier_counts.get(tier, 0)
        pct = count / len(records) * 100
        print(f"    {tier:<10} {count:>5}  ({pct:.1f}%)")

    n_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\n  Batches: {n_batches} x {BATCH_SIZE} records")

    # --- Build payloads ---
    payloads = [build_company_payload(r) for r in records]

    # --- Dry-run: print sample payloads and exit ---
    if dry_run:
        print("\n" + "-" * 60)
        print("Sample payloads (first 3 companies):")
        print("-" * 60)
        for i, p in enumerate(payloads[:3], 1):
            props = p["properties"]
            print(f"\n[{i}] {p['id']}  ->  {props['churn_risk_level']}  {props['churn_risk_score']}%")
            print(f"    name              : {props['name']}")
            print(f"    churn_account_id  : {props['churn_account_id']}")
            print(f"    churn_risk_score  : {props['churn_risk_score']}")
            print(f"    churn_risk_level  : {props['churn_risk_level']}")
            print(f"    churn_scored_date : {props['churn_scored_date']}")
            print(f"    churn_risk_factors:")
            for line in props["churn_risk_factors"].splitlines():
                print(f"      {line}")
        print("\n" + "=" * 60)
        print("DRY RUN complete. Run without --dry-run to sync to HubSpot.")
        print("=" * 60)
        return

    # --- Live sync: send batches ---
    print("\nStarting sync to HubSpot...")
    total_success = 0
    all_failed_ids: list[str] = []
    all_paired: list[tuple[dict, dict]] = []  # (input_payload, hs_result) for write-back

    for i in range(0, len(payloads), BATCH_SIZE):
        batch = payloads[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        success, failed, hs_results = _send_batch_with_retry(batch, token, batch_num)
        total_success += success
        all_failed_ids.extend(failed)
        all_paired.extend(zip(batch, hs_results))
        print(f"  Batch {batch_num}/{n_batches}: {success}/{len(batch)} upserted")
        if batch_num < n_batches:
            time.sleep(INTER_BATCH_SLEEP_S)

    # Write HubSpot company IDs back to the local mapping table so the
    # dashboard can build HubSpot URLs without making live API calls.
    if all_paired:
        write_hubspot_map(engine, all_paired)

    # --- Summary ---
    print("\n" + "=" * 60)
    print(f"Sync complete.")
    print(f"  Succeeded : {total_success}")
    print(f"  Failed    : {len(all_failed_ids)}")
    if all_failed_ids:
        print(f"  Failed IDs: {', '.join(all_failed_ids[:20])}")
        if len(all_failed_ids) > 20:
            print(f"              ... and {len(all_failed_ids) - 20} more.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync churn predictions from the DB to HubSpot Companies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/sync_to_hubspot.py --dry-run   # verify payloads, no API calls
  python scripts/sync_to_hubspot.py             # live sync
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be synced without calling the HubSpot API.",
    )
    args = parser.parse_args()
    sync_to_hubspot(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
