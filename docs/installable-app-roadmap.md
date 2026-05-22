# Installable App Roadmap

The long-term goal is a stable local app that does not depend on Codex automation.

## Stage 1: CLI Package

Install with:

```bash
pipx install github-ai-radar
```

Run with:

```bash
github-ai-radar init
github-ai-radar run --once
github-ai-radar status
```

The CLI owns local directories, SQLite, reports, and run state files.

Implemented in v0.2:

- GitHub candidate search through authenticated `gh`
- SQLite repository and snapshot storage
- 3-day, 7-day, and 30-day growth calculation from local history
- HTML, Markdown, and audit JSON report generation
- macOS `launchd` install/status/uninstall commands

## Stage 2: Native Scheduler Integration

The app should generate and install native schedules:

- macOS: `launchd` user agent
- Linux: `systemd --user` timer
- Windows: Task Scheduler

The scheduled command should be:

```bash
github-ai-radar run --once --root /path/to/workspace
```

Codex can still read and discuss reports, but it is no longer responsible for starting the job.

## Stage 3: Local Service

Add a long-running service mode:

```bash
github-ai-radar serve
```

Responsibilities:

- expose local report index
- show watchlist and decisions
- provide health status
- avoid duplicate concurrent runs

Implemented in v0.3-v0.4:

- local dashboard on `127.0.0.1`
- manual report generation from the UI
- HTML report, Markdown source, audit JSON, status, stage, and log browsing
- direct settings forms for run parameters, topics, GitHub queries, external source queries, scoring, and LLM API
- health checks, report center cards, progress bars, stage explanations, and folded advanced settings

Still planned:

- service-owned timezone-aware scheduler loop
- richer watchlist and decision views

## Stage 4: Desktop App

Wrap the local service with a small desktop shell.

Candidate approaches:

- Tauri front end + Python sidecar
- Electron front end + Python service
- Native Swift app for macOS first

The desktop app should manage:

- configuration
- report browsing
- watchlist decisions
- scheduler install/uninstall
- manual run/retry
- local backup/export

Implemented in v0.4:

- macOS `.app` installed under `~/Applications`
- native WebKit app window when Swift is available
- fallback launcher when Swift is not available

Implemented in v0.5:

- generated pixel cat app icon
- active external-source event collector inside the app pipeline

Still planned:

- signed and notarized distributable app package
- fully self-contained runtime bundle that does not depend on a developer Python environment
- drag-and-drop `.dmg` or `.pkg` installer

## Stage 5: Optional Codex Integration

Codex becomes optional:

- summarize today's report
- perform deeper read-only review
- draft follow-up plans
- inspect suspicious candidates

The core app must continue to collect data and generate baseline reports when Codex is unavailable.
