# System Design

GitHub AI Radar is a local research system for discovering, tracking, scoring, and auditing AI-related open-source projects. The data model and report outline reserve space for adjacent finance/high-tech and biopharma events, but the current released app only collects GitHub repository data.

## Product Boundary

The system focuses on three domains:

1. AI applications: agents, computer use, browser automation, image recognition, long-running autonomous work, memory, RAG, MCP, tool use, workflow automation, and developer tooling.
2. International finance and high technology: AI companies, chips, cloud, capital markets, regulation, supply chains, mergers, earnings, fintech, quantitative workflows, and risk systems.
3. AI biopharma: AI drug discovery, protein design, genomics, clinical trial automation, biology foundation models, pharma collaborations, and regulatory changes.

Phase 1 is read-only. The app does not clone, install, or execute discovered projects. External event collection is planned for the next phase and is intentionally labelled as inactive in the UI.

## Components

```text
collector       Finds GitHub repositories. External source collection is planned.
storage         Persists repositories, snapshots, reviews, watchlist, and run artifacts. Event tables are reserved.
reviewer        Performs read-only README/metadata/source-snippet analysis.
scorer          Computes relevance, quality, risk, and trend scores.
reporter        Generates Markdown and audit JSON outputs.
recovery        Writes state and logs for visibility. Stage-level resume is planned.
scheduler       Runs the app daily without Codex.
doctor          Diagnoses local GitHub auth, config, database, and scheduler.
llm             Optional OpenAI-compatible API helper for future deeper analysis.
app shell       Later desktop/web UI for viewing reports and decisions.
```

## Daily Pipeline

1. Resolve report date in GMT+8.
2. Load config and query templates.
3. Create or replace `state/YYYY-MM-DD.state.json` so the UI can show progress.
4. Expand enabled topics into lightweight GitHub queries.
5. Search GitHub candidates using authenticated `gh` or GitHub API.
6. Store raw search payloads.
7. Upsert repository records and daily snapshots.
8. Compute 3-day, 7-day, and 30-day star growth when local history exists.
9. Inspect README, license, releases, topics, file tree, and small source snippets.
10. Score candidates and apply penalties.
11. Render Markdown report and audit JSON.
12. Verify files and mark state as completed.

Planned next phase:

- discover high-signal finance/high-tech and AI-biopharma events from official and high-trust sources
- attach source URLs and trust notes to the audit JSON
- update event watchlists and decisions

## Checkpoint Model

Each run is split into stages:

```text
init
github_search
github_readme_review
scoring
markdown_render
audit_json_render
final_verify
completed
```

After each stage, the app writes:

- current state
- completed stage name
- input counts
- output artifact paths
- error summaries

The current released pipeline includes `init`, `github_search`, `github_readme_review`, `scoring`, `markdown_render`, `audit_json_render`, `final_verify`, and `completed`. The state file supports UI progress, auditability, and manual diagnosis. True stage-level resume from partial files is a planned stability feature, not an active guarantee in this release. `event_sources` is reserved for the planned external-source collector.

## Data Ownership

Local user data belongs outside the public repository:

```text
data/radar.sqlite
reports/github-radar/
reports/github-radar/raw/
reports/github-radar/state/
reports/github-radar/partials/   # reserved for future stage-level resume
reports/github-radar/logs/
```

The public repository should contain code, templates, and docs, not private report archives.
