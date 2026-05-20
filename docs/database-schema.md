# Database Schema

The first production database is SQLite.

## Tables

### schema_migrations

Tracks local SQLite schema versions so future releases can migrate data safely.

### repositories

Stable repository identity and mostly static metadata.

### repo_snapshots

Daily point-in-time metrics for stars, forks, pushed date, topics, and candidate-pool membership. This table powers 3-day, 7-day, and 30-day growth.

### repo_reviews

Per-run read-only analysis, including score, recommendation, README quality, usability notes, risk notes, and scoring details.

### events

Reserved for the planned external finance/high-tech and AI-biopharma event collector. The current release does not populate this table.

### sources

Reserved source URL metadata, publisher, source type, fetch time, and trust notes for the planned event collector. Current audit files only include GitHub repository and artifact URLs.

### watchlist

Long-term tracking queue for projects and events.

### decisions

Human or system decisions such as ignore, watch, deep read, or trial later.

### runs

Run-level state for manual, scheduled, or recovery-triggered executions.

### run_artifacts

Generated files linked to a run.

## Local Data Policy

The SQLite database should not be committed to the public repository. Users may export redacted data later if they want to publish benchmarks or public reports.
