import json
from pathlib import Path

from github_ai_radar.app_launcher import macos_app_status
from github_ai_radar.paths import RadarPaths
from github_ai_radar.storage import initialize
from github_ai_radar.web import render_dashboard


def test_dashboard_renders_report_links(tmp_path):
    paths = RadarPaths.from_root(tmp_path)
    paths.ensure()
    initialize(paths.database)
    report = paths.reports_dir / "2026-05-20.md"
    audit = paths.reports_dir / "2026-05-20.audit.json"
    state = paths.state_dir / "2026-05-20.state.json"
    report.write_text("# Daily Report\n", encoding="utf-8")
    audit.write_text(json.dumps({"ok": True}), encoding="utf-8")
    state.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    html = render_dashboard(paths).decode("utf-8")

    assert "GitHub AI Radar" in html
    assert "2026-05-20" in html
    assert "/report/2026-05-20" in html
    assert "/audit/2026-05-20" in html


def test_macos_app_status_uses_user_applications_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda *args: tmp_path)

    status = macos_app_status(name="Radar Test")

    assert status["exists"] is False
    assert status["path"] == str(tmp_path / "Applications" / "Radar Test.app")
