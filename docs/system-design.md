# System Design

GitHub AI Radar is a local research system for discovering, tracking, scoring, and auditing AI-related open-source projects and adjacent high-signal events.

## Product Boundary

The system focuses on three domains:

1. AI applications: agents, computer use, browser automation, image recognition, long-running autonomous work, memory, RAG, MCP, tool use, workflow automation, and developer tooling.
2. International finance and high technology: AI companies, chips, cloud, capital markets, regulation, supply chains, mergers, earnings, fintech, quantitative workflows, and risk systems.
3. AI biopharma: AI drug discovery, protein design, genomics, clinical trial automation, biology foundation models, pharma collaborations, and regulatory changes.

Phase 1 is read-only. The app does not clone, install, or execute discovered projects.

## Components

```text
collector       Finds GitHub repositories and external sources.
storage         Persists repositories, snapshots, events, reviews, watchlist, and run artifacts.
reviewer        Performs read-only README/metadata/source-snippet analysis.
scorer          Computes relevance, quality, risk, and trend scores.
reporter        Generates Markdown and audit JSON outputs.
recovery        Maintains state, partials, logs, and resumable stages.
scheduler       Runs the app daily without Codex.
doctor          Diagnoses local GitHub auth, config, database, and scheduler.
llm             Optional OpenAI-compatible API helper for future deeper analysis.
app shell       Later desktop/web UI for viewing reports and decisions.
```

## Daily Pipeline

1. Resolve report date in GMT+8.
2. Load config and query templates.
3. Resume from `state/YYYY-MM-DD.state.json` if present.
4. Expand enabled topics into lightweight GitHub queries.
5. Search GitHub candidates using authenticated `gh` or GitHub API.
6. Store raw search payloads.
7. Upsert repository records and daily snapshots.
8. Compute 3-day, 7-day, and 30-day star growth when local history exists.
9. Inspect README, license, releases, topics, file tree, and small source snippets.
10. Discover high-signal finance/high-tech and AI-biopharma events.
11. Score candidates and apply penalties.
12. Update watchlist and decisions.
13. Render Markdown report and audit JSON.
14. Verify files and mark state as completed.

## Recovery Model

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

If interrupted, the next run resumes from the last successful stage and keeps existing partials unless they fail validation.

## Data Ownership

Local user data belongs outside the public repository:

```text
data/radar.sqlite
reports/github-radar/
reports/github-radar/raw/
reports/github-radar/state/
reports/github-radar/partials/
reports/github-radar/logs/
```

The public repository should contain code, templates, and docs, not private report archives.
