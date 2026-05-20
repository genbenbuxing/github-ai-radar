from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS repositories (
  id INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL UNIQUE,
  url TEXT NOT NULL,
  description TEXT,
  primary_language TEXT,
  license_key TEXT,
  created_at TEXT,
  is_archived INTEGER NOT NULL DEFAULT 0,
  is_fork INTEGER NOT NULL DEFAULT 0,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_snapshots (
  id INTEGER PRIMARY KEY,
  repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  snapshot_date TEXT NOT NULL,
  stars INTEGER,
  forks INTEGER,
  open_issues INTEGER,
  pushed_at TEXT,
  updated_at TEXT,
  topics_json TEXT,
  entered_candidate_pool INTEGER NOT NULL DEFAULT 0,
  UNIQUE(repository_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS repo_reviews (
  id INTEGER PRIMARY KEY,
  repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  run_id INTEGER,
  reviewed_at TEXT NOT NULL,
  score INTEGER NOT NULL,
  recommendation TEXT NOT NULL,
  readme_quality TEXT,
  usability_notes TEXT,
  risk_notes TEXT,
  scoring_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  event_date TEXT NOT NULL,
  domain TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  source_name TEXT,
  summary TEXT,
  facts_json TEXT,
  inference_json TEXT,
  UNIQUE(event_date, url)
);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  title TEXT,
  publisher TEXT,
  source_type TEXT,
  fetched_at TEXT,
  trust_notes TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
  id INTEGER PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_key TEXT NOT NULL,
  status TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 3,
  reason TEXT NOT NULL,
  next_check_date TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(target_type, target_key)
);

CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY,
  target_type TEXT NOT NULL,
  target_key TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL,
  decided_at TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  report_date TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  state_path TEXT,
  UNIQUE(report_date, trigger_type, started_at)
);

CREATE TABLE IF NOT EXISTS run_artifacts (
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL,
  path TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(database: Path) -> None:
    with connect(database) as conn:
        conn.executescript(SCHEMA)


def table_counts(database: Path) -> dict[str, int]:
    tables = [
        "repositories",
        "repo_snapshots",
        "repo_reviews",
        "events",
        "sources",
        "watchlist",
        "decisions",
        "runs",
        "run_artifacts",
    ]
    with connect(database) as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
