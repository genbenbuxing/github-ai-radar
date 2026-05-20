from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from github_ai_radar import __version__
from github_ai_radar.paths import RadarPaths
from github_ai_radar.storage import initialize, table_counts


def _paths(args: argparse.Namespace) -> RadarPaths:
    return RadarPaths.from_root(Path(args.root).expanduser().resolve())


def cmd_init(args: argparse.Namespace) -> int:
    paths = _paths(args)
    paths.ensure()
    initialize(paths.database)
    print(f"initialized: {paths.root}")
    print(f"database: {paths.database}")
    print(f"reports: {paths.reports_dir}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    paths = _paths(args)
    exists = paths.database.exists()
    payload = {
        "version": __version__,
        "root": str(paths.root),
        "database": str(paths.database),
        "database_exists": exists,
        "reports_dir": str(paths.reports_dir),
        "counts": table_counts(paths.database) if exists else {},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    paths = _paths(args)
    paths.ensure()
    initialize(paths.database)
    tz = ZoneInfo(args.timezone)
    report_date = datetime.now(tz).strftime("%Y-%m-%d")
    state_path = paths.state_dir / f"{report_date}.state.json"
    state = {
        "report_date": report_date,
        "status": "planned",
        "message": "Collection/review pipeline is not implemented yet. This scaffold verifies installable app state, storage, and recovery paths.",
        "next_stage": "implement github_client and reporter",
        "updated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"state written: {state_path}")
    if args.once:
        print("run --once completed scaffold check")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="github-ai-radar")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--root",
        default=".",
        help="Project root for data, reports, and configuration. Defaults to current directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize local directories and SQLite database.")
    init_parser.set_defaults(func=cmd_init)

    status_parser = subparsers.add_parser("status", help="Print local database and artifact status as JSON.")
    status_parser.set_defaults(func=cmd_status)

    run_parser = subparsers.add_parser("run", help="Run the radar pipeline.")
    run_parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    run_parser.add_argument("--timezone", default="Asia/Shanghai", help="Report timezone.")
    run_parser.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
