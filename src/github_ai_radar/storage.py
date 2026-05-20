from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


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


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def create_run(database: Path, report_date: str, trigger_type: str, state_path: str) -> int:
    with connect(database) as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs (report_date, started_at, status, trigger_type, state_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (report_date, _now(), "running", trigger_type, state_path),
        )
        return int(cursor.lastrowid)


def complete_run(database: Path, run_id: int, status: str) -> None:
    with connect(database) as conn:
        conn.execute(
            "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
            (status, _now(), run_id),
        )


def add_run_artifact(database: Path, run_id: int, artifact_type: str, path: str) -> None:
    with connect(database) as conn:
        conn.execute(
            """
            INSERT INTO run_artifacts (run_id, artifact_type, path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, artifact_type, path, _now()),
        )


def upsert_repository(database: Path, repo: dict[str, Any], seen_date: str) -> int:
    with connect(database) as conn:
        conn.execute(
            """
            INSERT INTO repositories (
              full_name, url, description, primary_language, license_key,
              created_at, is_archived, is_fork, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name) DO UPDATE SET
              url = excluded.url,
              description = excluded.description,
              primary_language = excluded.primary_language,
              license_key = excluded.license_key,
              created_at = COALESCE(excluded.created_at, repositories.created_at),
              is_archived = excluded.is_archived,
              is_fork = excluded.is_fork,
              last_seen_at = excluded.last_seen_at
            """,
            (
                repo["full_name"],
                repo["url"],
                repo.get("description"),
                repo.get("language"),
                repo.get("license_key"),
                repo.get("created_at"),
                1 if repo.get("is_archived") else 0,
                1 if repo.get("is_fork") else 0,
                seen_date,
                seen_date,
            ),
        )
        row = conn.execute("SELECT id FROM repositories WHERE full_name = ?", (repo["full_name"],)).fetchone()
        return int(row["id"])


def upsert_snapshot(
    database: Path,
    repository_id: int,
    snapshot_date: str,
    repo: dict[str, Any],
    *,
    entered_candidate_pool: bool,
) -> None:
    with connect(database) as conn:
        conn.execute(
            """
            INSERT INTO repo_snapshots (
              repository_id, snapshot_date, stars, forks, open_issues, pushed_at,
              updated_at, topics_json, entered_candidate_pool
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repository_id, snapshot_date) DO UPDATE SET
              stars = excluded.stars,
              forks = excluded.forks,
              open_issues = excluded.open_issues,
              pushed_at = excluded.pushed_at,
              updated_at = excluded.updated_at,
              topics_json = excluded.topics_json,
              entered_candidate_pool = max(repo_snapshots.entered_candidate_pool, excluded.entered_candidate_pool)
            """,
            (
                repository_id,
                snapshot_date,
                repo.get("stars"),
                repo.get("forks"),
                repo.get("open_issues"),
                repo.get("pushed_at"),
                repo.get("updated_at"),
                json.dumps(repo.get("topics") or [], ensure_ascii=False),
                1 if entered_candidate_pool else 0,
            ),
        )


def _snapshot_on_or_before(conn: sqlite3.Connection, repository_id: int, snapshot_date: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM repo_snapshots
        WHERE repository_id = ? AND snapshot_date <= ?
        ORDER BY snapshot_date DESC
        LIMIT 1
        """,
        (repository_id, snapshot_date),
    ).fetchone()


def compute_growth(database: Path, repository_id: int, report_date: str) -> dict[str, dict[str, Any]]:
    from datetime import date, timedelta

    current_date = date.fromisoformat(report_date)
    windows = {"3d": 3, "7d": 7, "30d": 30}
    with connect(database) as conn:
        current = conn.execute(
            """
            SELECT * FROM repo_snapshots
            WHERE repository_id = ? AND snapshot_date = ?
            """,
            (repository_id, report_date),
        ).fetchone()
        if not current or current["stars"] is None:
            return {key: {"status": "insufficient_history"} for key in windows}
        result: dict[str, dict[str, Any]] = {}
        for key, days in windows.items():
            target_date = (current_date - timedelta(days=days)).isoformat()
            previous = _snapshot_on_or_before(conn, repository_id, target_date)
            if not previous or previous["stars"] is None:
                result[key] = {"status": "insufficient_history"}
                continue
            delta = int(current["stars"]) - int(previous["stars"])
            result[key] = {
                "status": "ok",
                "current_stars": int(current["stars"]),
                "previous_stars": int(previous["stars"]),
                "previous_snapshot_date": previous["snapshot_date"],
                "delta": delta,
            }
        return result


def record_review(database: Path, repository_id: int, run_id: int, score: Any) -> None:
    with connect(database) as conn:
        conn.execute(
            """
            INSERT INTO repo_reviews (
              repository_id, run_id, reviewed_at, score, recommendation,
              readme_quality, usability_notes, risk_notes, scoring_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repository_id,
                run_id,
                _now(),
                score.score,
                score.recommendation,
                score.readme_quality,
                score.usability_notes,
                score.risk_notes,
                json.dumps(score.scoring, ensure_ascii=False),
            ),
        )
