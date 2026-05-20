from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from string import Template
from typing import Any

import tomli_w

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10
    import tomli as tomllib  # type: ignore[no-redef]

from github_ai_radar.defaults import DEFAULT_FILES


@dataclass(frozen=True)
class AppConfig:
    radar: dict[str, Any]
    paths: dict[str, Any]
    filters: dict[str, Any]
    watchlist: dict[str, Any]
    github_queries: list[dict[str, str]]
    source_queries: list[dict[str, str]]
    weights: dict[str, int]
    penalties: dict[str, int]
    growth: dict[str, int]
    topics: list[dict[str, Any]]
    llm: dict[str, Any]


def _load_toml(path: Path) -> dict[str, Any]:
    if path.exists():
        with path.open("rb") as handle:
            return tomllib.load(handle)
    default = DEFAULT_FILES.get(path.name)
    if default is None:
        return {}
    return tomllib.loads(default)


def _write_toml(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as handle:
        tomli_w.dump(payload, handle)
    tmp.replace(path)
    return path


def load_config_file(root: Path, name: str) -> dict[str, Any]:
    if name not in DEFAULT_FILES and name != "llm.toml":
        raise ValueError(f"Unsupported config file: {name}")
    config_dir = root / "config"
    if name == "llm.toml" and not (config_dir / name).exists():
        return _load_toml(config_dir / "llm.toml.example")
    return _load_toml(config_dir / name)


def write_config_file(root: Path, name: str, payload: dict[str, Any]) -> Path:
    if name not in DEFAULT_FILES and name != "llm.toml":
        raise ValueError(f"Unsupported config file: {name}")
    return _write_toml(root / "config" / name, payload)


def ensure_default_config(root: Path) -> list[Path]:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in DEFAULT_FILES.items():
        path = config_dir / name
        if path.exists():
            continue
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def secrets_path(root: Path) -> Path:
    return root / "config" / "secrets.env"


def load_secrets(root: Path) -> dict[str, str]:
    path = secrets_path(root)
    if not path.exists():
        return {}
    secrets: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            secrets[key] = value
    return secrets


def write_secret(root: Path, key: str, value: str) -> Path:
    if not key:
        raise ValueError("Secret environment variable name is required")
    if any(char.isspace() for char in key) or "=" in key:
        raise ValueError("Secret environment variable name must not contain whitespace or '='")
    path = secrets_path(root)
    secrets = load_secrets(root)
    if value:
        secrets[key] = value
    elif key in secrets:
        del secrets[key]
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Local private secrets for GitHub AI Radar.",
        "# This file is ignored by git. Do not publish it.",
    ]
    for item_key in sorted(secrets):
        escaped = secrets[item_key].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{item_key}="{escaped}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def configured_secret(root: Path, key: str | None) -> str | None:
    if not key:
        return None
    import os

    return os.environ.get(key) or load_secrets(root).get(key)


def load_config(root: Path) -> AppConfig:
    config_dir = root / "config"
    radar = _load_toml(config_dir / "radar.toml")
    queries = _load_toml(config_dir / "queries.toml")
    scoring = _load_toml(config_dir / "scoring.toml")
    topics = _load_toml(config_dir / "topics.toml")
    llm = _load_toml(config_dir / "llm.toml")
    return AppConfig(
        radar=radar.get("radar", {}),
        paths=radar.get("paths", {}),
        filters=radar.get("filters", {}),
        watchlist=radar.get("watchlist", {}),
        github_queries=queries.get("github_queries", []),
        source_queries=queries.get("source_queries", []),
        weights=scoring.get("weights", {}),
        penalties=scoring.get("penalties", {}),
        growth=scoring.get("growth", {}),
        topics=topics.get("topics", []),
        llm=llm.get("llm", {}),
    )


def llm_status(root: Path) -> dict[str, Any]:
    llm_path = root / "config" / "llm.toml"
    example_path = root / "config" / "llm.toml.example"
    config = _load_toml(llm_path).get("llm", {}) if llm_path.exists() else {}
    api_key_env = config.get("api_key_env")
    api_key = configured_secret(root, api_key_env)
    return {
        "configured": llm_path.exists(),
        "example_exists": example_path.exists(),
        "enabled": bool(config.get("enabled", False)),
        "provider": config.get("provider"),
        "base_url": config.get("base_url"),
        "model": config.get("model"),
        "api_key_env": api_key_env,
        "timeout_seconds": config.get("timeout_seconds"),
        "api_key_present": bool(api_key),
        "secrets_file": str(secrets_path(root)),
        "secrets_file_exists": secrets_path(root).exists(),
    }


def render_query(template: str, report_date: date) -> str:
    values = {
        "today": report_date.isoformat(),
        "date_minus_7": (report_date - timedelta(days=7)).isoformat(),
        "date_minus_14": (report_date - timedelta(days=14)).isoformat(),
        "date_minus_30": (report_date - timedelta(days=30)).isoformat(),
        "date_minus_90": (report_date - timedelta(days=90)).isoformat(),
        "date_minus_120": (report_date - timedelta(days=120)).isoformat(),
    }
    return Template(template).safe_substitute(values)
