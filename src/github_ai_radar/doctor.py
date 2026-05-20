from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from github_ai_radar.config import llm_status, load_config
from github_ai_radar.paths import RadarPaths
from github_ai_radar.scheduler import launchd_status
from github_ai_radar.storage import schema_version, table_counts


def _run(command: list[str]) -> tuple[bool, str]:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, output


def run_doctor(root: Path) -> dict[str, Any]:
    paths = RadarPaths.from_root(root)
    gh_path = shutil.which("gh")
    gh_ok = False
    gh_output = "gh not found"
    if gh_path:
        gh_ok, gh_output = _run(["gh", "auth", "status"])

    config = load_config(root)
    db_exists = paths.database.exists()
    counts = table_counts(paths.database) if db_exists else {}
    return {
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
        },
        "root": str(root),
        "paths": {
            "data_dir": str(paths.data_dir),
            "reports_dir": str(paths.reports_dir),
            "database": str(paths.database),
            "database_exists": db_exists,
        },
        "github_cli": {
            "path": gh_path,
            "authenticated": gh_ok,
            "status": gh_output,
        },
        "configuration": {
            "github_queries": len(config.github_queries),
            "source_queries": len(config.source_queries),
            "topics": len(config.topics),
            "llm": llm_status(root),
        },
        "database": {
            "schema": schema_version(paths.database),
            "counts": counts,
        },
        "scheduler": launchd_status(),
    }
