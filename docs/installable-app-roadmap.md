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

The CLI owns local directories, SQLite, reports, and recovery state.

Implemented in v0.2:

- GitHub candidate search through authenticated `gh`
- SQLite repository and snapshot storage
- 3-day, 7-day, and 30-day growth calculation from local history
- Markdown and audit JSON report generation
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

- run scheduler loop
- expose local report index
- show watchlist and decisions
- provide health status
- avoid duplicate concurrent runs

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

## Stage 5: Optional Codex Integration

Codex becomes optional:

- summarize today's report
- perform deeper read-only review
- draft follow-up plans
- inspect suspicious candidates

The core app must continue to collect data and generate baseline reports when Codex is unavailable.
