# Contributing

Thanks for helping improve GitHub AI Radar.

## Development Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e . pytest
github-ai-radar doctor
python -m pytest -q
```

## Principles

- Keep the default workflow local-first and read-only.
- Do not add features that execute discovered repositories in phase 1.
- Prefer simple configuration over plugin complexity.
- Keep reports auditable: cite queries, source URLs, scoring notes, and generated files.
- Avoid committing local databases, reports, API keys, or personal watchlists.

## Pull Requests

Please include:

- What changed
- Why it matters
- How it was tested
- Any migration or security implications
