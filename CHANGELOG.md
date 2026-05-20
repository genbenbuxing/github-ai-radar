# Changelog

All notable changes to GitHub AI Radar will be documented here.

The project uses semantic versioning.

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
