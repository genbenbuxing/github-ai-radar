# GitHub AI Radar

Local, auditable research radar for AI application projects, high-tech finance events, and AI biopharma collaboration signals.

The project is designed to start as a lightweight CLI app and grow into an installable local application that can run without Codex. Codex can still be used as an analysis assistant, but the long-term system owns its own storage, scheduling, recovery, and reporting.

## Goals

- Discover new and high-signal GitHub repositories in AI applications, agents, computer use, memory, image recognition, RAG, MCP, workflow automation, and developer tooling.
- Track international finance and high-tech events related to AI, chips, cloud, capital markets, regulation, and supply chains.
- Track biopharma developments where AI collaborates with drug discovery, clinical development, biology foundation models, genomics, and pharma workflows.
- Store structured historical data locally, including repository snapshots and source citations.
- Generate daily Markdown reports and machine-readable audit JSON files.
- Recover cleanly from interrupted runs.
- Eventually run as an installable app with a local scheduler, independent of Codex automation.

## Current Status

This repository is in the early app stage. The CLI can initialize local storage, collect GitHub repository candidates with `gh`, store snapshots in SQLite, compute available growth metrics, and generate Markdown/audit JSON reports.

```bash
pipx install .
github-ai-radar init
github-ai-radar run --once --max-candidates 30 --deep-review-limit 8
github-ai-radar status
```

Install a local macOS schedule:

```bash
github-ai-radar schedule install --timezone Asia/Shanghai --hour 10 --minute 0
github-ai-radar schedule status
```

The scheduler uses macOS `launchd` and converts the desired report time to the machine's local timezone at install time. A future service mode will handle timezone/DST more precisely.

## Architecture

```text
config/                 User-editable radar settings and scoring rules
src/github_ai_radar/    Installable Python package
docs/                   System design, operations, and roadmap
data/                   Local SQLite database, ignored by git
reports/                Local generated reports, ignored by git
```

Core modules:

- `github_client`: GitHub search and read-only repository inspection.
- `source_client`: External event source discovery and citation collection.
- `storage`: SQLite schema, repository snapshots, events, reviews, watchlist, and run records.
- `scorer`: Conservative ranking and trend calculation.
- `reporter`: Markdown and audit JSON rendering.
- `recovery`: State files, partials, logs, and resume-safe execution.
- `scheduler`: Local scheduling through launchd/systemd/Task Scheduler.

## Safety Boundary

Phase 1 is read-only:

- Do not clone repositories.
- Do not install dependencies from discovered projects.
- Do not execute third-party project code.
- Do not expose browser cookies, SSH keys, personal tokens, or private files.
- Only inspect repository metadata, README files, licenses, releases, topics, file trees, and small source snippets.

## Documentation

- [System Design](docs/system-design.md)
- [Installable App Roadmap](docs/installable-app-roadmap.md)
- [Operations](docs/operations.md)
- [Scoring Rubric](docs/scoring-rubric.md)
- [Database Schema](docs/database-schema.md)
