# GitHub AI Radar

**A local, auditable radar for GitHub AI projects and frontier AI signals.**

GitHub AI Radar helps you discover and track open-source projects in AI applications, agents, computer use, memory, RAG, MCP, image recognition, AI biopharma, and high-tech finance. It stores structured snapshots locally, scores candidates conservatively, and generates daily Markdown plus audit JSON reports.

The app is intentionally local-first. Your database, reports, watchlist, and API configuration stay on your machine.

## What It Does

- Finds new and high-signal GitHub repositories with the authenticated GitHub CLI.
- Reads repository metadata and README content without cloning or executing code.
- Stores daily repository snapshots in SQLite.
- Computes 3-day, 7-day, and 30-day star growth from local history.
- Scores projects using relevance, usability evidence, README quality, maintenance, community signal, license, novelty, growth, and safety.
- Generates a readable daily Markdown report and a machine-readable audit JSON file.
- Installs a macOS `launchd` schedule so daily runs can happen without Codex.
- Supports optional local LLM configuration for future deeper analysis through OpenAI-compatible APIs.

## Safety Model

Phase 1 is read-only:

- No repository cloning.
- No dependency installation from discovered projects.
- No third-party project execution.
- No browser cookies, SSH keys, or personal files are exposed.
- API keys are read from environment variables, not committed config files.

## Quickstart

Requirements:

- Python 3.9+
- GitHub CLI (`gh`)
- Logged-in GitHub CLI account:

```bash
gh auth login
```

Install from a local checkout:

```bash
git clone https://github.com/genbenbuxing/github-ai-radar.git
cd github-ai-radar
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Initialize local state:

```bash
github-ai-radar init
github-ai-radar doctor
```

Run a small manual report:

```bash
github-ai-radar run --once --max-candidates 30 --deep-review-limit 8
```

Generated files:

```text
data/radar.sqlite
reports/github-radar/YYYY-MM-DD.md
reports/github-radar/YYYY-MM-DD.audit.json
reports/github-radar/state/YYYY-MM-DD.state.json
reports/github-radar/raw/github/YYYY-MM-DD.json
```

## Daily Schedule

Install a macOS launchd schedule for 10:00 GMT+8:

```bash
github-ai-radar schedule install --timezone Asia/Shanghai --hour 10 --minute 0
github-ai-radar schedule status
```

Uninstall:

```bash
github-ai-radar schedule uninstall
```

Current limitation: macOS `launchd` stores local wall-clock time. The installer converts the requested report timezone to your current local time at install time. A future service mode will handle timezone and DST more precisely.

## Optional LLM Configuration

LLM use is optional and disabled by default.

```bash
cp config/llm.toml.example config/llm.toml
```

Then edit `config/llm.toml`:

```toml
[llm]
enabled = true
provider = "openai_compatible"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"
api_key_env = "OPENAI_API_KEY"
```

Set your key in the environment:

```bash
export OPENAI_API_KEY="..."
```

Do not put raw API keys in config files. `config/llm.toml` is ignored by git.

## Add More Collection Directions

Edit:

```text
config/topics.toml
config/queries.toml
```

`topics.toml` is for human-readable collection directions. `queries.toml` controls actual GitHub queries today. This keeps customization simple without a plugin system.

## Architecture

```text
config/                 User-editable settings, queries, topics, and scoring
src/github_ai_radar/    Installable Python package
docs/                   System design, operations, release notes
data/                   Local SQLite database, ignored by git
reports/                Local generated reports, ignored by git
```

Core modules:

- `github_client`: GitHub search and read-only repository inspection.
- `storage`: SQLite schema, snapshots, reviews, events, watchlist, run records.
- `scorer`: Conservative scoring and trend calculation.
- `reporter`: Markdown and audit JSON rendering.
- `scheduler`: macOS launchd integration.
- `doctor`: local setup diagnostics.
- `llm`: optional OpenAI-compatible chat completion helper.

## Roadmap

- v0.3: stronger recovery, run lock, retries, `run --resume`, richer watchlist.
- v0.4: official-source event collection for AI finance/high-tech and AI biopharma.
- v0.5: local report index and HTML report browsing.
- v0.6: package release automation and PyPI distribution.
- v1.0: stable local app with scheduler, reports, audit trail, and optional LLM-assisted analysis.

## Documentation

- [System Design](docs/system-design.md)
- [Installable App Roadmap](docs/installable-app-roadmap.md)
- [Operations](docs/operations.md)
- [Scoring Rubric](docs/scoring-rubric.md)
- [Database Schema](docs/database-schema.md)
- [Release Checklist](docs/release-checklist.md)

## License

MIT
