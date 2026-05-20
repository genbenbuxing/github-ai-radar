# Security Policy

GitHub AI Radar is local-first and read-only by default, but it handles URLs, repository metadata, optional API configuration, and local reports. Treat the local data directory as private.

## Supported Versions

Security updates target the latest minor version while the project is pre-1.0.

## Reporting a Vulnerability

Open a GitHub issue if the report does not contain sensitive details. For sensitive reports, contact the maintainer privately before publishing details.

## Safety Expectations

- Do not commit `config/llm.toml` or raw API keys.
- Do not commit `data/` or `reports/`.
- Do not run code from discovered repositories in phase 1.
- Do not pass private environment variables into discovered projects.
- Use low-privilege tokens where possible.

## LLM API Keys

The app reads API keys only from environment variables named in `config/llm.toml`. The example config is safe to commit; your real config is ignored by git.
