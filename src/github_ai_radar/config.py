from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from string import Template
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10
    import tomli as tomllib  # type: ignore[no-redef]


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


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_config(root: Path) -> AppConfig:
    config_dir = root / "config"
    radar = _load_toml(config_dir / "radar.toml")
    queries = _load_toml(config_dir / "queries.toml")
    scoring = _load_toml(config_dir / "scoring.toml")
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
    )


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
