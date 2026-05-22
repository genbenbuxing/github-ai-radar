import json
from pathlib import Path

import pytest

from github_ai_radar.app_launcher import macos_app_status
from github_ai_radar.config import load_config, llm_status
from github_ai_radar.paths import RadarPaths
from github_ai_radar.pipeline import run_once
from github_ai_radar.storage import initialize
from github_ai_radar.web import (
    _save_llm_settings,
    _save_queries,
    _save_radar_settings,
    render_dashboard,
    render_results,
    render_settings,
)


def test_dashboard_renders_report_links(tmp_path):
    paths = RadarPaths.from_root(tmp_path)
    paths.ensure()
    initialize(paths.database)
    report = paths.reports_dir / "2026-05-20.md"
    audit = paths.reports_dir / "2026-05-20.audit.json"
    state = paths.state_dir / "2026-05-20.state.json"
    report.write_text("# Daily Report\n", encoding="utf-8")
    audit.write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "repo": {"full_name": "example/agent"},
                        "score": {"score": 88, "risk_notes": "Needs sandbox"},
                    }
                ],
                "external_events": [{"title": "AI event"}],
            }
        ),
        encoding="utf-8",
    )
    state.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    html = render_dashboard(paths).decode("utf-8")

    assert "GitHub AI Radar" in html
    assert "2026-05-20" in html
    assert "系统健康" in html
    assert "HTML 阅读版" in html
    assert "/report/2026-05-20" in html
    assert "/audit/2026-05-20" in html


def test_results_page_renders_report_center_cards(tmp_path):
    paths = RadarPaths.from_root(tmp_path)
    paths.ensure()
    initialize(paths.database)
    report = paths.reports_dir / "2026-05-20.md"
    html_report = paths.reports_dir / "2026-05-20.html"
    audit = paths.reports_dir / "2026-05-20.audit.json"
    state = paths.state_dir / "2026-05-20.state.json"
    report.write_text("# Daily Report\n", encoding="utf-8")
    html_report.write_text("<html>Daily Report</html>\n", encoding="utf-8")
    audit.write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "repo": {"full_name": "example/agent"},
                        "score": {"score": 88, "risk_notes": "Needs sandbox"},
                    }
                ],
                "external_events": [{"title": "AI event"}],
            }
        ),
        encoding="utf-8",
    )
    state.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    html = render_results(paths).decode("utf-8")

    assert "报告中心" in html or "报告索引" in html
    assert "example/agent" in html
    assert "阅读报告" in html
    assert "风险提示" in html


def test_settings_page_has_direct_save_forms(tmp_path):
    paths = RadarPaths.from_root(tmp_path)
    paths.ensure()

    html = render_settings(paths).decode("utf-8")

    assert 'action="/actions/settings/radar"' in html
    assert 'action="/actions/settings/llm"' in html
    assert 'action="/actions/settings/topics"' in html
    assert 'action="/actions/settings/queries"' in html
    assert "像素风小猫 logo" in html
    assert "当前生效：外部来源查询" in html
    assert "高级：精确查询规则" in html
    assert "高级：评分规则" in html
    assert "外部来源查询语句" in html
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


def test_direct_query_save_updates_source_queries(tmp_path):
    paths = RadarPaths.from_root(tmp_path)
    paths.ensure()

    _save_queries(
        paths,
        {
            "github_query_count": ["1"],
            "github_query_0_name": ["custom_ai"],
            "github_query_0_query": ["ai agent stars:>=10 archived:false fork:false"],
            "source_query_count": ["1"],
            "source_query_0_name": ["custom_events"],
            "source_query_0_query": ["AI agent regulation official"],
            "new_github_query_name": [""],
            "new_github_query": [""],
            "new_source_query_name": ["custom_feed"],
            "new_source_query": ["https://example.com/feed.xml"],
        },
    )

    after = load_config(tmp_path)
    assert after.github_queries == [
        {"name": "custom_ai", "query": "ai agent stars:>=10 archived:false fork:false"}
    ]
    assert after.source_queries == [
        {"name": "custom_events", "query": "AI agent regulation official"},
        {"name": "custom_feed", "query": "https://example.com/feed.xml"},
    ]


def test_failed_run_marks_state_failed(tmp_path):
    with pytest.raises(Exception):
        run_once(tmp_path, timezone="Invalid/Zone")

    states = list((tmp_path / "reports" / "github-radar" / "state").glob("*.state.json"))
    assert states
    state = json.loads(states[0].read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["errors"]


def test_macos_app_status_uses_user_applications_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda *args: tmp_path)

    status = macos_app_status(name="Radar Test")

    assert status["exists"] is False
    assert status["path"] == str(tmp_path / "Applications" / "Radar Test.app")
