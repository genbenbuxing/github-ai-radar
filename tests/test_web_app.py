import json
from pathlib import Path

from github_ai_radar.app_launcher import macos_app_status
from github_ai_radar.config import load_config, llm_status
from github_ai_radar.paths import RadarPaths
from github_ai_radar.storage import initialize
from github_ai_radar.web import _save_llm_settings, _save_radar_settings, render_dashboard, render_settings


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


def test_settings_page_has_direct_save_forms(tmp_path):
    paths = RadarPaths.from_root(tmp_path)
    paths.ensure()

    html = render_settings(paths).decode("utf-8")

    assert 'action="/actions/settings/radar"' in html
    assert 'action="/actions/settings/llm"' in html
    assert 'action="/actions/settings/topics"' in html
    assert 'action="/actions/settings/queries"' in html
    assert "打开 LLM 设置" not in html


def test_direct_radar_settings_save_updates_toml(tmp_path):
    paths = RadarPaths.from_root(tmp_path)
    paths.ensure()

    _save_radar_settings(
        paths,
        {
            "timezone": ["Asia/Shanghai"],
            "report_time": ["10:15"],
            "report_style": ["standard"],
            "max_candidates_per_run": ["42"],
            "deep_review_limit": ["7"],
            "read_only": ["1"],
        },
    )

    config = load_config(tmp_path)
    assert config.radar["report_time"] == "10:15"
    assert config.radar["max_candidates_per_run"] == 42
    assert config.radar["deep_review_limit"] == 7
    assert config.radar["read_only"] is True


def test_direct_llm_settings_save_writes_private_secret(tmp_path):
    paths = RadarPaths.from_root(tmp_path)
    paths.ensure()

    _save_llm_settings(
        paths,
        {
            "enabled": ["1"],
            "provider": ["openai_compatible"],
            "base_url": ["https://api.example.com/v1"],
            "model": ["example-model"],
            "api_key_env": ["EXAMPLE_API_KEY"],
            "timeout_seconds": ["30"],
            "api_key_value": ["secret-value"],
        },
    )

    status = llm_status(tmp_path)
    assert status["configured"] is True
    assert status["enabled"] is True
    assert status["api_key_env"] == "EXAMPLE_API_KEY"
    assert status["api_key_present"] is True
    assert (tmp_path / "config" / "secrets.env").exists()


def test_macos_app_status_uses_user_applications_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda *args: tmp_path)

    status = macos_app_status(name="Radar Test")

    assert status["exists"] is False
    assert status["path"] == str(tmp_path / "Applications" / "Radar Test.app")
