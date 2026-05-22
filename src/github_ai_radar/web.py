from __future__ import annotations

import html
import json
import platform
import shutil
import sqlite3
import subprocess
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from github_ai_radar.config import load_config, load_config_file, llm_status, write_config_file, write_secret
from github_ai_radar.paths import RadarPaths
from github_ai_radar.pipeline import STAGES, run_once
from github_ai_radar.reporter import render_markdown_as_html
from github_ai_radar.scheduler import install_launchd, launchd_status, uninstall_launchd
from github_ai_radar.storage import table_counts


STAGE_LABELS = {
    "init": "准备环境",
    "github_search": "检索 GitHub",
    "github_readme_review": "阅读 README",
    "event_sources": "采集外部来源",
    "scoring": "评分排序",
    "markdown_render": "生成报告",
    "audit_json_render": "生成审计记录",
    "final_verify": "验证文件",
    "completed": "完成",
}

STAGE_DESCRIPTIONS = {
    "init": "创建目录、读取配置并准备数据库。",
    "github_search": "根据关注方向和 GitHub 查询规则拉取候选项目。",
    "github_readme_review": "只读读取项目元数据和 README，不 clone、不执行代码。",
    "event_sources": "读取外部 RSS/Atom/公开新闻源，筛选候选事件。",
    "scoring": "结合文档、活跃度、License、风险和 star 增长计算分数。",
    "markdown_render": "写入 HTML 阅读版和 Markdown 源文件。",
    "audit_json_render": "写入机器可读审计记录。",
    "final_verify": "检查报告、HTML、审计 JSON 是否完整可读。",
    "completed": "报告已经生成，可以在结果页阅读。",
}

FAILURE_HINTS = {
    "init": "请先运行初始化，或检查当前目录是否可写。",
    "github_search": "请检查 GitHub CLI 是否已安装并完成登录，也确认网络可访问 GitHub。",
    "github_readme_review": "通常是单个仓库读取失败或 GitHub API 限制，可稍后重试。",
    "event_sources": "通常是外部 RSS/新闻源超时，可稍后重试或减少外部来源查询。",
    "markdown_render": "请检查报告目录是否可写。",
    "audit_json_render": "请检查报告目录是否可写，并确认磁盘空间充足。",
    "final_verify": "报告文件存在但校验失败，请查看日志中的具体错误。",
}

_RUN_LOCK = threading.Lock()
_RUN_JOBS: dict[str, dict[str, object]] = {}

_PIXEL_CAT = (
    "................",
    "...KK....KK.....",
    "..KGGK..KGGK....",
    "..KGGKKKKGGK....",
    ".KGGGGGGGGGGK...",
    ".KGGWGGGGWGGK...",
    ".KGGGBGGBGGGK...",
    ".KGGGGPPGGGGK...",
    ".KGGGPKKPGGGK...",
    "..KGGGWWGGGK....",
    "...KKGGGGKK.....",
    "....KYYYYK......",
    "...KGGGGGGK.....",
    "...KGG..GGK.....",
    "....KK..KK......",
    "................",
)
_PIXEL_CAT_COLORS = {
    "K": "#273142",
    "G": "#d9e3ef",
    "W": "#fff7dc",
    "P": "#f4a3b8",
    "B": "#2563eb",
    "Y": "#f6c343",
}


def _pixel_cat_logo() -> str:
    rects = []
    for y, row in enumerate(_PIXEL_CAT):
        for x, key in enumerate(row):
            color = _PIXEL_CAT_COLORS.get(key)
            if color:
                rects.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{color}"/>')
    return (
        '<svg class="pixel-cat" viewBox="0 0 16 16" role="img" aria-label="像素风小猫 logo" '
        'shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="0" y="0" width="16" height="16" rx="3" fill="#f8fafc"/>'
        f"{''.join(rects)}"
        "</svg>"
    )


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _report_metadata(audit_path: Path) -> dict[str, object]:
    audit = _read_json(audit_path)
    reviews = audit.get("reviews") or []
    events = audit.get("external_events") or []
    top_review = None
    if isinstance(reviews, list) and reviews:
        top_review = max(reviews, key=lambda item: int(item.get("score", {}).get("score") or 0))
    top_repo = "-"
    top_score = "-"
    if isinstance(top_review, dict):
        repo = top_review.get("repo") or {}
        score = top_review.get("score") or {}
        top_repo = str(repo.get("full_name") or "-")
        top_score = str(score.get("score") or "-")
    risk_count = 0
    for review in reviews if isinstance(reviews, list) else []:
        score = review.get("score") if isinstance(review, dict) else {}
        risk = str((score or {}).get("risk_notes") or "").strip().lower()
        benign = {"-", "none", "no obvious risk", "no major read-only risk signal found."}
        if risk and risk not in benign and "no major read-only risk" not in risk:
            risk_count += 1
    return {
        "review_count": len(reviews) if isinstance(reviews, list) else 0,
        "event_count": len(events) if isinstance(events, list) else 0,
        "top_repo": top_repo,
        "top_score": top_score,
        "risk_count": risk_count,
    }


def _reports(paths: RadarPaths) -> list[dict]:
    reports: list[dict] = []
    for markdown in sorted(paths.reports_dir.glob("*.md"), reverse=True):
        date = markdown.stem
        html_report = paths.reports_dir / f"{date}.html"
        audit = paths.reports_dir / f"{date}.audit.json"
        state = paths.state_dir / f"{date}.state.json"
        state_payload = _read_json(state)
        metadata = _report_metadata(audit)
        reports.append(
            {
                "date": date,
                "markdown": markdown,
                "html": html_report,
                "audit": audit,
                "state": state,
                "status": state_payload.get("status", "unknown"),
                "size": html_report.stat().st_size if html_report.exists() else markdown.stat().st_size,
                "state_payload": state_payload,
                **metadata,
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


def _quick_command(command: list[str], timeout: int = 4) -> tuple[bool, str]:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, output


def _health_items(paths: RadarPaths, state: dict | None = None) -> list[dict[str, str]]:
    state = state or _latest_state(paths)
    gh_path = shutil.which("gh")
    if gh_path:
        gh_ok, gh_output = _quick_command(["gh", "auth", "status"])
        gh_detail = "已登录" if gh_ok else (gh_output.splitlines()[0] if gh_output else "未完成登录")
    else:
        gh_ok = False
        gh_detail = "未找到 gh 命令"

    schedule = launchd_status()
    llm = llm_status(paths.root)
    report_ok = state.get("status") == "completed"
    db_ok = paths.database.exists()
    items = [
        {
            "label": "GitHub CLI",
            "status": "正常" if gh_ok else "需要处理",
            "detail": gh_detail,
            "tone": "ok" if gh_ok else "bad",
        },
        {
            "label": "本地数据库",
            "status": "正常" if db_ok else "未初始化",
            "detail": str(paths.database),
            "tone": "ok" if db_ok else "warn",
        },
        {
            "label": "每日任务",
            "status": "已启用" if schedule.get("loaded") else "未启用",
            "detail": "自动化页可调整时间",
            "tone": "ok" if schedule.get("loaded") else "warn",
        },
        {
            "label": "LLM API",
            "status": "已配置" if llm.get("api_key_present") else "可选",
            "detail": str(llm.get("model") or "未配置"),
            "tone": "ok" if llm.get("api_key_present") else "warn",
        },
        {
            "label": "最近报告",
            "status": "成功" if report_ok else "待生成",
            "detail": str(state.get("report_date") or "还没有完成报告"),
            "tone": "ok" if report_ok else "warn",
        },
    ]
    return items


def _health_panel(paths: RadarPaths, state: dict) -> str:
    rows = []
    for item in _health_items(paths, state):
        rows.append(
            '<div class="health-item">'
            f'<span class="pill {html.escape(item["tone"])}">{html.escape(item["status"])}</span>'
            f'<strong>{html.escape(item["label"])}</strong>'
            f'<span class="muted">{html.escape(item["detail"])}</span>'
            "</div>"
        )
    return "\n".join(rows)


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


def _parse_nonnegative_int(values: dict[str, list[str]], name: str, default: int) -> int:
    try:
        return max(0, int(values.get(name, [str(default)])[0]))
    except ValueError:
        return default


def _form_value(values: dict[str, list[str]], name: str, default: str = "") -> str:
    return values.get(name, [default])[0].strip()


def _form_bool(values: dict[str, list[str]], name: str) -> bool:
    return values.get(name, [""])[0] in {"1", "true", "on", "yes"}


def _lines_to_list(value: str) -> list[str]:
    lines: list[str] = []
    for chunk in value.replace(",", "\n").splitlines():
        item = chunk.strip()
        if item:
            lines.append(item)
    return lines


def _list_to_text(items: object) -> str:
    if not isinstance(items, list):
        return ""
    return "\n".join(str(item) for item in items)


def _field(name: str, value: object, *, input_type: str = "text", min_value: int | None = None, max_value: int | None = None) -> str:
    attrs = []
    if min_value is not None:
        attrs.append(f'min="{min_value}"')
    if max_value is not None:
        attrs.append(f'max="{max_value}"')
    attr_text = " ".join(attrs)
    return f'<input name="{html.escape(name)}" type="{html.escape(input_type)}" value="{html.escape(str(value))}" {attr_text}>'


def _textarea(name: str, value: object, rows: int = 3) -> str:
    return f'<textarea name="{html.escape(name)}" rows="{rows}">{html.escape(str(value))}</textarea>'


def _checked(value: object) -> str:
    return " checked" if bool(value) else ""


def _save_radar_settings(paths: RadarPaths, values: dict[str, list[str]]) -> str:
    payload = load_config_file(paths.root, "radar.toml")
    radar = payload.setdefault("radar", {})
    radar["timezone"] = _form_value(values, "timezone", "Asia/Shanghai") or "Asia/Shanghai"
    radar["report_time"] = _form_value(values, "report_time", "10:00") or "10:00"
    radar["report_style"] = _form_value(values, "report_style", "standard") or "standard"
    radar["max_candidates_per_run"] = _parse_int(values, "max_candidates_per_run", 100)
    radar["deep_review_limit"] = _parse_int(values, "deep_review_limit", 10)
    radar["read_only"] = _form_bool(values, "read_only")
    write_config_file(paths.root, "radar.toml", payload)
    return "运行参数已保存。"


def _save_llm_settings(paths: RadarPaths, values: dict[str, list[str]]) -> str:
    payload = load_config_file(paths.root, "llm.toml")
    llm = payload.setdefault("llm", {})
    llm["enabled"] = _form_bool(values, "enabled")
    llm["provider"] = _form_value(values, "provider", "openai_compatible") or "openai_compatible"
    llm["base_url"] = _form_value(values, "base_url", "https://api.openai.com/v1") or "https://api.openai.com/v1"
    llm["model"] = _form_value(values, "model", "gpt-4.1-mini") or "gpt-4.1-mini"
    llm["api_key_env"] = _form_value(values, "api_key_env", "OPENAI_API_KEY") or "OPENAI_API_KEY"
    llm["timeout_seconds"] = _parse_int(values, "timeout_seconds", 60)
    write_config_file(paths.root, "llm.toml", payload)
    api_key_value = _form_value(values, "api_key_value")
    if api_key_value:
        write_secret(paths.root, str(llm["api_key_env"]), api_key_value)
        return "LLM 设置和本地私有 API Key 已保存。"
    if _form_bool(values, "clear_api_key"):
        write_secret(paths.root, str(llm["api_key_env"]), "")
        return "LLM 设置已保存，并已清除本地私有 API Key。"
    return "LLM 设置已保存。"


def _save_topics(paths: RadarPaths, values: dict[str, list[str]]) -> str:
    count = _parse_bounded_int(values, "topic_count", 0, 0, 200)
    topics: list[dict[str, object]] = []
    for index in range(count):
        prefix = f"topic_{index}_"
        name = _form_value(values, prefix + "name")
        if not name:
            continue
        topics.append(
            {
                "name": name,
                "enabled": _form_bool(values, prefix + "enabled"),
                "description": _form_value(values, prefix + "description"),
                "github_terms": _lines_to_list(_form_value(values, prefix + "github_terms")),
                "source_terms": _lines_to_list(_form_value(values, prefix + "source_terms")),
            }
        )
    new_name = _form_value(values, "new_topic_name")
    if new_name:
        topics.append(
            {
                "name": new_name,
                "enabled": True,
                "description": _form_value(values, "new_topic_description"),
                "github_terms": _lines_to_list(_form_value(values, "new_topic_github_terms")),
                "source_terms": _lines_to_list(_form_value(values, "new_topic_source_terms")),
            }
        )
    write_config_file(paths.root, "topics.toml", {"topics": topics})
    return "采集方向已保存。"


def _save_queries(paths: RadarPaths, values: dict[str, list[str]]) -> str:
    payload = load_config_file(paths.root, "queries.toml")
    github_count = _parse_bounded_int(values, "github_query_count", 0, 0, 200)
    source_count = _parse_bounded_int(values, "source_query_count", 0, 0, 200)
    github_queries: list[dict[str, str]] = []
    source_queries: list[dict[str, str]] = []
    for index in range(github_count):
        name = _form_value(values, f"github_query_{index}_name")
        query = _form_value(values, f"github_query_{index}_query")
        if name and query:
            github_queries.append({"name": name, "query": query})
    for index in range(source_count):
        name = _form_value(values, f"source_query_{index}_name")
        query = _form_value(values, f"source_query_{index}_query")
        if name and query:
            source_queries.append({"name": name, "query": query})
    new_name = _form_value(values, "new_github_query_name")
    new_query = _form_value(values, "new_github_query")
    if new_name and new_query:
        github_queries.append({"name": new_name, "query": new_query})
    new_source_name = _form_value(values, "new_source_query_name")
    new_source_query = _form_value(values, "new_source_query")
    if new_source_name and new_source_query:
        source_queries.append({"name": new_source_name, "query": new_source_query})
    payload["github_queries"] = github_queries
    payload["source_queries"] = source_queries
    write_config_file(paths.root, "queries.toml", payload)
    return "查询规则已保存。GitHub 查询和外部来源查询会在下一次报告中生效。"


def _save_scoring(paths: RadarPaths, values: dict[str, list[str]]) -> str:
    payload = load_config_file(paths.root, "scoring.toml")
    for section_name in ("weights", "penalties"):
        section = payload.setdefault(section_name, {})
        for key in list(section.keys()):
            section[key] = _parse_nonnegative_int(values, f"{section_name}_{key}", int(section[key]))
    write_config_file(paths.root, "scoring.toml", payload)
    return "评分权重已保存。"


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
    .brand-lockup {{ display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 10px; align-items: center; margin-bottom: 24px; }}
    .app-logo {{
      width: 42px;
      height: 42px;
      border-radius: 8px;
      background: #f8fafc;
      display: grid;
      place-items: center;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.35), 0 8px 22px rgba(0,0,0,.22);
      overflow: hidden;
    }}
    .pixel-cat {{ width: 36px; height: 36px; display: block; image-rendering: pixelated; }}
    .brand {{ font-size: 18px; font-weight: 700; margin-bottom: 4px; }}
    .brand-sub {{ color: #bdc7d8; font-size: 12px; }}
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
    .grid-5 {{ grid-template-columns: repeat(5, minmax(0, 1fr)); }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .panel.soft {{ background: #fbfcfe; }}
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
    input, select, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      background: white;
      color: var(--ink);
      font: inherit;
    }}
    textarea {{ resize: vertical; min-height: 78px; }}
    input[type="checkbox"] {{ width: auto; transform: translateY(1px); }}
    .form-grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; align-items: end; }}
    .settings-form {{ display: grid; gap: 12px; }}
    .settings-form .row {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .settings-form .row-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .editable-list {{ display: grid; gap: 12px; }}
    .editable-item {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fbfcfe; }}
    .checkbox-line {{ display: flex; align-items: center; gap: 8px; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); background: #eef2f7; }}
    tr:last-child td {{ border-bottom: 0; }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 3px 8px; font-weight: 700; font-size: 12px; background: var(--soft); }}
    .pill.ok {{ color: var(--good); background: #dff8ec; }}
    .pill.warn {{ color: var(--warn); background: #fff3cf; }}
    .pill.bad {{ color: var(--bad); background: #fee4e2; }}
    .health-grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }}
    .health-item {{
      display: grid;
      gap: 6px;
      align-content: start;
      min-height: 92px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      padding: 12px;
    }}
    .report-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .report-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      padding: 14px;
      display: grid;
      gap: 10px;
    }}
    .report-card-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: start; }}
    .report-title {{ font-size: 17px; font-weight: 760; overflow-wrap: anywhere; }}
    .mini-metrics {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .mini-metric {{ border: 1px solid var(--line); border-radius: 8px; background: white; padding: 8px; }}
    .mini-metric strong {{ display: block; font-size: 18px; line-height: 1.2; }}
    .settings-tabs {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
    .settings-tabs a {{ border: 1px solid var(--line); background: white; border-radius: 8px; padding: 8px 10px; font-weight: 700; color: var(--ink); }}
    details.disclosure {{ padding: 0; overflow: hidden; }}
    details.disclosure > summary {{
      cursor: pointer;
      list-style: none;
      padding: 16px;
      font-weight: 760;
      border-bottom: 1px solid var(--line);
    }}
    details.disclosure > summary::-webkit-details-marker {{ display: none; }}
    .details-body {{ padding: 16px; }}
    .progress-shell {{ display: grid; gap: 8px; margin-bottom: 12px; }}
    .progress-label {{ display: flex; justify-content: space-between; gap: 10px; color: var(--muted); font-weight: 700; }}
    .progress-track {{ height: 10px; background: var(--soft); border-radius: 999px; overflow: hidden; border: 1px solid var(--line); }}
    .progress-fill {{ height: 100%; background: linear-gradient(90deg, #0b63ce, #0a7a4b); }}
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
    .stage.skipped .dot {{ background: #8a94a6; }}
    .stage-desc {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
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
      .grid-2, .grid-3, .grid-4, .grid-5, .form-grid, .settings-form .row, .settings-form .row-3, .health-grid, .report-grid, .mini-metrics {{ grid-template-columns: 1fr; }}
      .stage {{ grid-template-columns: 22px minmax(0, 1fr); }}
      .stage .muted {{ grid-column: 2; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand-lockup">
        <div class="app-logo">{_pixel_cat_logo()}</div>
        <div>
          <div class="brand">GitHub AI Radar</div>
          <div class="brand-sub">本地研究雷达控制台</div>
        </div>
      </div>
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
        elif state.get("status") == "completed" and index <= last_index:
            class_name = "skipped"
            label = "未记录"
            item = {"completed_at": "旧版本运行未包含此阶段"}
        else:
            class_name = "pending"
            label = "等待"
        detail_parts = []
        if "candidate_count" in item:
            detail_parts.append(f"候选 {item['candidate_count']} 个")
        if "review_count" in item:
            detail_parts.append(f"深读 {item['review_count']} 个")
        if "event_count" in item:
            detail_parts.append(f"外部事件 {item['event_count']} 条")
        if item.get("path"):
            detail_parts.append(str(item["path"]))
        if item.get("html_path"):
            detail_parts.append(str(item["html_path"]))
        if item.get("raw_path"):
            detail_parts.append(str(item["raw_path"]))
        detail = " / ".join(detail_parts) or _format_dt(item.get("completed_at"))
        rows.append(
            '<div class="stage {class_name}">'
            '<span class="dot"></span>'
            '<div><strong>{name}</strong><div class="stage-desc">{description}</div><div class="muted">{detail}</div></div>'
            '<span class="pill {pill}">{label}</span>'
            "</div>".format(
                class_name=class_name,
                name=html.escape(STAGE_LABELS.get(name, name)),
                description=html.escape(STAGE_DESCRIPTIONS.get(name, "")),
                detail=html.escape(detail),
                pill="ok" if class_name == "done" else "warn" if class_name in {"running", "skipped"} else "bad" if class_name == "failed" else "",
                label=html.escape(label),
            )
        )
    return "\n".join(rows)


def _stage_progress(state: dict) -> str:
    completed = {item.get("name") for item in state.get("stages", []) if isinstance(item, dict)}
    count = len([name for name in STAGES if name in completed])
    if state.get("status") == "completed":
        count = len(STAGES)
    percent = int((count / len(STAGES)) * 100) if STAGES else 0
    status = str(state.get("status") or "未生成")
    return (
        '<div class="progress-shell">'
        f'<div class="progress-label"><span>任务进度</span><span>{html.escape(status)} · {percent}%</span></div>'
        '<div class="progress-track">'
        f'<div class="progress-fill" style="width:{percent}%"></div>'
        "</div></div>"
    )


def _failure_hint(state: dict) -> str:
    if state.get("status") != "failed":
        return ""
    last = str(state.get("last_successful_stage") or "init")
    next_index = STAGES.index(last) + 1 if last in STAGES and STAGES.index(last) + 1 < len(STAGES) else 0
    failed_stage = STAGES[next_index] if next_index < len(STAGES) else last
    hint = FAILURE_HINTS.get(failed_stage, "请打开日志查看具体错误。")
    errors = state.get("errors") or []
    detail = ""
    if errors and isinstance(errors[-1], dict):
        detail = str(errors[-1].get("error") or "")
    return (
        '<div class="notice bad">'
        f'最近一次任务失败：{html.escape(STAGE_LABELS.get(failed_stage, failed_stage))}。'
        f'{html.escape(hint)}'
        + (f'<br><span class="muted">{html.escape(detail)}</span>' if detail else "")
        + "</div>"
    )


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
        f"<td>{html.escape(str(item.get('review_count', 0)))}</td>"
        f"<td>{html.escape(str(item.get('event_count', 0)))}</td>"
        f"<td>{html.escape(str(item.get('top_repo') or '-'))}<br><span class=\"muted\">分数 {html.escape(str(item.get('top_score') or '-'))}</span></td>"
        f"<td><a href=\"/report/{html.escape(item['date'])}\">HTML 阅读版</a> · "
        f"<a href=\"/markdown/{html.escape(item['date'])}\">Markdown</a> · "
        f"<a href=\"/audit/{html.escape(item['date'])}\">审计 JSON</a></td>"
        "</tr>"
        for item in reports[:limit]
    ) or '<tr><td colspan="6" class="muted">还没有报告。可以先回到操作台点击“立即生成报告”。</td></tr>'


def _report_cards(reports: list[dict], limit: int = 12) -> str:
    cards = []
    for item in reports[:limit]:
        status_tone = "ok" if item["status"] == "completed" else "warn"
        cards.append(
            '<article class="report-card">'
            '<div class="report-card-head">'
            f'<div><div class="muted">报告日期</div><div class="report-title">{html.escape(item["date"])}</div></div>'
            f'<span class="pill {status_tone}">{html.escape(str(item["status"]))}</span>'
            "</div>"
            f'<div class="muted">最高信号：{html.escape(str(item.get("top_repo") or "-"))} · 分数 {html.escape(str(item.get("top_score") or "-"))}</div>'
            '<div class="mini-metrics">'
            f'<div class="mini-metric"><strong>{html.escape(str(item.get("review_count", 0)))}</strong><span class="muted">项目分析</span></div>'
            f'<div class="mini-metric"><strong>{html.escape(str(item.get("event_count", 0)))}</strong><span class="muted">外部事件</span></div>'
            f'<div class="mini-metric"><strong>{html.escape(str(item.get("risk_count", 0)))}</strong><span class="muted">风险提示</span></div>'
            "</div>"
            '<div class="actions">'
            f'<a class="button" href="/report/{html.escape(item["date"])}">阅读报告</a>'
            f'<a class="button secondary" href="/markdown/{html.escape(item["date"])}">Markdown</a>'
            f'<a class="button secondary" href="/audit/{html.escape(item["date"])}">审计 JSON</a>'
            "</div>"
            "</article>"
        )
    return "\n".join(cards) or '<div class="panel muted">还没有报告。可以先回到操作台点击“立即生成报告”。</div>'


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


def _radar_settings_form(config: object) -> str:
    radar = getattr(config, "radar")
    return f"""
<form method="post" action="/actions/settings/radar" class="settings-form">
  <div class="row row-3">
    <div><label>报告时区</label>{_field("timezone", radar.get("timezone", "Asia/Shanghai"))}</div>
    <div><label>报告时间</label>{_field("report_time", radar.get("report_time", "10:00"))}</div>
    <div><label>报告版本</label>{_field("report_style", radar.get("report_style", "standard"))}</div>
  </div>
  <div class="row">
    <div><label>默认候选项目数</label>{_field("max_candidates_per_run", radar.get("max_candidates_per_run", 100), input_type="number", min_value=1)}</div>
    <div><label>默认深度阅读数</label>{_field("deep_review_limit", radar.get("deep_review_limit", 10), input_type="number", min_value=1)}</div>
  </div>
  <label class="checkbox-line"><input type="checkbox" name="read_only" value="1"{_checked(radar.get("read_only", True))}>只读研究模式</label>
  <div class="actions"><button class="button" type="submit">保存运行参数</button></div>
</form>
"""


def _llm_form(llm_status_payload: dict[str, object]) -> str:
    configured = bool(llm_status_payload.get("configured"))
    llm_data = {
        "enabled": llm_status_payload.get("enabled", False),
        "provider": llm_status_payload.get("provider") or "openai_compatible",
        "base_url": llm_status_payload.get("base_url") or "https://api.openai.com/v1",
        "model": llm_status_payload.get("model") or "gpt-4.1-mini",
        "api_key_env": llm_status_payload.get("api_key_env") or "OPENAI_API_KEY",
        "timeout_seconds": llm_status_payload.get("timeout_seconds") or 60,
    }
    return f"""
<form method="post" action="/actions/settings/llm" class="settings-form">
  <label class="checkbox-line"><input type="checkbox" name="enabled" value="1"{_checked(llm_data["enabled"])}>启用 LLM 辅助分析</label>
  <div class="row">
    <div><label>Provider</label>{_field("provider", llm_data["provider"])}</div>
    <div><label>模型</label>{_field("model", llm_data["model"])}</div>
  </div>
  <div><label>OpenAI-compatible Base URL</label>{_field("base_url", llm_data["base_url"])}</div>
  <div class="row">
    <div><label>API Key 变量名</label>{_field("api_key_env", llm_data["api_key_env"])}</div>
    <div><label>超时时间秒数</label>{_field("timeout_seconds", llm_data["timeout_seconds"], input_type="number", min_value=1)}</div>
  </div>
  <div><label>API Key</label><input name="api_key_value" type="password" placeholder="留空表示不修改已保存的本地私有 key"></div>
  <label class="checkbox-line"><input type="checkbox" name="clear_api_key" value="1">清除已保存的本地私有 API Key</label>
  <div class="helper">Key 会保存到 <span class="file-chip">config/secrets.env</span>，该文件已被 git 忽略。配置文件状态：{'已创建' if configured else '未创建'}；Key 状态：{'已检测到' if llm_status_payload.get("api_key_present") else '未检测到'}。</div>
  <div class="actions"><button class="button" type="submit">保存 LLM 设置</button></div>
</form>
"""


def _scoring_form(config: object) -> str:
    rows = []
    for section_name, title in (("weights", "加分权重"), ("penalties", "降权规则")):
        section = getattr(config, section_name)
        controls = "\n".join(
            f'<div><label>{html.escape(str(key))}</label>{_field(f"{section_name}_{key}", value, input_type="number", min_value=0)}</div>'
            for key, value in section.items()
        )
        rows.append(f'<h3>{title}</h3><div class="row row-3">{controls}</div>')
    return f"""
<form method="post" action="/actions/settings/scoring" class="settings-form">
  {''.join(rows)}
  <div class="actions"><button class="button" type="submit">保存评分权重</button></div>
</form>
"""


def _topics_form(config: object) -> str:
    topic_items = []
    topics = getattr(config, "topics")
    for index, item in enumerate(topics):
        prefix = f"topic_{index}_"
        topic_items.append(
            f"""
<div class="editable-item">
  <div class="row">
    <div><label>方向名称</label>{_field(prefix + "name", item.get("name", ""))}</div>
    <div><label class="checkbox-line"><input type="checkbox" name="{prefix}enabled" value="1"{_checked(item.get("enabled"))}>启用这个方向</label></div>
  </div>
  <div><label>说明</label>{_field(prefix + "description", item.get("description", ""))}</div>
  <div class="row">
    <div>
      <label>GitHub 关键词，每行一个</label>
      {_textarea(prefix + "github_terms", _list_to_text(item.get("github_terms")), rows=5)}
      <div class="muted">当前版本会立即用于 GitHub 项目搜索。</div>
    </div>
    <div>
      <label>外部来源关键词，每行一个</label>
      {_textarea(prefix + "source_terms", _list_to_text(item.get("source_terms")), rows=5)}
      <div class="muted">当前版本会用于外部来源采集，适合写公司公告、监管、论文、合作、财报等关键词。</div>
    </div>
  </div>
</div>
"""
        )
    return f"""
<form method="post" action="/actions/settings/topics" class="settings-form">
  <input type="hidden" name="topic_count" value="{len(topics)}">
  <div class="editable-list">{''.join(topic_items)}</div>
  <div class="editable-item">
    <h3>新增方向</h3>
    <div class="row">
      <div><label>方向名称</label>{_field("new_topic_name", "")}</div>
      <div><label>说明</label>{_field("new_topic_description", "")}</div>
    </div>
    <div class="row">
      <div><label>GitHub 关键词，每行一个</label>{_textarea("new_topic_github_terms", "", rows=4)}<div class="muted">当前版本会立即用于 GitHub 搜索。</div></div>
      <div><label>外部来源关键词，每行一个</label>{_textarea("new_topic_source_terms", "", rows=4)}<div class="muted">用于外部 RSS/公开新闻源查询。</div></div>
    </div>
  </div>
  <div class="actions"><button class="button" type="submit">保存采集方向</button></div>
</form>
"""


def _queries_form(config: object) -> str:
    github_items = []
    source_items = []
    github_queries = getattr(config, "github_queries")
    source_queries = getattr(config, "source_queries")
    for index, item in enumerate(github_queries):
        prefix = f"github_query_{index}_"
        github_items.append(
            f"""
<div class="editable-item">
  <div><label>名称</label>{_field(prefix + "name", item.get("name", ""))}</div>
  <div><label>GitHub 查询语句</label>{_textarea(prefix + "query", item.get("query", ""), rows=2)}</div>
</div>
"""
        )
    for index, item in enumerate(source_queries):
        prefix = f"source_query_{index}_"
        source_items.append(
            f"""
<div class="editable-item">
  <div><label>名称</label>{_field(prefix + "name", item.get("name", ""))}</div>
  <div><label>外部来源查询语句</label>{_textarea(prefix + "query", item.get("query", ""), rows=2)}</div>
</div>
"""
        )
    return f"""
<form method="post" action="/actions/settings/queries" class="settings-form">
  <input type="hidden" name="github_query_count" value="{len(github_queries)}">
  <input type="hidden" name="source_query_count" value="{len(source_queries)}">
  <h3>当前生效：GitHub 查询</h3>
  <p class="muted">这些查询会在下一次报告中立即用于检索 GitHub 仓库。适合写明确的 GitHub 搜索语法，例如 <span class="file-chip">stars:&gt;=50</span>、<span class="file-chip">created:&gt;=${{date_minus_14}}</span>、<span class="file-chip">pushed:&gt;=${{date_minus_30}}</span>。</p>
  <div class="editable-list">{''.join(github_items)}</div>
  <div class="editable-item">
    <h3>新增 GitHub 查询</h3>
    <div class="row">
      <div><label>名称</label>{_field("new_github_query_name", "")}</div>
      <div><label>查询语句</label>{_textarea("new_github_query", "", rows=2)}</div>
    </div>
  </div>
  <h3>当前生效：外部来源查询</h3>
  <p class="muted">这些查询会通过 RSS/Atom/公开新闻源检索外部事件，优先筛选官方、监管、研究和高信号来源。也可以直接填写 RSS/Atom URL。</p>
  <div class="editable-list">{''.join(source_items)}</div>
  <div class="editable-item">
    <h3>新增外部来源查询</h3>
    <div class="row">
      <div><label>名称</label>{_field("new_source_query_name", "")}</div>
      <div><label>查询语句或 RSS/Atom URL</label>{_textarea("new_source_query", "", rows=2)}</div>
    </div>
  </div>
  <div class="actions"><button class="button" type="submit">保存查询规则</button></div>
</form>
"""


def render_dashboard(paths: RadarPaths, notice: str = "") -> bytes:
    counts = table_counts(paths.database) if paths.database.exists() else {}
    reports = _reports(paths)
    state = _latest_state(paths)
    job = _RUN_JOBS.get(str(paths.root))
    active = _active_job(paths.root)
    status_text = "运行中" if active else state.get("status", "未生成")
    cards = [
        ("报告", len(reports), "结果页查看 HTML 阅读版和审计 JSON"),
        ("项目", counts.get("repositories", 0), "本地 SQLite 已记录项目"),
        ("外部事件", counts.get("events", 0), "来源采集器筛选出的事件"),
        ("来源", counts.get("sources", 0), "已记录的公开来源链接"),
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
            report_path = result.get("html") or result.get("markdown") if isinstance(result, dict) else ""
            job_notice = f'<div class="notice ok">最近一次手动运行已完成。报告：{html.escape(str(report_path))}</div>'
    body = f"""
{notice}
{job_notice}
<h1>操作台</h1>
<p class="lead">这里是普通用户入口：生成报告、查看结果、设置参数、管理每日自动化。</p>
<div class="grid grid-5">{card_html}</div>

<section class="section panel">
  <h2>系统健康</h2>
  <div class="health-grid">{_health_panel(paths, state)}</div>
</section>

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
    <p class="muted">采集方向、查询词、评分权重、LLM API 都可以在“参数”页直接保存。</p>
    <div class="actions"><a class="button" href="/settings">查看参数</a></div>
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
    {_failure_hint(state)}
    {_stage_progress(state)}
    <div class="timeline">{_stage_items(state)}</div>
  </div>
  <div class="panel">
    <h2>最近报告</h2>
    <table>
      <thead><tr><th>日期</th><th>状态</th><th>项目</th><th>事件</th><th>最高信号</th><th>打开</th></tr></thead>
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
<p class="lead">这里集中查看每天的 HTML 阅读版报告、Markdown 源文件、机器审计 JSON 和最近的项目分析记录。</p>
<section class="panel">
  <h2>报告中心</h2>
  <div class="actions" style="margin-bottom: 12px;">{_open_form("reports", "打开报告文件夹")}{_open_form("data", "打开数据库文件夹")}</div>
  <div class="report-grid">{_report_cards(reports, limit=12)}</div>
</section>
<section class="section panel">
  <h2>报告索引</h2>
  <table>
    <thead><tr><th>日期</th><th>状态</th><th>项目</th><th>事件</th><th>最高信号</th><th>打开</th></tr></thead>
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
    body = f"""
{notice}
<h1>参数</h1>
<p class="lead">常用设置放在前面，高级查询和评分规则默认折叠。保存后回到操作台立即生成一次报告即可生效。</p>

<div class="settings-tabs">
  <a href="#run">运行参数</a>
  <a href="#topics">采集方向</a>
  <a href="#llm">LLM API</a>
  <a href="#queries">高级查询</a>
  <a href="#scoring">评分规则</a>
  <a href="/automation">每日自动化</a>
</div>

<section class="section panel">
  <h2>常见目标对照表</h2>
  <table>
    <thead><tr><th>我想做什么</th><th>在哪里改</th><th>怎么改</th><th>之后做什么</th></tr></thead>
    <tbody>
      <tr><td>添加新的信息方向</td><td>采集方向</td><td>填写新增方向名称、说明和关键词，点击保存。</td><td>保存后回操作台立即生成报告。</td></tr>
      <tr><td>让搜索更宽或更窄</td><td>查询规则</td><td>调整 stars、created、pushed、topic 等条件；stars 越低越宽，时间窗口越长越宽。</td><td>生成一次报告观察候选数量。</td></tr>
      <tr><td>控制每天看多少项目</td><td>运行参数</td><td>修改候选项目数和深度阅读数。</td><td>候选多会更慢，深读多会更详细。</td></tr>
      <tr><td>调整推荐分数</td><td>评分标准</td><td>修改加分权重和降权规则。</td><td>新报告会使用新的评分权重。</td></tr>
      <tr><td>使用自己的 LLM API</td><td>LLM API</td><td>启用 LLM，填写 base_url、model 和 API Key。</td><td>新任务会读取保存后的设置。</td></tr>
    </tbody>
  </table>
</section>

<section id="run" class="section panel">
  <h2>运行参数</h2>
  <p class="muted">这里决定每次报告看多少项目、读多深，以及报告日期使用哪个时区。</p>
  {_radar_settings_form(config)}
  <div class="helper">
    <ol class="steps">
      <li><strong>候选项目数</strong>决定先看多少个 GitHub 候选。</li>
      <li><strong>深度阅读数</strong>决定读取多少个 README 并打分。</li>
      <li><strong>报告时区</strong>影响报告日期和每日任务的目标时间。</li>
    </ol>
  </div>
</section>

<section id="topics" class="section panel">
  <h2>采集方向</h2>
  <p class="muted">采集方向是“你关心什么”。GitHub 关键词会用于项目搜索；外部来源关键词会用于 RSS/Atom/公开新闻源采集。</p>
  {_topics_form(config)}
</section>

<section id="llm" class="section panel">
  <h2>LLM API</h2>
  <p class="muted">这是可选能力。不开启时，雷达仍然可以正常生成基础报告。</p>
  {_llm_form(llm)}
  <div class="helper">
    <ol class="steps">
      <li>API Key 不写进公开配置文件，会保存到本地私有 <span class="file-chip">config/secrets.env</span>。</li>
      <li>如果你使用 OpenAI 官方 API，base_url 保持默认即可。</li>
      <li>如果你使用兼容服务，填写服务商提供的 OpenAI-compatible 地址。</li>
    </ol>
  </div>
</section>

<details id="queries" class="section panel disclosure">
  <summary>高级：精确查询规则</summary>
  <div class="details-body">
    <p class="muted">如果你只是添加兴趣方向，优先改“采集方向”。这里适合填写明确的 GitHub 搜索语法、外部 RSS/Atom URL 或更窄的新闻查询。</p>
    {_queries_form(config)}
  </div>
</details>

<details id="scoring" class="section panel disclosure">
  <summary>高级：评分规则</summary>
  <div class="details-body">
    <p class="muted">领域相关度、可用性、文档、维护、社区、License、新颖性和 star 增长都在这里调整。</p>
    <div class="helper">想让项目更偏“能马上用”，提高 usability_evidence 和 readme_quality；想追踪爆发项目，提高 star_growth_3d。</div>
    {_scoring_form(config)}
  </div>
</details>

<section class="section grid grid-3">
  <div class="panel">
    <h2>下一步</h2>
    <p class="muted">保存参数后，回到操作台生成一次报告，确认候选数量和报告内容符合预期。</p>
    <div class="actions"><a class="button" href="/">去操作台</a><a class="button secondary" href="/results">查看结果</a></div>
  </div>
  <div class="panel">
    <h2>本地文件</h2>
    <p class="muted">所有配置仍然保存在本地，可以随时打开文件夹检查。</p>
    <div class="actions">{_open_form("config", "打开配置文件夹")}</div>
  </div>
  <div class="panel">
    <h2>每日自动化</h2>
    <p class="muted">报告生成时间和任务启停在自动化页管理。</p>
    <div class="actions"><a class="button secondary" href="/automation">管理自动化</a></div>
  </div>
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
    <div class="helper">每日任务由系统 launchd 触发，不依赖 Codex 对话。失败时优先查看下方阶段和日志。</div>
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
  {_failure_hint(state)}
  {_stage_progress(state)}
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
                "html": str(item["html"]) if item["html"].exists() else None,
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
            html_report = self.paths.reports_dir / f"{date}.html"
            markdown = self.paths.reports_dir / f"{date}.md"
            if html_report.exists():
                self._send(html_report.read_bytes(), "text/html; charset=utf-8")
                return
            if not markdown.exists():
                self._send(b"report not found", "text/plain; charset=utf-8", 404)
                return
            content = render_markdown_as_html(markdown.read_text(encoding="utf-8"), title=f"Report {date}")
            self._send(content.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path.startswith("/markdown/"):
            date = path.rsplit("/", 1)[-1]
            markdown = self.paths.reports_dir / f"{date}.md"
            if not markdown.exists():
                self._send(b"markdown not found", "text/plain; charset=utf-8", 404)
                return
            self._send(markdown.read_bytes(), "text/markdown; charset=utf-8")
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
            if path == "/actions/settings/radar":
                message = _save_radar_settings(self.paths, values)
                self._send_redirect("/settings?" + urlencode({"notice": message, "level": "ok"}))
                return
            if path == "/actions/settings/llm":
                message = _save_llm_settings(self.paths, values)
                self._send_redirect("/settings?" + urlencode({"notice": message, "level": "ok"}))
                return
            if path == "/actions/settings/topics":
                message = _save_topics(self.paths, values)
                self._send_redirect("/settings?" + urlencode({"notice": message, "level": "ok"}))
                return
            if path == "/actions/settings/queries":
                message = _save_queries(self.paths, values)
                self._send_redirect("/settings?" + urlencode({"notice": message, "level": "ok"}))
                return
            if path == "/actions/settings/scoring":
                message = _save_scoring(self.paths, values)
                self._send_redirect("/settings?" + urlencode({"notice": message, "level": "ok"}))
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
