from __future__ import annotations

import argparse
import json
from pathlib import Path

from github_ai_radar import __version__
from github_ai_radar.config import ensure_default_config
from github_ai_radar.doctor import run_doctor
from github_ai_radar.app_launcher import install_macos_app, macos_app_status, uninstall_macos_app
from github_ai_radar.paths import RadarPaths
from github_ai_radar.pipeline import run_once
from github_ai_radar.scheduler import install_launchd, launchd_status, uninstall_launchd
from github_ai_radar.storage import initialize, table_counts
from github_ai_radar.web import serve_dashboard


def _paths(args: argparse.Namespace) -> RadarPaths:
    return RadarPaths.from_root(Path(args.root).expanduser().resolve())


def cmd_init(args: argparse.Namespace) -> int:
    paths = _paths(args)
    paths.ensure()
    written = ensure_default_config(paths.root)
    initialize(paths.database)
    print(f"initialized: {paths.root}")
    print(f"database: {paths.database}")
    print(f"reports: {paths.reports_dir}")
    if written:
        print("created config files:")
        for path in written:
            print(f"- {path}")
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
    result = run_once(
        Path(args.root).expanduser().resolve(),
        timezone=args.timezone,
        max_candidates=args.max_candidates,
        deep_review_limit=args.deep_review_limit,
        trigger_type=args.trigger_type,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_schedule_install(args: argparse.Namespace) -> int:
    path = install_launchd(
        Path(args.root).expanduser().resolve(),
        hour=args.hour,
        minute=args.minute,
        timezone=args.timezone,
    )
    print(f"installed launchd agent: {path}")
    print(f"target report time: {args.hour:02d}:{args.minute:02d} {args.timezone}")
    return 0


def cmd_schedule_uninstall(args: argparse.Namespace) -> int:
    path = uninstall_launchd()
    print(f"uninstalled launchd agent: {path}")
    return 0


def cmd_schedule_status(args: argparse.Namespace) -> int:
    print(json.dumps(launchd_status(), ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    serve_dashboard(
        Path(args.root).expanduser().resolve(),
        host=args.host,
        port=args.port,
        open_browser=args.open,
    )
    return 0


def cmd_app_install(args: argparse.Namespace) -> int:
    path = install_macos_app(
        Path(args.root).expanduser().resolve(),
        port=args.port,
        name=args.name,
    )
    print(f"installed macOS app: {path}")
    print(f"local app window will load: http://127.0.0.1:{args.port}/")
    return 0


def cmd_app_uninstall(args: argparse.Namespace) -> int:
    path = uninstall_macos_app(name=args.name)
    print(f"uninstalled macOS app: {path}")
    return 0


def cmd_app_status(args: argparse.Namespace) -> int:
    print(json.dumps(macos_app_status(name=args.name), ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print(json.dumps(run_doctor(Path(args.root).expanduser().resolve()), ensure_ascii=False, indent=2))
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

    doctor_parser = subparsers.add_parser("doctor", help="Diagnose local setup, GitHub auth, database, config, and scheduler.")
    doctor_parser.set_defaults(func=cmd_doctor)

    run_parser = subparsers.add_parser("run", help="Run the radar pipeline.")
    run_parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    run_parser.add_argument("--timezone", default="Asia/Shanghai", help="Report timezone.")
    run_parser.add_argument("--max-candidates", type=int, help="Maximum unique GitHub candidates to inspect.")
    run_parser.add_argument("--deep-review-limit", type=int, help="Maximum repositories to fetch README/metadata for.")
    run_parser.add_argument("--trigger-type", default="manual", choices=["manual", "scheduled", "recovery"], help="Run trigger label.")
    run_parser.set_defaults(func=cmd_run)

    schedule_parser = subparsers.add_parser("schedule", help="Manage native local scheduler integration.")
    schedule_subparsers = schedule_parser.add_subparsers(dest="schedule_command", required=True)

    schedule_install = schedule_subparsers.add_parser("install", help="Install macOS launchd daily schedule.")
    schedule_install.add_argument("--timezone", default="Asia/Shanghai", help="Desired report timezone.")
    schedule_install.add_argument("--hour", type=int, default=10, help="Desired report hour in report timezone.")
    schedule_install.add_argument("--minute", type=int, default=0, help="Desired report minute in report timezone.")
    schedule_install.set_defaults(func=cmd_schedule_install)

    schedule_uninstall = schedule_subparsers.add_parser("uninstall", help="Uninstall macOS launchd schedule.")
    schedule_uninstall.set_defaults(func=cmd_schedule_uninstall)

    schedule_status = schedule_subparsers.add_parser("status", help="Print macOS launchd schedule status.")
    schedule_status.set_defaults(func=cmd_schedule_status)

    serve_parser = subparsers.add_parser("serve", help="Start the local HTML dashboard.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Dashboard bind host.")
    serve_parser.add_argument("--port", type=int, default=8765, help="Dashboard bind port.")
    serve_parser.add_argument("--open", action="store_true", help="Open the dashboard in the default browser.")
    serve_parser.set_defaults(func=cmd_serve)

    app_parser = subparsers.add_parser("app", help="Manage the local macOS app.")
    app_subparsers = app_parser.add_subparsers(dest="app_command", required=True)

    app_install = app_subparsers.add_parser("install", help="Install the macOS .app into ~/Applications.")
    app_install.add_argument("--port", type=int, default=8765, help="Local dashboard port used by the app.")
    app_install.add_argument("--name", default="GitHub AI Radar", help="Application display name.")
    app_install.set_defaults(func=cmd_app_install)

    app_uninstall = app_subparsers.add_parser("uninstall", help="Remove the macOS .app.")
    app_uninstall.add_argument("--name", default="GitHub AI Radar", help="Application display name.")
    app_uninstall.set_defaults(func=cmd_app_uninstall)

    app_status = app_subparsers.add_parser("status", help="Print macOS .app status.")
    app_status.add_argument("--name", default="GitHub AI Radar", help="Application display name.")
    app_status.set_defaults(func=cmd_app_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
