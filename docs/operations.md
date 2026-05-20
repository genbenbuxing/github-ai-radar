# Operations

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
github-ai-radar init
github-ai-radar status
```

## Daily Manual Run

```bash
github-ai-radar run --once --root .
```

## Scheduling Target

The desired report time is 10:00 GMT+8.

For a machine using America/Los_Angeles time during daylight saving time, this corresponds to 19:00 on the previous calendar day. Native schedulers should store the intended timezone explicitly where possible.

## Artifacts

Generated artifacts should live outside git history:

```text
data/radar.sqlite
reports/github-radar/YYYY-MM-DD.md
reports/github-radar/YYYY-MM-DD.audit.json
reports/github-radar/state/YYYY-MM-DD.state.json
reports/github-radar/raw/github/YYYY-MM-DD.json
reports/github-radar/raw/sources/YYYY-MM-DD.json
```

## Health Checks

A completed run must satisfy:

- Markdown report exists and is non-empty.
- Audit JSON exists and parses.
- State JSON exists and says `completed`.
- Key sections are present in Markdown.
- Raw source records are linked from the audit JSON.

## Safety Rules

- Do not clone discovered repositories in phase 1.
- Do not run install scripts from discovered repositories.
- Do not pass private tokens into discovered tools.
- Prefer official, regulatory, company, or primary sources for events.
- Separate facts from inference in every report.
