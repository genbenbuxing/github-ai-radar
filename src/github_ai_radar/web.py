from __future__ import annotations

import html
import json
import sqlite3
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from github_ai_radar.paths import RadarPaths
from github_ai_radar.storage import table_counts


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _reports(paths: RadarPaths) -> list[dict]:
    reports: list[dict] = []
    for markdown in sorted(paths.reports_dir.glob("*.md"), reverse=True):
        date = markdown.stem
        audit = paths.reports_dir / f"{date}.audit.json"
        state = paths.state_dir / f"{date}.state.json"
        state_payload = _read_json(state)
        reports.append(
            {
                "date": date,
                "markdown": markdown,
                "audit": audit,
                "state": state,
                "status": state_payload.get("status", "unknown"),
                "size": markdown.stat().st_size,
            }
        )
    return reports


def _latest_reviews(paths: RadarPaths, limit: int = 10) -> list[sqlite3.Row]:
    if not paths.database.exists():
        return []
    with sqlite3.connect(paths.database) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT
              repositories.full_name,
              repositories.url,
              repositories.primary_language,
              repo_reviews.score,
              repo_reviews.recommendation,
              repo_reviews.readme_quality,
              repo_reviews.risk_notes,
              repo_reviews.reviewed_at
            FROM repo_reviews
            JOIN repositories ON repositories.id = repo_reviews.repository_id
            ORDER BY repo_reviews.reviewed_at DESC, repo_reviews.score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def _html_page(title: str, body: str) -> bytes:
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #d8dee6;
      --accent: #1463ff;
      --good: #087f5b;
      --warn: #9a6700;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      padding: 18px 28px;
      background: #101828;
      color: white;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
    }}
    header h1 {{ margin: 0; font-size: 18px; font-weight: 650; }}
    header nav a {{ color: #dbeafe; margin-left: 16px; text-decoration: none; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    .muted {{ color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); background: #f3f5f8; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .section {{ margin-top: 22px; }}
    .status {{ font-weight: 650; color: var(--good); }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      overflow: auto;
    }}
    @media (max-width: 820px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      header {{ align-items: flex-start; flex-direction: column; }}
      header nav a {{ margin-left: 0; margin-right: 12px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>GitHub AI Radar</h1>
    <nav>
      <a href="/">Dashboard</a>
      <a href="/api/status">API Status</a>
    </nav>
  </header>
  <main>{body}</main>
</body>
</html>"""
    return page.encode("utf-8")


def render_dashboard(paths: RadarPaths) -> bytes:
    counts = table_counts(paths.database) if paths.database.exists() else {}
    reports = _reports(paths)
    reviews = _latest_reviews(paths)
    cards = [
        ("Reports", len(reports)),
        ("Repositories", counts.get("repositories", 0)),
        ("Snapshots", counts.get("repo_snapshots", 0)),
        ("Reviews", counts.get("repo_reviews", 0)),
    ]
    card_html = "\n".join(
        f'<div class="card"><div class="muted">{html.escape(label)}</div><div class="metric">{value}</div></div>'
        for label, value in cards
    )
    report_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(item['date'])}</td>"
        f"<td><span class=\"status\">{html.escape(str(item['status']))}</span></td>"
        f"<td>{item['size']} bytes</td>"
        f"<td><a href=\"/report/{html.escape(item['date'])}\">Markdown</a> · "
        f"<a href=\"/audit/{html.escape(item['date'])}\">Audit JSON</a></td>"
        "</tr>"
        for item in reports[:20]
    ) or '<tr><td colspan="4" class="muted">No reports yet.</td></tr>'
    review_rows = "\n".join(
        "<tr>"
        f"<td><a href=\"{html.escape(row['url'])}\">{html.escape(row['full_name'])}</a></td>"
        f"<td>{html.escape(row['primary_language'] or '')}</td>"
        f"<td>{row['score']}</td>"
        f"<td>{html.escape(row['recommendation'])}</td>"
        f"<td>{html.escape(row['risk_notes'] or '')}</td>"
        "</tr>"
        for row in reviews
    ) or '<tr><td colspan="5" class="muted">No reviews yet.</td></tr>'
    body = f"""
<div class="grid">{card_html}</div>
<div class="section card">
  <div class="muted">Workspace</div>
  <div>{html.escape(str(paths.root))}</div>
  <div class="muted">Generated at {html.escape(datetime.now().isoformat(timespec="seconds"))}</div>
</div>
<section class="section">
  <h2>Reports</h2>
  <table>
    <thead><tr><th>Date</th><th>Status</th><th>Size</th><th>Open</th></tr></thead>
    <tbody>{report_rows}</tbody>
  </table>
</section>
<section class="section">
  <h2>Latest Reviews</h2>
  <table>
    <thead><tr><th>Repository</th><th>Language</th><th>Score</th><th>Recommendation</th><th>Risk</th></tr></thead>
    <tbody>{review_rows}</tbody>
  </table>
</section>
"""
    return _html_page("GitHub AI Radar", body)


def _status_json(paths: RadarPaths) -> bytes:
    payload = {
        "root": str(paths.root),
        "database": str(paths.database),
        "reports_dir": str(paths.reports_dir),
        "counts": table_counts(paths.database) if paths.database.exists() else {},
        "reports": [
            {
                "date": item["date"],
                "status": item["status"],
                "markdown": str(item["markdown"]),
                "audit": str(item["audit"]),
            }
            for item in _reports(paths)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


class DashboardHandler(BaseHTTPRequestHandler):
    paths: RadarPaths

    def _send(self, content: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/":
            self._send(render_dashboard(self.paths))
            return
        if path == "/api/status":
            self._send(_status_json(self.paths), "application/json; charset=utf-8")
            return
        if path.startswith("/report/"):
            date = path.rsplit("/", 1)[-1]
            report = self.paths.reports_dir / f"{date}.md"
            if not report.exists():
                self._send(b"report not found", "text/plain; charset=utf-8", 404)
                return
            content = html.escape(report.read_text(encoding="utf-8"))
            self._send(_html_page(f"Report {date}", f"<h2>Report {html.escape(date)}</h2><pre>{content}</pre>"))
            return
        if path.startswith("/audit/"):
            date = path.rsplit("/", 1)[-1]
            audit = self.paths.reports_dir / f"{date}.audit.json"
            if not audit.exists():
                self._send(b"audit not found", "text/plain; charset=utf-8", 404)
                return
            self._send(audit.read_bytes(), "application/json; charset=utf-8")
            return
        self._send(b"not found", "text/plain; charset=utf-8", 404)

    def log_message(self, format: str, *args: object) -> None:
        return


def serve_dashboard(root: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    paths = RadarPaths.from_root(root)
    paths.ensure()

    class Handler(DashboardHandler):
        pass

    Handler.paths = paths
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"GitHub AI Radar dashboard: {url}")
    server.serve_forever()
