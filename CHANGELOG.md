# Changelog

All notable changes to GitHub AI Radar will be documented here.

The project uses semantic versioning.

## [0.5.0] - 2026-05-22

### Added

- Active external-source collector for RSS/Atom/public-news event candidates.
- Persisted external source and event records in SQLite.
- Editable external-source queries and source keywords in the no-code settings page.
- External event sections in Markdown reports and audit JSON.
- HTML reading report export and an in-app Markdown fallback reader for older reports.
- Report center cards, system health checks, clearer task progress, stage explanations, and folded advanced settings for no-code users.
- Pixel cat branding in the local dashboard and generated macOS app icon.

## [0.4.1] - 2026-05-20

### Fixed

- Clarified no-code UI copy so external source settings are shown as planned fields instead of active report controls.
- Preserved reserved `source_queries` when editing active GitHub queries from the dashboard.
- Marked failed pipeline runs in state JSON and the local run table so the UI does not leave interrupted jobs looking active.
- Aligned README and docs with the current product boundary: GitHub project radar now, official-source event collection later.

## [0.4.0] - 2026-05-20

### Added

- Direct settings editing in the dashboard for run parameters, LLM API, topics, GitHub queries, and scoring.
- Private local `config/secrets.env` support for no-code LLM API key setup.
- Native macOS WebKit app window instead of opening the dashboard in an external browser when Swift is available.

## [0.3.2] - 2026-05-20

### Added

- Friendlier settings guide for non-coders, including what to change, where to change it, and what to do after saving.
- LLM setup instructions directly in the settings page.
- README user guide covering app usage, LLM setup, schedules, result harvesting, run monitoring, and CLI equivalents.

## [0.3.1] - 2026-05-20

### Added

- No-code local console UI with clear entries for report generation, results, settings, and automation.
- Manual report generation form in the dashboard.
- Automation page with launchd status, schedule controls, stage timeline, and logs.
- Settings page that shows collection directions, GitHub queries, scoring, and LLM API status.
- Local buttons for opening report, config, log, and data folders from the app.

## [0.3.0] - 2026-05-20

### Added

- Local HTML dashboard for browsing report status, generated Markdown, audit JSON, and recent repository reviews.
- `serve` command for starting the dashboard on `127.0.0.1`.
- macOS `.app` launcher install/status/uninstall commands.
- README instructions for opening GitHub AI Radar as a local app.

## [0.2.0] - 2026-05-20

### Added

- GitHub repository discovery through authenticated `gh`.
- SQLite repository, snapshot, review, run, and artifact storage.
- 3-day, 7-day, and 30-day star-growth calculation from local snapshots.
- Markdown and audit JSON report generation.
- macOS `launchd` schedule install/status/uninstall commands.
- `doctor` diagnostics command.
- Optional OpenAI-compatible LLM configuration example.
- Configurable collection topics and query templates.

## [0.1.0] - 2026-05-20

### Added

- Initial installable CLI scaffold.
- SQLite schema draft.
- Product and system design docs.
