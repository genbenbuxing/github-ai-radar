# Operations

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
github-ai-radar init
github-ai-radar status
github-ai-radar doctor
```

`init` creates local directories, initializes SQLite, and writes default config files when they do not already exist.

## Daily Manual Run

```bash
github-ai-radar run --once --root . --max-candidates 30 --deep-review-limit 8
```

## Scheduling Target

The desired report time is 10:00 GMT+8.

For a machine using America/Los_Angeles time during daylight saving time, this corresponds to 19:00 on the previous calendar day. Native schedulers should store the intended timezone explicitly where possible.

Install the macOS launchd schedule:

```bash
github-ai-radar --root /path/to/github-ai-radar schedule install --timezone Asia/Shanghai --hour 10 --minute 0
github-ai-radar schedule status
```

Uninstall:

```bash
github-ai-radar schedule uninstall
```

Current limitation: `launchd` stores local wall-clock time, not the target timezone. The installer converts the requested report timezone to local wall-clock time when installing the task.

## Local Dashboard And App

The dashboard can be started directly:

```bash
github-ai-radar serve --open
```

Install the macOS app wrapper:

```bash
github-ai-radar app install
github-ai-radar app status
```

When Swift is available at install time, the app opens in a native WebKit window. The same local dashboard remains available at `http://127.0.0.1:8765/` for debugging and automation.

## Optional LLM API

Copy the example config and keep the real file local:

```bash
cp config/llm.toml.example config/llm.toml
```

Set `enabled = true`, choose an OpenAI-compatible `base_url` and `model`, then either save the key through the app UI or export the environment variable named by `api_key_env`.

```bash
export OPENAI_API_KEY="..."
```

The app stores no-code UI keys in local private `config/secrets.env`, which is ignored by git. The app should never store raw API keys in git-tracked files.

## Custom Collection Directions

Edit:

```text
config/topics.toml
config/queries.toml
```

`topics.toml` is the friendly place to add directions. Enabled topic `github_terms` contribute simple GitHub searches. `queries.toml` is the precise place for curated GitHub search strings.

Current release boundary: external source terms and `source_queries` are preserved for the planned event-source collector, but they do not change the generated report yet. GitHub terms and GitHub queries are the active collection controls.

## Artifacts

Generated artifacts should live outside git history:

```text
data/radar.sqlite
reports/github-radar/YYYY-MM-DD.md
reports/github-radar/YYYY-MM-DD.audit.json
reports/github-radar/state/YYYY-MM-DD.state.json
reports/github-radar/raw/github/YYYY-MM-DD.json
```

## Health Checks

A completed run must satisfy:

- Markdown report exists and is non-empty.
- Audit JSON exists and parses.
- State JSON exists and says `completed`.
- Key sections are present in Markdown.
- Raw GitHub search records are linked from the audit JSON artifacts.

## Safety Rules

- Do not clone discovered repositories in phase 1.
- Do not run install scripts from discovered repositories.
- Do not pass private tokens into discovered tools.
- Prefer official, regulatory, company, or primary sources when the planned event collector is added.
- Separate facts from inference in every report.
