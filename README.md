# GitHub AI Radar

**A local, auditable radar for GitHub AI projects.**

GitHub AI Radar helps you discover and track open-source projects in AI applications, agents, computer use, memory, RAG, MCP, image recognition, AI biopharma, and high-tech finance. It stores structured snapshots locally, scores candidates conservatively, and generates daily Markdown plus audit JSON reports.

Current release boundary: the working product is a GitHub project radar. Finance/high-tech and biopharma event sections are present in the report structure, but automatic external news, announcement, regulatory, and paper collection is not enabled yet. Those external-source settings are kept as next-stage planning fields so the app does not pretend to have collected sources it has not actually read.

The app is intentionally local-first. Your database, reports, watchlist, and API configuration stay on your machine.

## What It Does

- Finds new and high-signal GitHub repositories with the authenticated GitHub CLI.
- Reads repository metadata and README content without cloning or executing code.
- Stores daily repository snapshots in SQLite.
- Computes 3-day, 7-day, and 30-day star growth from local history.
- Scores projects using relevance, usability evidence, README quality, maintenance, community signal, license, novelty, growth, and safety.
- Generates a readable daily Markdown report and a machine-readable audit JSON file.
- Serves a local HTML dashboard for browsing reports, audit files, and recent repository reviews.
- Installs a macOS `.app` launcher so the dashboard can be opened from Finder, Spotlight, or Launchpad.
- Installs a macOS `launchd` schedule so daily runs can happen without Codex.
- Supports optional local LLM configuration for future deeper analysis through OpenAI-compatible APIs.
- Keeps external finance, high-tech, and biopharma source queries as visible planned fields, but does not use them until the official-source collector is implemented.

## Safety Model

Phase 1 is read-only:

- No repository cloning.
- No dependency installation from discovered projects.
- No third-party project execution.
- No browser cookies, SSH keys, or personal files are exposed.
- API keys are read from environment variables or local `config/secrets.env`, not committed config files.

## Quickstart

Requirements:

- Python 3.9+
- GitHub CLI (`gh`)
- Logged-in GitHub CLI account:

```bash
gh auth login
```

Install from the release tag with `pipx`:

```bash
pipx install "git+https://github.com/genbenbuxing/github-ai-radar.git@v0.4.1"
```

Or install from a local checkout:

```bash
git clone https://github.com/genbenbuxing/github-ai-radar.git
cd github-ai-radar
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

You can also download the wheel from GitHub Releases and install it directly:

```bash
python -m pip install github_ai_radar-0.4.1-py3-none-any.whl
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

## Local Dashboard And App

Open the dashboard directly from the command line:

```bash
github-ai-radar serve --open
```

The dashboard runs locally at:

```text
http://127.0.0.1:8765/
```

Install the macOS app:

```bash
github-ai-radar app install
```

Then open **GitHub AI Radar** from `~/Applications`, Finder, Spotlight, or Launchpad. On macOS systems with Swift available at install time, this creates a native WebKit app window. The dashboard URL still exists locally for automation and debugging.

The local app is organized for non-coders:

- **操作台**: generate a report now, see the latest task stage, and jump to common actions.
- **结果**: open generated Markdown reports, audit JSON files, and recent project reviews.
- **参数**: edit collection directions, GitHub queries, scoring rules, run settings, and LLM API directly in the app.
- **自动化**: enable or stop the daily schedule, inspect run stages, and open logs.

Check or remove the app:

```bash
github-ai-radar app status
github-ai-radar app uninstall
```

## User Guide

### 1. Open The App

After installation, open **GitHub AI Radar** from `~/Applications`, Finder, Spotlight, or Launchpad.

The app opens its own local window. The same UI is also available at:

```text
http://127.0.0.1:8765/
```

The app has four main pages:

- **操作台**: run a report now and see the latest run stage.
- **结果**: open generated reports, audit JSON files, and recent project reviews.
- **参数**: edit collection directions, GitHub queries, scoring, run settings, and LLM settings directly in the app.
- **自动化**: enable or stop the daily schedule, inspect stages, and open logs.

### 2. Generate A Report Now

In the app:

1. Open **操作台**.
2. Check or edit the report timezone, candidate count, and deep-read count.
3. Click **立即生成报告**.
4. Open **自动化** to watch the stages.
5. Open **结果** to read the finished report.

Command-line equivalent:

```bash
github-ai-radar run --once --timezone Asia/Shanghai --max-candidates 100 --deep-review-limit 10
```

### 3. View Results

In the app:

1. Open **结果**.
2. Click **打开报告** to read the Markdown report.
3. Click **审计 JSON** to inspect the machine-readable audit record.
4. Click **打开报告文件夹** to see all local report artifacts.

Report files are stored locally:

```text
reports/github-radar/YYYY-MM-DD.md
reports/github-radar/YYYY-MM-DD.audit.json
reports/github-radar/state/YYYY-MM-DD.state.json
reports/github-radar/raw/github/YYYY-MM-DD.json
```

The Markdown report is for reading. The audit JSON is for traceability: GitHub queries, checked repositories, scoring notes, growth evidence, artifacts, risks, and uncertainty. External event source URLs will appear after the official-source collector is implemented.

### 4. Edit Collection Directions

In the app:

1. Open **参数**.
2. Use the **设置向导** and **常见目标对照表**.
3. Edit the **采集方向** form directly in the page.
4. Click **保存采集方向**.
5. Return to **操作台** and generate a report to apply the new settings.

Typical edit:

```toml
[[topics]]
name = "custom"
enabled = true
description = "My extra research direction."
github_terms = [
  "my keyword",
  "another keyword"
]
source_terms = [
  "my external source query for a later release"
]
```

Use **采集方向** when you want to describe what you care about. Use **查询规则** only when you want precise GitHub search syntax such as `stars:>=50`, `created:>=${date_minus_14}`, `pushed:>=${date_minus_30}`, or `topic:ai-agent`.

In the current release, `github_terms` affect the next report immediately. `source_terms` are saved for the planned external event radar and do not change today's report.

### 5. Configure Your Own LLM API

LLM use is optional. The radar can run without it.

In the app:

1. Open **参数**.
2. Find **LLM API**.
3. Enable LLM, then fill in Provider, Base URL, model, timeout, and API Key.
4. Click **保存 LLM 设置**.

The app saves public configuration to `config/llm.toml`:

```toml
[llm]
enabled = true
provider = "openai_compatible"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"
api_key_env = "OPENAI_API_KEY"
timeout_seconds = 60
```

The API Key itself is saved to local private `config/secrets.env`, which is ignored by git. You can also leave the API Key field blank and provide the key through the environment variable named by `api_key_env`.

For a temporary terminal session:

```bash
export OPENAI_API_KEY="..."
github-ai-radar serve --open
```

For scheduled runs on macOS, the app can read `config/secrets.env`, so no-code users do not need to manage shell environment variables. Do not put raw API keys into `config/llm.toml`.

After changing LLM settings, run a new report from **操作台**.

### 6. Create A Daily Schedule

In the app:

1. Open **自动化**.
2. Set report timezone, hour, and minute.
3. Click **启用每日任务**.
4. Check that the page shows the schedule as enabled.

Command-line equivalent for 10:00 GMT+8:

```bash
github-ai-radar schedule install --timezone Asia/Shanghai --hour 10 --minute 0
github-ai-radar schedule status
```

Stop the schedule:

```bash
github-ai-radar schedule uninstall
```

macOS stores `launchd` schedules as local wall-clock time. The installer converts the requested report timezone to your current local time when installing the task.

### 7. Monitor A Run

In the app:

1. Open **自动化**.
2. Read **任务阶段**.
3. Open **日志** if a run fails or appears stuck.

Stages:

- **准备环境**: create folders and database.
- **检索 GitHub**: run GitHub searches.
- **阅读 README**: read repository metadata and README snippets.
- **评分排序**: score candidates.
- **生成报告**: write the Markdown report.
- **生成审计记录**: write the audit JSON.
- **验证文件**: check report artifacts.
- **完成**: the report is ready.

Logs are stored in:

```text
reports/github-radar/logs/
```

## CLI Reference For Advanced Users

The local app is the recommended interface. These commands are useful for automation, debugging, or remote sessions.

Initialize:

```bash
github-ai-radar init
github-ai-radar doctor
```

Run once:

```bash
github-ai-radar run --once --timezone Asia/Shanghai --max-candidates 100 --deep-review-limit 10
```

Start the dashboard:

```bash
github-ai-radar serve --open
```

Install or remove the macOS app:

```bash
github-ai-radar app install
github-ai-radar app status
github-ai-radar app uninstall
```

Install or remove the daily schedule:

```bash
github-ai-radar schedule install --timezone Asia/Shanghai --hour 10 --minute 0
github-ai-radar schedule status
github-ai-radar schedule uninstall
```

## Architecture

```text
config/                 User-editable settings, queries, topics, and scoring
src/github_ai_radar/    Installable Python package
docs/                   System design, operations, release notes
data/                   Local SQLite database, ignored by git
reports/                Local generated reports, ignored by git
```

Current data boundary: `github_client`, `storage`, `scorer`, `reporter`, `web`, `app_launcher`, `scheduler`, and `doctor` are active. External source/event collection tables and config fields are reserved for v0.5 and should be read as roadmap placeholders in this release.

Core modules:

- `github_client`: GitHub search and read-only repository inspection.
- `storage`: SQLite schema, snapshots, reviews, events, watchlist, run records.
- `scorer`: Conservative scoring and trend calculation.
- `reporter`: Markdown and audit JSON rendering.
- `web`: local HTML dashboard and status API.
- `app_launcher`: macOS `.app` launcher generation.
- `scheduler`: macOS launchd integration.
- `doctor`: local setup diagnostics.
- `llm`: optional OpenAI-compatible chat completion helper.

## Roadmap

- v0.4.1: clearer no-code UI copy, removal of inactive external-source edit traps, and release documentation alignment.
- v0.4: direct dashboard settings and native macOS WebKit app window.
- v0.5: official-source event collection for AI finance/high-tech and AI biopharma.
- v0.6: richer tracking views, watchlist history, and trend charts.
- v0.7: package release automation and PyPI distribution.
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
