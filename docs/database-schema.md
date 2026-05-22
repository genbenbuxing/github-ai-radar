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

External finance/high-tech, AI-biopharma, and AI application ecosystem event candidates. Each row stores event date, domain, title, source URL, source name, summary, facts, and inference notes.

### sources

Source URL metadata, publisher, source type, fetch time, and trust notes for the external event collector.

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
