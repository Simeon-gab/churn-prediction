# Data Dictionary

The churn model is fed by three raw CSVs. This is what each column means.

## `ravenstack_subscriptions.csv` — 5,000 rows

One row per subscription. `churn_flag` is the target.

| Column              | Type    | Description                                          |
|---------------------|---------|------------------------------------------------------|
| subscription_id     | str     | Unique ID (e.g., `S-8cec59`)                         |
| account_id          | str     | FK to the parent account (e.g., `A-3c1a3f`)          |
| start_date          | date    | Subscription start (DD/MM/YYYY)                      |
| end_date            | date    | Subscription end — null if still active              |
| plan_tier           | str     | `Basic` / `Pro` / `Enterprise`                       |
| seats               | int     | Number of seats on the subscription                  |
| mrr_amount          | int     | Monthly recurring revenue ($)                        |
| arr_amount          | int     | Annual recurring revenue ($)                         |
| is_trial            | bool    | Whether this was a trial                             |
| upgrade_flag        | bool    | Whether the subscription was upgraded                |
| downgrade_flag      | bool    | Whether the subscription was downgraded              |
| **churn_flag**      | bool    | **Target: True if the subscription churned**         |
| billing_frequency   | str     | `monthly` / `annual`                                 |
| auto_renew_flag     | bool    | Whether auto-renew is on                             |

## `ravenstack_feature_usage.csv` — 25,000 rows

Many rows per subscription. Aggregated in `build_features.py`.

| Column              | Type    | Description                                          |
|---------------------|---------|------------------------------------------------------|
| usage_id            | str     | Unique event ID                                      |
| subscription_id     | str     | FK to subscription                                   |
| usage_date          | date    | When the event happened                              |
| feature_name        | str     | Which product feature was used                       |
| usage_count         | int     | Number of times the feature was used                 |
| usage_duration_secs | int     | Total duration in seconds                            |
| error_count         | int     | Errors hit during that usage                         |
| is_beta_feature     | bool    | Whether the feature is in beta                       |

## `ravenstack_support_tickets.csv` — 2,000 rows

Many rows per account. Aggregated in `build_features.py`.

| Column                        | Type  | Description                                  |
|-------------------------------|-------|----------------------------------------------|
| ticket_id                     | str   | Unique ticket ID                             |
| account_id                    | str   | FK to account                                |
| submitted_at                  | date  | When the ticket was opened                   |
| closed_at                     | datetime | When the ticket was closed                |
| resolution_time_hours         | int   | Hours from submit to close                   |
| priority                      | str   | `low` / `medium` / `high` / `urgent`         |
| first_response_time_minutes   | int   | Minutes until first agent response           |
| satisfaction_score            | float | CSAT, 1–5 (nullable)                         |
| escalation_flag               | bool  | Whether the ticket was escalated             |

## Engineered features (added by `build_features.py`)

| Feature               | Formula                                             |
|-----------------------|-----------------------------------------------------|
| tenure_days           | (end_date or reference_date) − start_date           |
| revenue_per_seat      | mrr_amount / seats                                  |
| usage_per_seat        | total_usage_count / seats                           |
| error_rate            | total_errors / (total_usage_count + 1)              |
| usage_per_day         | total_usage_count / (tenure_days + 1)               |
