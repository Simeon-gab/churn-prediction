"""
db.py
-----
Single place that knows how to create a SQLAlchemy engine.

Portfolio default: SQLite at data/churn.db
Production swap:   set DATABASE_URL to a Postgres DSN, e.g.
                   postgresql://user:pass@host:5432/dbname

Every other module calls get_engine() — none of them know or care
whether the backing DB is SQLite or Postgres. That's the whole point.

One schema difference to fix when promoting to Postgres:
  - scored_date is a plain TEXT column here (SQLite has no DATE type).
  - In Postgres, make it a GENERATED ALWAYS AS (scored_at::date) STORED
    column and keep the UNIQUE constraint on it.  The application code
    doesn't change; only the DDL in write_predictions.py needs updating.
"""

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


# Read from env var; fall back to SQLite in the repo's data/ folder.
# The path is relative to wherever the process is run from (project root).
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/churn.db")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine for the configured database.

    Cached per process — calling this 1,000 times costs the same as
    calling it once.  The cache is busted when the process restarts,
    which is exactly when you'd want a fresh connection pool anyway.
    """
    return create_engine(
        DATABASE_URL,
        # echo=True would log every SQL statement — handy for debugging,
        # but too noisy for normal runs.
        echo=False,
    )
