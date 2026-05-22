# System Design

GitHub AI Radar is a local research system for discovering, tracking, scoring, and auditing AI-related open-source projects plus lightweight external events from RSS/Atom/public news sources.

## Product Boundary

The system focuses on three domains:

1. AI applications: agents, computer use, browser automation, image recognition, long-running autonomous work, memory, RAG, MCP, tool use, workflow automation, and developer tooling.
2. International finance and high technology: AI companies, chips, cloud, capital markets, regulation, supply chains, mergers, earnings, fintech, quantitative workflows, and risk systems.
3. AI biopharma: AI drug discovery, protein design, genomics, clinical trial automation, biology foundation models, pharma collaborations, and regulatory changes.

Phase 1 is read-only. The app does not clone, install, or execute discovered projects. External event collection reads only public feed/query results and stores source links for audit.

## Components

```text
collector       Finds GitHub repositories and public external source candidates.
storage         Persists repositories, snapshots, reviews, events, sources, watchlist, and run artifacts.
reviewer        Performs read-only README/metadata/source-snippet analysis.
scorer          Computes relevance, quality, risk, and trend scores.
reporter        Generates HTML, Markdown, and audit JSON outputs.
recovery        Writes state and logs for visibility. Stage-level resume is planned.
scheduler       Runs the app daily without Codex.
doctor          Diagnoses local GitHub auth, config, database, and scheduler.
llm             Optional OpenAI-compatible API helper for future deeper analysis.
app shell       Local web/native shell for viewing reports, settings, automation, and run state.
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
11. Collect external event candidates through RSS/Atom/public-news queries.
12. Upsert source and event records.
13. Render HTML report, Markdown source file, and audit JSON.
14. Verify files and mark state as completed.

## Checkpoint Model

Each run is split into stages:

```text
init
github_search
github_readme_review
event_sources
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

The current released pipeline includes `init`, `github_search`, `github_readme_review`, `event_sources`, `scoring`, `markdown_render`, `audit_json_render`, `final_verify`, and `completed`. The state file supports UI progress, auditability, and manual diagnosis. True stage-level resume from partial files is a planned stability feature, not an active guarantee in this release.

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
