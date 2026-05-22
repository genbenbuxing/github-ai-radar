import json

from github_ai_radar.reporter import render_html, render_markdown_as_html, verify_report, write_report


def _payload():
    return {
        "report_date": "2026-05-22",
        "timezone": "Asia/Shanghai",
        "generated_at": "2026-05-22T02:15:00Z",
        "queries": [{"name": "agent", "query": "ai agent stars:>=10"}],
        "candidate_count": 1,
        "deep_review_limit": 1,
        "reviews": [
            {
                "repo": {
                    "full_name": "example/agent",
                    "url": "https://github.com/example/agent",
                    "description": "Agent toolkit",
                    "language": "Python",
                    "stars": 42,
                    "forks": 3,
                    "license_key": "mit",
                },
                "score": {
                    "score": 80,
                    "recommendation": "deep_read",
                    "readme_quality": "clear",
                    "usability_notes": "Has examples",
                    "risk_notes": "Needs sandbox",
                    "scoring": {"growth": {"3d": {"status": "ok", "delta": 5}}},
                },
            }
        ],
        "external_events": [],
        "external_source_queries": [],
        "external_source_errors": [],
        "artifacts": {},
        "safety": {
            "cloned_repositories": False,
            "installed_dependencies": False,
            "executed_third_party_code": False,
        },
    }


def test_write_report_creates_html_markdown_and_audit(tmp_path):
    markdown = tmp_path / "2026-05-22.md"
    html = tmp_path / "2026-05-22.html"
    audit = tmp_path / "2026-05-22.audit.json"

    write_report(_payload(), markdown, audit, html)
    verify_report(markdown, audit, html)

    assert markdown.exists()
    assert html.exists()
    assert "每日研究报告" in html.read_text(encoding="utf-8")
    assert json.loads(audit.read_text(encoding="utf-8"))["report_date"] == "2026-05-22"


def test_render_markdown_as_html_handles_basic_report_markdown():
    rendered = render_markdown_as_html(
        "# 标题\n\n## 小节\n\n| 项目 | 分数 |\n| --- | ---: |\n| [repo](https://example.com) | 80 |\n\n- 风险：`test`\n"
    )

    assert "<table>" in rendered
    assert '<a href="https://example.com">repo</a>' in rendered
    assert "<code>test</code>" in rendered


def test_render_html_escapes_report_values():
    payload = _payload()
    payload["reviews"][0]["repo"]["description"] = "<script>alert(1)</script>"

    rendered = render_html(payload)

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
