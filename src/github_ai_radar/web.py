from __future__ import annotations

import html
import json
import platform
import sqlite3
import subprocess
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from github_ai_radar.config import load_config, llm_status
from github_ai_radar.paths import RadarPaths
from github_ai_radar.pipeline import STAGES, run_once
from github_ai_radar.scheduler import install_launchd, launchd_status, uninstall_launchd
from github_ai_radar.storage import table_counts


STAGE_LABELS = {
    "init": "准备环境",
    "github_search": "检索 GitHub",
    "github_readme_review": "阅读 README",
    "scoring": "评分排序",
    "markdown_render": "生成报告",
    "audit_json_render": "生成审计记录",
    "final_verify": "验证文件",
    "completed": "完成",
}

_RUN_LOCK = threading.Lock()
_RUN_JOBS: dict[str, dict[str, object]] = {}


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
                "state_payload": state_payload,
            }
        )
    return reports


def _latest_state(paths: RadarPaths) -> dict:
    states = sorted(paths.state_dir.glob("*.state.json"), reverse=True)
    return _read_json(states[0]) if states else {}


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


def _logs(paths: RadarPaths) -> list[dict]:
    items = []
    for path in sorted(paths.logs_dir.glob("*.log")):
        items.append({"name": path.name, "path": path, "size": path.stat().st_size})
    return items


def _notice(query: str) -> str:
    payload = parse_qs(query)
    message = payload.get("notice", [""])[0]
    if not message:
        return ""
    level = payload.get("level", ["ok"])[0]
    return f'<div class="notice {html.escape(level)}">{html.escape(message)}</div>'


def _redirect(location: str) -> bytes:
    return location.encode("utf-8")


def _format_dt(value: object) -> str:
    if not value:
        return "-"
    text = str(value)
    return text.replace("T", " ").replace("Z", "")


def _active_job(root: Path) -> dict[str, object] | None:
    job = _RUN_JOBS.get(str(root))
    if job and job.get("status") == "running":
        return job
    return None


def _background_run(job: dict[str, object], root: Path, options: dict[str, object]) -> None:
    try:
        result = run_once(
            root,
            timezone=str(options["timezone"]),
            max_candidates=options.get("max_candidates") or None,
            deep_review_limit=options.get("deep_review_limit") or None,
            trigger_type="manual",
        )
        job["status"] = "completed"
        job["result"] = result
    except Exception as exc:  # surfaced in the UI instead of crashing the server
        job["status"] = "failed"
        job["error"] = str(exc)
    finally:
        job["finished_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _start_run(root: Path, options: dict[str, object]) -> tuple[bool, str]:
    with _RUN_LOCK:
        if _active_job(root):
            return False, "报告任务已经在运行，请在自动化页面查看阶段。"
        job = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "options": options,
        }
        _RUN_JOBS[str(root)] = job
        thread = threading.Thread(target=_background_run, args=(job, root, options), daemon=True)
        thread.start()
    return True, "已开始生成报告。"


def _parse_int(values: dict[str, list[str]], name: str, default: int) -> int:
    try:
        return max(1, int(values.get(name, [str(default)])[0]))
    except ValueError:
        return default


def _parse_bounded_int(values: dict[str, list[str]], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return min(maximum, max(minimum, int(values.get(name, [str(default)])[0])))
    except ValueError:
        return default


def _open_target(paths: RadarPaths, target: str) -> str:
    config_dir = paths.root / "config"
    allowed = {
        "root": paths.root,
        "config": config_dir,
        "reports": paths.reports_dir,
        "logs": paths.logs_dir,
        "data": paths.data_dir,
        "radar_config": config_dir / "radar.toml",
        "topics_config": config_dir / "topics.toml",
        "queries_config": config_dir / "queries.toml",
        "scoring_config": config_dir / "scoring.toml",
        "llm_config": config_dir / "llm.toml",
        "llm_example": config_dir / "llm.toml.example",
        "readme": paths.root / "README.md",
    }
    path = allowed.get(target)
    if path is None:
        raise ValueError("未知的本地入口。")
    if target == "llm_config" and not path.exists():
        example = config_dir / "llm.toml.example"
        if example.exists():
            path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Darwin":
        subprocess.run(["open", str(path)], check=False)
        return f"已打开：{path}"
    return f"位置：{path}"


def _open_form(target: str, label: str, variant: str = "secondary") -> str:
    return (
        '<form method="post" action="/actions/open" class="inline-form">'
        f'<input type="hidden" name="target" value="{html.escape(target)}">'
        f'<button class="button {html.escape(variant)}" type="submit">{html.escape(label)}</button>'
        "</form>"
    )


def _html_page(title: str, body: str, active: str = "home") -> bytes:
    nav = [
        ("home", "/", "操作台"),
        ("results", "/results", "结果"),
        ("settings", "/settings", "参数"),
        ("automation", "/automation", "自动化"),
        ("api", "/api/status", "状态 API"),
    ]
    nav_html = "\n".join(
        f'<a class="{"active" if key == active else ""}" href="{href}">{label}</a>'
        for key, href, label in nav
    )
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #18212f;
      --muted: #647084;
      --line: #d9e0ea;
      --soft: #eef3f8;
      --accent: #0b63ce;
      --accent-ink: #ffffff;
      --good: #0a7a4b;
      --warn: #9a6700;
      --bad: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{ min-height: 100vh; display: grid; grid-template-columns: 230px minmax(0, 1fr); }}
    aside {{
      background: #111827;
      color: white;
      padding: 22px 18px;
    }}
    .brand {{ font-size: 18px; font-weight: 700; margin-bottom: 4px; }}
    .brand-sub {{ color: #bdc7d8; font-size: 12px; margin-bottom: 24px; }}
    nav a {{
      display: block;
      color: #dce6f5;
      padding: 10px 12px;
      border-radius: 8px;
      margin-bottom: 6px;
      text-decoration: none;
      font-weight: 600;
    }}
    nav a.active, nav a:hover {{ background: #243246; color: white; text-decoration: none; }}
    main {{ padding: 26px; max-width: 1240px; width: 100%; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; line-height: 1.25; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; }}
    .lead {{ color: var(--muted); margin: 0 0 20px; }}
    .grid {{ display: grid; gap: 14px; }}
    .grid-2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .grid-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .grid-4 {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric {{ font-size: 26px; font-weight: 760; margin-top: 4px; }}
    .muted {{ color: var(--muted); }}
    .section {{ margin-top: 18px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .button {{
      border: 0;
      border-radius: 8px;
      background: var(--accent);
      color: var(--accent-ink);
      padding: 9px 12px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      display: inline-block;
    }}
    .button.secondary {{ background: var(--soft); color: var(--ink); border: 1px solid var(--line); }}
    .button.danger {{ background: #fee4e2; color: var(--bad); border: 1px solid #fecdca; }}
    .inline-form {{ display: inline; margin: 0; }}
    label {{ display: block; font-weight: 700; margin-bottom: 5px; }}
    input, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      background: white;
      color: var(--ink);
      font: inherit;
    }}
    .form-grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; align-items: end; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); background: #eef2f7; }}
    tr:last-child td {{ border-bottom: 0; }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 3px 8px; font-weight: 700; font-size: 12px; background: var(--soft); }}
    .pill.ok {{ color: var(--good); background: #dff8ec; }}
    .pill.warn {{ color: var(--warn); background: #fff3cf; }}
    .pill.bad {{ color: var(--bad); background: #fee4e2; }}
    .timeline {{ display: grid; gap: 8px; }}
    .stage {{
      display: grid;
      grid-template-columns: 26px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: white;
    }}
    .dot {{ width: 14px; height: 14px; border-radius: 50%; background: #b8c2d1; }}
    .stage.done .dot {{ background: var(--good); }}
    .stage.running .dot {{ background: var(--warn); }}
    .stage.failed .dot {{ background: var(--bad); }}
    .notice {{ padding: 10px 12px; border-radius: 8px; margin-bottom: 14px; border: 1px solid var(--line); background: white; }}
    .notice.ok {{ border-color: #b7ebcc; background: #ecfdf3; color: var(--good); }}
    .notice.bad {{ border-color: #fecdca; background: #fff1f0; color: var(--bad); }}
    .helper {{
      background: #f8fbff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      margin-top: 10px;
    }}
    .steps {{
      margin: 0;
      padding-left: 20px;
    }}
    .steps li {{ margin: 6px 0; }}
    .file-chip {{
      display: inline-block;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      background: var(--soft);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 2px 6px;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: white;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      overflow: auto;
    }}
    @media (max-width: 900px) {{
      .shell {{ display: block; }}
      aside {{ position: static; }}
      nav {{ display: flex; gap: 6px; flex-wrap: wrap; }}
      nav a {{ margin-bottom: 0; }}
      main {{ padding: 18px; }}
      .grid-2, .grid-3, .grid-4, .form-grid {{ grid-template-columns: 1fr; }}
      .stage {{ grid-template-columns: 22px minmax(0, 1fr); }}
      .stage .muted {{ grid-column: 2; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">GitHub AI Radar</div>
      <div class="brand-sub">本地研究雷达控制台</div>
      <nav>{nav_html}</nav>
    </aside>
    <main>{body}</main>
  </div>
</body>
</html>"""
    return page.encode("utf-8")


def _stage_items(state: dict) -> str:
    stages = {item.get("name"): item for item in state.get("stages", []) if isinstance(item, dict)}
    completed = set(stages)
    last = state.get("last_successful_stage")
    last_index = STAGES.index(last) if last in STAGES else -1
    rows = []
    for index, name in enumerate(STAGES):
        item = stages.get(name, {})
        if name in completed:
            class_name = "done"
            label = "已完成"
        elif state.get("status") == "running" and index == last_index + 1:
            class_name = "running"
            label = "进行中"
        elif state.get("status") == "failed" and index == last_index + 1:
            class_name = "failed"
            label = "失败"
        else:
            class_name = "pending"
            label = "等待"
        detail_parts = []
        if "candidate_count" in item:
            detail_parts.append(f"候选 {item['candidate_count']} 个")
        if "review_count" in item:
            detail_parts.append(f"深读 {item['review_count']} 个")
        if item.get("path"):
            detail_parts.append(str(item["path"]))
        detail = " / ".join(detail_parts) or _format_dt(item.get("completed_at"))
        rows.append(
            '<div class="stage {class_name}">'
            '<span class="dot"></span>'
            '<div><strong>{name}</strong><div class="muted">{detail}</div></div>'
            '<span class="pill {pill}">{label}</span>'
            "</div>".format(
                class_name=class_name,
                name=html.escape(STAGE_LABELS.get(name, name)),
                detail=html.escape(detail),
                pill="ok" if class_name == "done" else "warn" if class_name == "running" else "bad" if class_name == "failed" else "",
                label=html.escape(label),
            )
        )
    return "\n".join(rows)


def _run_form(paths: RadarPaths) -> str:
    config = load_config(paths.root)
    max_candidates = int(config.radar.get("max_candidates_per_run", 100))
    deep_review_limit = int(config.radar.get("deep_review_limit", 10))
    timezone = str(config.radar.get("timezone", "Asia/Shanghai"))
    return f"""
<form method="post" action="/actions/run" class="form-grid">
  <div>
    <label for="timezone">报告时区</label>
    <input id="timezone" name="timezone" value="{html.escape(timezone)}">
  </div>
  <div>
    <label for="max_candidates">候选项目数</label>
    <input id="max_candidates" name="max_candidates" type="number" min="1" value="{max_candidates}">
  </div>
  <div>
    <label for="deep_review_limit">深度阅读数</label>
    <input id="deep_review_limit" name="deep_review_limit" type="number" min="1" value="{deep_review_limit}">
  </div>
  <div>
    <button class="button" type="submit">立即生成报告</button>
  </div>
</form>
"""


def _report_rows(reports: list[dict], limit: int = 12) -> str:
    return "\n".join(
        "<tr>"
        f"<td>{html.escape(item['date'])}</td>"
        f"<td><span class=\"pill {'ok' if item['status'] == 'completed' else 'warn'}\">{html.escape(str(item['status']))}</span></td>"
        f"<td>{item['size']} bytes</td>"
        f"<td><a href=\"/report/{html.escape(item['date'])}\">打开报告</a> · "
        f"<a href=\"/audit/{html.escape(item['date'])}\">审计 JSON</a></td>"
        "</tr>"
        for item in reports[:limit]
    ) or '<tr><td colspan="4" class="muted">还没有报告。可以先回到操作台点击“立即生成报告”。</td></tr>'


def _review_rows(paths: RadarPaths) -> str:
    reviews = _latest_reviews(paths)
    return "\n".join(
        "<tr>"
        f"<td><a href=\"{html.escape(row['url'])}\">{html.escape(row['full_name'])}</a></td>"
        f"<td>{html.escape(row['primary_language'] or '-')}</td>"
        f"<td>{row['score']}</td>"
        f"<td>{html.escape(row['recommendation'])}</td>"
        f"<td>{html.escape(row['risk_notes'] or '-')}</td>"
        "</tr>"
        for row in reviews
    ) or '<tr><td colspan="5" class="muted">还没有项目分析记录。</td></tr>'


def render_dashboard(paths: RadarPaths, notice: str = "") -> bytes:
    counts = table_counts(paths.database) if paths.database.exists() else {}
    reports = _reports(paths)
    state = _latest_state(paths)
    job = _RUN_JOBS.get(str(paths.root))
    active = _active_job(paths.root)
    status_text = "运行中" if active else state.get("status", "未生成")
    cards = [
        ("报告", len(reports), "结果页查看 Markdown 和审计 JSON"),
        ("项目", counts.get("repositories", 0), "本地 SQLite 已记录项目"),
        ("快照", counts.get("repo_snapshots", 0), "用于计算 3 日增长"),
        ("任务", status_text, "自动化页查看阶段"),
    ]
    card_html = "\n".join(
        f'<div class="panel"><div class="muted">{html.escape(label)}</div><div class="metric">{html.escape(str(value))}</div><div class="muted">{html.escape(desc)}</div></div>'
        for label, value, desc in cards
    )
    job_notice = ""
    if job:
        if job.get("status") == "failed":
            job_notice = f'<div class="notice bad">最近一次手动运行失败：{html.escape(str(job.get("error", "")))}</div>'
        elif job.get("status") == "completed":
            result = job.get("result") or {}
            markdown = result.get("markdown") if isinstance(result, dict) else ""
            job_notice = f'<div class="notice ok">最近一次手动运行已完成。报告：{html.escape(str(markdown))}</div>'
    body = f"""
{notice}
{job_notice}
<h1>操作台</h1>
<p class="lead">这里是普通用户入口：生成报告、查看结果、设置参数、管理每日自动化。</p>
<div class="grid grid-4">{card_html}</div>

<section class="section panel">
  <h2>生成今日报告</h2>
  {_run_form(paths)}
</section>

<section class="section grid grid-3">
  <div class="panel">
    <h3>结果在哪里看</h3>
    <p class="muted">生成后进入“结果”页，也可以直接打开本地报告文件夹。</p>
    <div class="actions"><a class="button" href="/results">查看结果</a>{_open_form("reports", "打开报告文件夹")}</div>
  </div>
  <div class="panel">
    <h3>参数在哪里改</h3>
    <p class="muted">采集方向、查询词、评分权重、LLM API 都集中在“参数”页。</p>
    <div class="actions"><a class="button" href="/settings">查看参数</a>{_open_form("config", "打开参数文件夹")}</div>
  </div>
  <div class="panel">
    <h3>任务执行到哪里了</h3>
    <p class="muted">每日任务和手动任务阶段都在“自动化”页展示。</p>
    <div class="actions"><a class="button" href="/automation">查看自动化</a></div>
  </div>
</section>

<section class="section grid grid-2">
  <div class="panel">
    <h2>最新任务阶段</h2>
    <div class="timeline">{_stage_items(state)}</div>
  </div>
  <div class="panel">
    <h2>最近报告</h2>
    <table>
      <thead><tr><th>日期</th><th>状态</th><th>大小</th><th>打开</th></tr></thead>
      <tbody>{_report_rows(reports, limit=5)}</tbody>
    </table>
  </div>
</section>
"""
    return _html_page("GitHub AI Radar", body, active="home")


def render_results(paths: RadarPaths, notice: str = "") -> bytes:
    reports = _reports(paths)
    body = f"""
{notice}
<h1>结果</h1>
<p class="lead">这里集中查看每天的中文报告、机器审计 JSON 和最近的项目分析记录。</p>
<section class="panel">
  <div class="actions" style="margin-bottom: 12px;">{_open_form("reports", "打开报告文件夹")}{_open_form("data", "打开数据库文件夹")}</div>
  <table>
    <thead><tr><th>日期</th><th>状态</th><th>大小</th><th>打开</th></tr></thead>
    <tbody>{_report_rows(reports, limit=30)}</tbody>
  </table>
</section>
<section class="section panel">
  <h2>最近项目分析</h2>
  <table>
    <thead><tr><th>项目</th><th>语言</th><th>分数</th><th>建议</th><th>风险</th></tr></thead>
    <tbody>{_review_rows(paths)}</tbody>
  </table>
</section>
"""
    return _html_page("GitHub AI Radar Results", body, active="results")


def render_settings(paths: RadarPaths, notice: str = "") -> bytes:
    config = load_config(paths.root)
    llm = llm_status(paths.root)
    topics = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('name', '-')))}</td>"
        f"<td><span class=\"pill {'ok' if item.get('enabled') else 'warn'}\">{'启用' if item.get('enabled') else '停用'}</span></td>"
        f"<td>{html.escape(str(item.get('description', '-')))}</td>"
        f"<td>{html.escape(', '.join(item.get('github_terms') or []))}</td>"
        "</tr>"
        for item in config.topics
    ) or '<tr><td colspan="4" class="muted">还没有采集方向。</td></tr>'
    query_rows = "\n".join(
        f"<tr><td>{html.escape(item.get('name', '-'))}</td><td>{html.escape(item.get('query', '-'))}</td></tr>"
        for item in config.github_queries
    ) or '<tr><td colspan="2" class="muted">还没有 GitHub 查询。</td></tr>'
    llm_rows = [
        ("配置文件", "已创建" if llm["configured"] else "未创建"),
        ("启用状态", "启用" if llm["enabled"] else "未启用"),
        ("Provider", llm.get("provider") or "-"),
        ("Base URL", llm.get("base_url") or "-"),
        ("Model", llm.get("model") or "-"),
        ("API Key 环境变量", llm.get("api_key_env") or "-"),
        ("API Key 是否可用", "可用" if llm["api_key_present"] else "未检测到"),
    ]
    llm_table = "\n".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>" for k, v in llm_rows)
    body = f"""
{notice}
<h1>参数</h1>
<p class="lead">这里不是给程序员看的配置清单，而是告诉你“想调整什么，应该去哪里改”。保存参数文件后，回到操作台立即生成一次报告即可生效。</p>

<section class="grid grid-4">
  <div class="panel">
    <h2>1. 改关注方向</h2>
    <p class="muted">增加行业、关键词或启用自定义方向。</p>
    <div class="helper"><span class="file-chip">config/topics.toml</span></div>
    <div class="actions section">{_open_form("topics_config", "打开采集方向")}</div>
  </div>
  <div class="panel">
    <h2>2. 改搜索规则</h2>
    <p class="muted">调整 stars、created、pushed、topic 等 GitHub 检索条件。</p>
    <div class="helper"><span class="file-chip">config/queries.toml</span></div>
    <div class="actions section">{_open_form("queries_config", "打开查询规则")}</div>
  </div>
  <div class="panel">
    <h2>3. 接入 LLM</h2>
    <p class="muted">填写 OpenAI-compatible API 地址、模型和环境变量名。</p>
    <div class="helper"><span class="file-chip">config/llm.toml</span></div>
    <div class="actions section">{_open_form("llm_config", "打开 LLM 设置")}</div>
  </div>
  <div class="panel">
    <h2>4. 运行与收获</h2>
    <p class="muted">在操作台生成报告，在结果页查看 Markdown 和审计 JSON。</p>
    <div class="actions section"><a class="button" href="/">去操作台</a><a class="button secondary" href="/results">查看结果</a></div>
  </div>
</section>

<section class="section panel">
  <h2>常见目标对照表</h2>
  <table>
    <thead><tr><th>我想做什么</th><th>在哪里改</th><th>怎么改</th><th>之后做什么</th></tr></thead>
    <tbody>
      <tr><td>添加新的信息方向</td><td><span class="file-chip">topics.toml</span></td><td>复制 custom 区块，设置 enabled = true，改 name、description、github_terms。</td><td>保存后回操作台立即生成报告。</td></tr>
      <tr><td>让搜索更宽或更窄</td><td><span class="file-chip">queries.toml</span></td><td>调整 stars、created、pushed、topic 等条件；stars 越低越宽，时间窗口越长越宽。</td><td>生成一次报告观察候选数量。</td></tr>
      <tr><td>控制每天看多少项目</td><td><span class="file-chip">radar.toml</span></td><td>修改 max_candidates_per_run 和 deep_review_limit。</td><td>候选多会更慢，深读多会更详细。</td></tr>
      <tr><td>调整推荐分数</td><td><span class="file-chip">scoring.toml</span></td><td>修改 weights 和 penalties，提升你更看重的指标。</td><td>新报告会使用新的评分权重。</td></tr>
      <tr><td>使用自己的 LLM API</td><td><span class="file-chip">llm.toml</span></td><td>enabled = true，填写 base_url、model、api_key_env；真实 key 放在环境变量里。</td><td>重启 App 或每日任务，让新环境变量被读取。</td></tr>
    </tbody>
  </table>
</section>

<section class="grid grid-3">
  <div class="panel">
    <h2>运行参数</h2>
    <table>
      <tbody>
        <tr><td>默认候选项目数</td><td>{html.escape(str(config.radar.get("max_candidates_per_run", "-")))}</td></tr>
        <tr><td>默认深度阅读数</td><td>{html.escape(str(config.radar.get("deep_review_limit", "-")))}</td></tr>
        <tr><td>报告时区</td><td>{html.escape(str(config.radar.get("timezone", "Asia/Shanghai")))}</td></tr>
      </tbody>
    </table>
    <div class="helper">
      <ol class="steps">
        <li><strong>候选项目数</strong>决定先看多少个 GitHub 候选。</li>
        <li><strong>深度阅读数</strong>决定读取多少个 README 并打分。</li>
        <li><strong>报告时区</strong>影响报告日期和每日任务的目标时间。</li>
      </ol>
    </div>
    <div class="actions section">{_open_form("radar_config", "打开运行参数")}</div>
  </div>
  <div class="panel">
    <h2>评分标准</h2>
    <p class="muted">领域相关度、可用性、文档、维护、社区、License、新颖性和 star 增长都在这里调整。</p>
    <div class="helper">想让项目更偏“能马上用”，提高 usability_evidence 和 readme_quality；想追踪爆发项目，提高 star_growth_3d。</div>
    <div class="actions">{_open_form("scoring_config", "打开评分权重")}</div>
  </div>
  <div class="panel">
    <h2>LLM API</h2>
    <table><tbody>{llm_table}</tbody></table>
    <div class="helper">
      <ol class="steps">
        <li>点击“打开 LLM 设置”，如果文件不存在会自动从示例创建。</li>
        <li>把 enabled 改为 true，填写 base_url、model 和 api_key_env。</li>
        <li>不要把真实 API Key 写进文件；把 Key 放到环境变量，例如 OPENAI_API_KEY。</li>
      </ol>
    </div>
    <div class="actions section">{_open_form("llm_config", "打开 LLM 设置")}{_open_form("llm_example", "打开示例")}</div>
  </div>
</section>

<section class="section panel">
  <h2>采集方向</h2>
  <p class="muted">采集方向是“你关心什么”。这里适合添加新行业、新技术、新公司类型或自定义关键词。</p>
  <div class="actions" style="margin-bottom: 12px;">{_open_form("topics_config", "打开采集方向")}</div>
  <table>
    <thead><tr><th>方向</th><th>状态</th><th>说明</th><th>关键词</th></tr></thead>
    <tbody>{topics}</tbody>
  </table>
</section>

<section class="section panel">
  <h2>GitHub 查询</h2>
  <p class="muted">GitHub 查询是“怎么找”。如果你只是添加兴趣方向，优先改采集方向；如果你明确知道 GitHub 搜索语法，再改这里。</p>
  <div class="actions" style="margin-bottom: 12px;">{_open_form("queries_config", "打开查询规则")}{_open_form("config", "打开参数文件夹")}{_open_form("readme", "打开使用说明")}</div>
  <table>
    <thead><tr><th>名称</th><th>查询语句</th></tr></thead>
    <tbody>{query_rows}</tbody>
  </table>
</section>
"""
    return _html_page("GitHub AI Radar Settings", body, active="settings")


def render_automation(paths: RadarPaths, notice: str = "") -> bytes:
    state = _latest_state(paths)
    job = _RUN_JOBS.get(str(paths.root), {})
    schedule = launchd_status()
    loaded = bool(schedule.get("loaded"))
    schedule_badge = f'<span class="pill {"ok" if loaded else "warn"}">{"已启用" if loaded else "未启用"}</span>'
    logs = "\n".join(
        f"<tr><td>{html.escape(item['name'])}</td><td>{item['size']} bytes</td><td>{html.escape(str(item['path']))}</td></tr>"
        for item in _logs(paths)
    ) or '<tr><td colspan="3" class="muted">还没有日志。</td></tr>'
    job_panel = ""
    if job:
        status = str(job.get("status", "-"))
        job_panel = f"""
<section class="section panel">
  <h2>当前手动任务</h2>
  <table><tbody>
    <tr><td>状态</td><td>{html.escape(status)}</td></tr>
    <tr><td>开始时间</td><td>{html.escape(_format_dt(job.get("started_at")))}</td></tr>
    <tr><td>结束时间</td><td>{html.escape(_format_dt(job.get("finished_at")))}</td></tr>
    <tr><td>错误</td><td>{html.escape(str(job.get("error", "-")))}</td></tr>
  </tbody></table>
</section>
"""
    body = f"""
{notice}
<h1>自动化</h1>
<p class="lead">这里查看每日计划是否启用、当前任务执行阶段，以及本地运行日志。</p>

<section class="grid grid-2">
  <div class="panel">
    <h2>每日自动化任务</h2>
    <table><tbody>
      <tr><td>状态</td><td>{schedule_badge}</td></tr>
      <tr><td>LaunchAgent</td><td>{html.escape(str(schedule.get("plist", "-")))}</td></tr>
      <tr><td>文件是否存在</td><td>{'是' if schedule.get("plist_exists") else '否'}</td></tr>
    </tbody></table>
  </div>
  <div class="panel">
    <h2>设置每日生成时间</h2>
    <form method="post" action="/actions/schedule/install" class="form-grid">
      <div><label for="schedule_timezone">报告时区</label><input id="schedule_timezone" name="timezone" value="Asia/Shanghai"></div>
      <div><label for="schedule_hour">小时</label><input id="schedule_hour" name="hour" type="number" min="0" max="23" value="10"></div>
      <div><label for="schedule_minute">分钟</label><input id="schedule_minute" name="minute" type="number" min="0" max="59" value="0"></div>
      <div><button class="button" type="submit">启用每日任务</button></div>
    </form>
    <div class="actions section">
      <form method="post" action="/actions/schedule/uninstall" class="inline-form"><button class="button danger" type="submit">停止每日任务</button></form>
    </div>
  </div>
</section>

{job_panel}

<section class="section panel">
  <h2>任务阶段</h2>
  <div class="timeline">{_stage_items(state)}</div>
</section>

<section class="section panel">
  <h2>日志</h2>
  <div class="actions" style="margin-bottom: 12px;">{_open_form("logs", "打开日志文件夹")}</div>
  <table>
    <thead><tr><th>文件</th><th>大小</th><th>位置</th></tr></thead>
    <tbody>{logs}</tbody>
  </table>
</section>
"""
    return _html_page("GitHub AI Radar Automation", body, active="automation")


def _status_json(paths: RadarPaths) -> bytes:
    active = _active_job(paths.root)
    payload = {
        "root": str(paths.root),
        "database": str(paths.database),
        "reports_dir": str(paths.reports_dir),
        "counts": table_counts(paths.database) if paths.database.exists() else {},
        "active_manual_job": active or {},
        "latest_state": _latest_state(paths),
        "schedule": launchd_status(),
        "reports": [
            {
                "date": item["date"],
                "status": item["status"],
                "markdown": str(item["markdown"]),
                "audit": str(item["audit"]),
                "state": str(item["state"]),
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

    def _send_redirect(self, location: str) -> None:
        content = _redirect(location)
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        notice = _notice(parsed.query)
        if path == "/":
            self._send(render_dashboard(self.paths, notice=notice))
            return
        if path == "/results":
            self._send(render_results(self.paths, notice=notice))
            return
        if path == "/settings":
            self._send(render_settings(self.paths, notice=notice))
            return
        if path == "/automation":
            self._send(render_automation(self.paths, notice=notice))
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
            body = f'<h1>报告 {html.escape(date)}</h1><p class="lead"><a href="/results">返回结果</a></p><pre>{content}</pre>'
            self._send(_html_page(f"Report {date}", body, active="results"))
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

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        values = parse_qs(self.rfile.read(length).decode("utf-8"))
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/actions/run":
                options = {
                    "timezone": values.get("timezone", ["Asia/Shanghai"])[0] or "Asia/Shanghai",
                    "max_candidates": _parse_int(values, "max_candidates", 100),
                    "deep_review_limit": _parse_int(values, "deep_review_limit", 10),
                }
                ok, message = _start_run(self.paths.root, options)
                level = "ok" if ok else "bad"
                self._send_redirect("/automation?" + urlencode({"notice": message, "level": level}))
                return
            if path == "/actions/schedule/install":
                timezone = values.get("timezone", ["Asia/Shanghai"])[0] or "Asia/Shanghai"
                hour = _parse_bounded_int(values, "hour", 10, 0, 23)
                minute = _parse_bounded_int(values, "minute", 0, 0, 59)
                install_launchd(self.paths.root, hour=hour, minute=minute, timezone=timezone)
                self._send_redirect("/automation?" + urlencode({"notice": "每日自动化任务已启用。", "level": "ok"}))
                return
            if path == "/actions/schedule/uninstall":
                uninstall_launchd()
                self._send_redirect("/automation?" + urlencode({"notice": "每日自动化任务已停止。", "level": "ok"}))
                return
            if path == "/actions/open":
                target = values.get("target", [""])[0]
                message = _open_target(self.paths, target)
                referer = self.headers.get("Referer") or "/"
                redirect_path = urlparse(referer).path or "/"
                self._send_redirect(redirect_path + "?" + urlencode({"notice": message, "level": "ok"}))
                return
        except Exception as exc:
            fallback = "/automation" if "schedule" in path or "run" in path else "/settings"
            self._send_redirect(fallback + "?" + urlencode({"notice": str(exc), "level": "bad"}))
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
