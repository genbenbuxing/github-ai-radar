from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo


LABEL = "com.github-ai-radar.daily"


def launch_agent_path(label: str = LABEL) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _python_executable() -> str:
    # The console script path is more stable after installation, but using the
    # command keeps generated plists portable across venv/pipx installs.
    return shutil.which("github-ai-radar") or "github-ai-radar"


def local_calendar_time(report_hour: int, report_minute: int, timezone: str) -> tuple[int, int, str]:
    target_tz = ZoneInfo(timezone)
    local_tz = datetime.now().astimezone().tzinfo
    target_now = datetime.now(target_tz)
    target_dt = datetime.combine(target_now.date(), time(report_hour, report_minute), target_tz)
    local_dt = target_dt.astimezone(local_tz)
    return local_dt.hour, local_dt.minute, str(local_tz)


def build_launchd_plist(root: Path, hour: int = 10, minute: int = 0, timezone: str = "Asia/Shanghai") -> dict:
    logs = root / "reports" / "github-radar" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    local_hour, local_minute, local_tz = local_calendar_time(hour, minute, timezone)
    return {
        "Label": LABEL,
        "ProgramArguments": [
            _python_executable(),
            "--root",
            str(root),
            "run",
            "--once",
            "--timezone",
            timezone,
            "--trigger-type",
            "scheduled",
        ],
        "StartCalendarInterval": {
            "Hour": local_hour,
            "Minute": local_minute,
        },
        "StandardOutPath": str(logs / "launchd.out.log"),
        "StandardErrorPath": str(logs / "launchd.err.log"),
        "WorkingDirectory": str(root),
        "RunAtLoad": False,
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"),
            "GITHUB_AI_RADAR_REPORT_TIMEZONE": timezone,
            "GITHUB_AI_RADAR_REPORT_HOUR": str(hour),
            "GITHUB_AI_RADAR_REPORT_MINUTE": str(minute),
            "GITHUB_AI_RADAR_LAUNCHD_LOCAL_TIMEZONE": local_tz,
        },
    }


def install_launchd(root: Path, hour: int = 10, minute: int = 0, timezone: str = "Asia/Shanghai") -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("launchd scheduling is only supported on macOS")
    path = launch_agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    plist = build_launchd_plist(root, hour=hour, minute=minute, timezone=timezone)
    with path.open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=False)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)], check=False, capture_output=True, text=True)
    completed = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return path


def uninstall_launchd() -> Path:
    if platform.system() != "Darwin":
        return launch_agent_path()
    path = launch_agent_path()
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)], check=False, capture_output=True, text=True)
    if path.exists():
        path.unlink()
    return path


def launchd_status() -> dict:
    path = launch_agent_path()
    if platform.system() != "Darwin":
        return {
            "label": LABEL,
            "plist": str(path),
            "plist_exists": path.exists(),
            "loaded": False,
            "details": "launchd is only available on macOS",
        }
    completed = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], check=False, capture_output=True, text=True)
    return {
        "label": LABEL,
        "plist": str(path),
        "plist_exists": path.exists(),
        "loaded": completed.returncode == 0,
        "details": completed.stdout if completed.returncode == 0 else completed.stderr,
    }
