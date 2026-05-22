from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _repo_line(review: dict[str, Any]) -> str:
    repo = review["repo"]
    growth = review["score"]["scoring"]["growth"]["3d"]
    growth_text = (
        f"+{growth['delta']} stars / 3d"
        if growth.get("status") == "ok"
        else "3日增长历史不足"
    )
    return (
        f"| [{repo['full_name']}]({repo['url']}) | {review['score']['score']} | "
        f"{repo.get('language') or ''} | {repo.get('stars') or 0} | {growth_text} | "
        f"{review['score']['recommendation']} |"
    )


def _event_block(event: dict[str, Any]) -> list[str]:
    facts = event.get("facts") or []
    lines = [
        f"### {event.get('title') or '未命名事件'}",
        "",
        f"- 来源：{event.get('url')}",
        f"- 发布方：{event.get('publisher') or 'unknown'} / 类型：{event.get('source_type') or 'unknown'} / 匹配查询：{event.get('query_name') or '-'}",
    ]
    if event.get("published_at"):
        lines.append(f"- 发布时间：{event['published_at']}")
    if event.get("summary"):
        lines.append(f"- 摘要：{event['summary']}")
    if facts:
        lines.append("- 事实：")
        lines.extend(f"  - {fact}" for fact in facts[:3])
    if event.get("inference"):
        lines.append(f"- 推断：{event['inference']}")
    lines.append("")
    return lines


def _event_section(events: list[dict[str, Any]], domain: str, empty_text: str) -> list[str]:
    selected = [event for event in events if event.get("domain") == domain]
    if not selected:
        return [empty_text, ""]
    lines: list[str] = []
    for event in selected[:5]:
        lines.extend(_event_block(event))
    return lines


def _html_text(value: object) -> str:
    return html.escape(str(value or ""))


def _html_link(url: object, label: object | None = None) -> str:
    href = str(url or "")
    if not href:
        return ""
    return f'<a href="{html.escape(href)}">{html.escape(str(label or href))}</a>'


def render_markdown(payload: dict[str, Any]) -> str:
    reviews = sorted(payload["reviews"], key=lambda item: item["score"]["score"], reverse=True)
    top = reviews[: payload.get("deep_review_limit", 10)]
    external_events = sorted(payload.get("external_events") or [], key=lambda item: item.get("score", 0), reverse=True)
    lines = [
        "# 每日 GitHub AI Radar 报告",
        "",
        f"报告日期：{payload['report_date']}（{payload['timezone']}）",
        f"生成时间：{payload['generated_at']}",
        "运行模式：本地 app 自动生成；只读分析，未 clone、未安装依赖、未执行第三方代码。",
        "",
        "## 执行摘要",
        "",
        f"- 本次执行了 {len(payload['queries'])} 条 GitHub 查询，去重后候选 {payload['candidate_count']} 个。",
        f"- 写入/更新 repository snapshots：{payload['candidate_count']} 条候选快照。",
        f"- 深度只读 review：{len(reviews)} 个项目。",
        f"- 外部来源采集：匹配到 {len(external_events)} 条候选事件，优先使用官方/监管/研究/高信号来源。",
        "- 3 日 star 增长只使用本地历史快照；历史不足时标记为 `insufficient_history`。",
        "",
        "## 今日高信号 GitHub 项目",
        "",
        "| 项目 | 分数 | 语言 | Stars | 3日增长 | 建议 |",
        "| --- | ---: | --- | ---: | --- | --- |",
    ]
    lines.extend(_repo_line(review) for review in top)
    lines.extend(
        [
            "",
            "## 重点项目分析",
            "",
        ]
    )
    for review in top:
        repo = review["repo"]
        score = review["score"]
        lines.extend(
            [
                f"### {repo['full_name']}",
                "",
                f"- 链接：{repo['url']}",
                f"- 描述：{repo.get('description') or '无描述'}",
                f"- 当前信号：{repo.get('stars') or 0} stars / {repo.get('forks') or 0} forks / license `{repo.get('license_key') or 'unknown'}`",
                f"- 分数：{score['score']}，建议：`{score['recommendation']}`",
                f"- README 质量：{score['readme_quality']}",
                f"- 可用性判断：{score['usability_notes']}",
                f"- 风险：{score['risk_notes']}",
                "",
            ]
        )
    lines.extend(
        [
            "## AI / 高科技 / 国际金融事件观察",
            "",
        ]
    )
    lines.extend(
        _event_section(
            external_events,
            "ai_finance_high_tech",
            "本次外部来源采集未匹配到足够高信号的 AI/高科技/国际金融事件。",
        )
    )
    lines.extend(
        [
            "## AI / 生物制药协作观察",
            "",
        ]
    )
    lines.extend(
        _event_section(
            external_events,
            "ai_biopharma",
            "本次外部来源采集未匹配到足够高信号的 AI/生物制药协作事件。",
        )
    )
    other_events = [event for event in external_events if event.get("domain") == "ai_applications"]
    if other_events:
        lines.extend(["## AI 应用与工具生态事件观察", ""])
        for event in other_events[:3]:
            lines.extend(_event_block(event))
    lines.extend(
        [
            "## 风险与不确定性",
            "",
            "- README/metadata 只能判断表面可用性，不能证明项目真实可运行。",
            "- 新项目 star/fork 可能受推广影响，需要结合后续快照观察。",
            "- computer-use/browser automation 项目往往涉及敏感权限，后续试跑必须隔离。",
            "- 外部来源采集来自 RSS/Atom/公开新闻源查询，只做候选事件筛选；事实必须以原始链接为准。",
            "- 首次运行时 3 日/7 日/30 日增长通常历史不足。",
            "",
            "## 建议后续动作",
            "",
            "- 将 `deep_read` 项目加入 watchlist，每日追踪。",
            "- 连续运行至少 4 天后启用 3 日 star 增长作为真实排名信号。",
            "- 对高影响外部事件建立 source trust 规则和人工复核流程。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(payload: dict[str, Any]) -> str:
    reviews = sorted(payload["reviews"], key=lambda item: item["score"]["score"], reverse=True)
    top = reviews[: payload.get("deep_review_limit", 10)]
    external_events = sorted(payload.get("external_events") or [], key=lambda item: item.get("score", 0), reverse=True)
    report_date = _html_text(payload["report_date"])
    title = f"每日 GitHub AI Radar 报告 - {report_date}"

    repo_rows = "\n".join(_repo_html_row(review) for review in top) or (
        '<tr><td colspan="6" class="muted">本次没有可展示的 GitHub 项目。</td></tr>'
    )
    repo_cards = "\n".join(_repo_html_card(review) for review in top) or '<p class="muted">本次没有重点项目分析。</p>'
    finance_events = _event_html_section(
        external_events,
        "ai_finance_high_tech",
        "本次外部来源采集未匹配到足够高信号的 AI/高科技/国际金融事件。",
    )
    biopharma_events = _event_html_section(
        external_events,
        "ai_biopharma",
        "本次外部来源采集未匹配到足够高信号的 AI/生物制药协作事件。",
    )
    app_events = _event_html_section(
        external_events,
        "ai_applications",
        "本次外部来源采集未匹配到额外 AI 应用与工具生态事件。",
        limit=3,
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #d9e0ea;
      --soft: #eef3f8;
      --accent: #0b63ce;
      --good: #0a7a4b;
      --warn: #9a6700;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 15px/1.68 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .page {{ max-width: 1040px; margin: 0 auto; padding: 28px 18px 46px; }}
    header {{ margin-bottom: 18px; }}
    .eyebrow {{ color: var(--muted); font-weight: 700; font-size: 13px; }}
    h1 {{ margin: 4px 0 8px; font-size: 30px; line-height: 1.22; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 21px; }}
    h3 {{ margin: 0 0 8px; font-size: 17px; }}
    .lead {{ color: var(--muted); margin: 0; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }}
    .button {{
      display: inline-block;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      padding: 8px 11px;
      font-weight: 700;
    }}
    .button.primary {{ background: var(--accent); border-color: var(--accent); color: white; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-top: 14px;
    }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .metric {{ background: #fbfcfe; border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .metric strong {{ display: block; font-size: 24px; line-height: 1.2; }}
    .muted {{ color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); background: #eef2f7; }}
    tr:last-child td {{ border-bottom: 0; }}
    .analysis-list {{ display: grid; gap: 12px; }}
    .item {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfe;
      padding: 14px;
    }}
    .item.repo {{ border-left: 4px solid var(--accent); }}
    .item.event {{ border-left: 4px solid #0a7a4b; }}
    .meta {{ color: var(--muted); font-size: 13px; margin: 4px 0 10px; }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 700; background: var(--soft); }}
    .pill.good {{ color: var(--good); background: #dff8ec; }}
    .risk-section {{ border-color: #fecdca; background: #fff8f7; }}
    .risk-list {{ margin: 0; padding-left: 20px; }}
    .risk-list li {{ margin: 6px 0; }}
    @media (max-width: 760px) {{
      .summary {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      table {{ font-size: 13px; }}
      h1 {{ font-size: 25px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header>
      <div class="eyebrow">GitHub AI Radar</div>
      <h1>每日研究报告</h1>
      <p class="lead">报告日期：{report_date}（{_html_text(payload['timezone'])}）｜生成时间：{_html_text(payload['generated_at'])}</p>
      <div class="toolbar">
        <a class="button primary" href="/results">返回结果</a>
        <a class="button" href="/markdown/{report_date}">Markdown 源文件</a>
        <a class="button" href="/audit/{report_date}">审计 JSON</a>
      </div>
    </header>

    <section>
      <h2>执行摘要</h2>
      <div class="summary">
        <div class="metric"><strong>{len(payload['queries'])}</strong><span>GitHub 查询</span></div>
        <div class="metric"><strong>{payload['candidate_count']}</strong><span>候选项目</span></div>
        <div class="metric"><strong>{len(reviews)}</strong><span>深度只读 review</span></div>
        <div class="metric"><strong>{len(external_events)}</strong><span>外部候选事件</span></div>
      </div>
      <p class="muted">运行模式：本地 app 自动生成；只读分析，未 clone、未安装依赖、未执行第三方代码。3 日 star 增长只使用本地历史快照。</p>
    </section>

    <section>
      <h2>今日高信号 GitHub 项目</h2>
      <table>
        <thead><tr><th>项目</th><th>分数</th><th>语言</th><th>Stars</th><th>3日增长</th><th>建议</th></tr></thead>
        <tbody>{repo_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>重点项目分析</h2>
      <div class="analysis-list">{repo_cards}</div>
    </section>

    <section>
      <h2>AI / 高科技 / 国际金融事件观察</h2>
      <div class="analysis-list">{finance_events}</div>
    </section>

    <section>
      <h2>AI / 生物制药协作观察</h2>
      <div class="analysis-list">{biopharma_events}</div>
    </section>

    <section>
      <h2>AI 应用与工具生态事件观察</h2>
      <div class="analysis-list">{app_events}</div>
    </section>

    <section class="risk-section">
      <h2>风险与不确定性</h2>
      <ul class="risk-list">
        <li>README/metadata 只能判断表面可用性，不能证明项目真实可运行。</li>
        <li>新项目 star/fork 可能受推广影响，需要结合后续快照观察。</li>
        <li>computer-use/browser automation 项目往往涉及敏感权限，后续试跑必须隔离。</li>
        <li>外部来源采集来自 RSS/Atom/公开新闻源查询，只做候选事件筛选；事实必须以原始链接为准。</li>
        <li>首次运行时 3 日/7 日/30 日增长通常历史不足。</li>
      </ul>
    </section>

    <section>
      <h2>建议后续动作</h2>
      <ul class="risk-list">
        <li>将 <code>deep_read</code> 项目加入 watchlist，每日追踪。</li>
        <li>连续运行至少 4 天后启用 3 日 star 增长作为真实排名信号。</li>
        <li>对高影响外部事件建立 source trust 规则和人工复核流程。</li>
      </ul>
    </section>
  </main>
</body>
</html>
"""


def _repo_html_row(review: dict[str, Any]) -> str:
    repo = review["repo"]
    growth = review["score"]["scoring"]["growth"]["3d"]
    growth_text = f"+{growth['delta']} stars / 3d" if growth.get("status") == "ok" else "历史不足"
    return (
        "<tr>"
        f"<td>{_html_link(repo['url'], repo['full_name'])}</td>"
        f"<td>{review['score']['score']}</td>"
        f"<td>{_html_text(repo.get('language') or '-')}</td>"
        f"<td>{repo.get('stars') or 0}</td>"
        f"<td>{_html_text(growth_text)}</td>"
        f"<td>{_html_text(review['score']['recommendation'])}</td>"
        "</tr>"
    )


def _repo_html_card(review: dict[str, Any]) -> str:
    repo = review["repo"]
    score = review["score"]
    return f"""
<article class="item repo">
  <h3>{_html_link(repo['url'], repo['full_name'])}</h3>
  <div class="meta">{_html_text(repo.get('stars') or 0)} stars · {_html_text(repo.get('forks') or 0)} forks · license <span class="pill">{_html_text(repo.get('license_key') or 'unknown')}</span></div>
  <p>{_html_text(repo.get('description') or '无描述')}</p>
  <p><strong>分数：</strong>{score['score']}，<strong>建议：</strong><span class="pill good">{_html_text(score['recommendation'])}</span></p>
  <p><strong>README 质量：</strong>{_html_text(score['readme_quality'])}</p>
  <p><strong>可用性判断：</strong>{_html_text(score['usability_notes'])}</p>
  <p><strong>风险：</strong>{_html_text(score['risk_notes'])}</p>
</article>
"""


def _event_html_section(events: list[dict[str, Any]], domain: str, empty_text: str, *, limit: int = 5) -> str:
    selected = [event for event in events if event.get("domain") == domain]
    if not selected:
        return f'<p class="muted">{_html_text(empty_text)}</p>'
    return "\n".join(_event_html_card(event) for event in selected[:limit])


def _event_html_card(event: dict[str, Any]) -> str:
    facts = "".join(f"<li>{_html_text(fact)}</li>" for fact in (event.get("facts") or [])[:3])
    facts_html = f"<ul>{facts}</ul>" if facts else ""
    published = f"<p><strong>发布时间：</strong>{_html_text(event['published_at'])}</p>" if event.get("published_at") else ""
    summary = f"<p>{_html_text(event['summary'])}</p>" if event.get("summary") else ""
    return f"""
<article class="item event">
  <h3>{_html_link(event.get('url'), event.get('title') or '未命名事件')}</h3>
  <div class="meta">发布方：{_html_text(event.get('publisher') or 'unknown')} · 类型：{_html_text(event.get('source_type') or 'unknown')} · 匹配查询：{_html_text(event.get('query_name') or '-')}</div>
  {published}
  {summary}
  {facts_html}
  <p><strong>推断：</strong>{_html_text(event.get('inference') or '-')}</p>
</article>
"""


def render_markdown_as_html(markdown: str, *, title: str = "Markdown Report") -> str:
    blocks = markdown.splitlines()
    html_lines: list[str] = []
    in_ul = False
    in_table = False
    table_rows: list[list[str]] = []

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False

    def flush_table() -> None:
        nonlocal in_table, table_rows
        if not in_table:
            return
        html_lines.append("<table>")
        for index, row in enumerate(table_rows):
            tag = "th" if index == 0 else "td"
            if index == 1 and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in row):
                continue
            cells = "".join(f"<{tag}>{_inline_markdown(cell.strip())}</{tag}>" for cell in row)
            html_lines.append(f"<tr>{cells}</tr>")
        html_lines.append("</table>")
        in_table = False
        table_rows = []

    for raw in blocks:
        line = raw.rstrip()
        if line.startswith("|") and line.endswith("|"):
            close_ul()
            in_table = True
            table_rows.append([cell for cell in line.strip("|").split("|")])
            continue
        flush_table()
        if not line:
            close_ul()
            continue
        if line.startswith("### "):
            close_ul()
            html_lines.append(f"<h3>{_inline_markdown(line[4:])}</h3>")
        elif line.startswith("## "):
            close_ul()
            html_lines.append(f"<h2>{_inline_markdown(line[3:])}</h2>")
        elif line.startswith("# "):
            close_ul()
            html_lines.append(f"<h1>{_inline_markdown(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{_inline_markdown(line[2:])}</li>")
        elif line.startswith("  - "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"<li>{_inline_markdown(line[4:])}</li>")
        else:
            close_ul()
            html_lines.append(f"<p>{_inline_markdown(line)}</p>")
    flush_table()
    close_ul()
    return _html_reader_shell(title, "\n".join(html_lines))


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    return escaped


def _html_reader_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; background: #f5f7fb; color: #172033; font: 15px/1.68 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 28px 18px 46px; }}
    a {{ color: #0b63ce; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    h1 {{ font-size: 30px; line-height: 1.22; }}
    h2 {{ margin-top: 28px; border-top: 1px solid #d9e0ea; padding-top: 18px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d9e0ea; border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #d9e0ea; text-align: left; vertical-align: top; }}
    th {{ color: #667085; background: #eef2f7; font-size: 12px; }}
    code {{ background: #eef3f8; border: 1px solid #d9e0ea; border-radius: 5px; padding: 1px 4px; }}
    .toolbar {{ margin-bottom: 18px; }}
    .button {{ display: inline-block; border-radius: 8px; background: #0b63ce; color: white; padding: 8px 11px; font-weight: 700; }}
  </style>
</head>
<body><main><div class="toolbar"><a class="button" href="/results">返回结果</a></div>{body}</main></body>
</html>
"""


def write_report(payload: dict[str, Any], markdown_path: Path, audit_path: Path, html_path: Path | None = None) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    if html_path is not None:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(render_html(payload), encoding="utf-8")
    audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_report(markdown_path: Path, audit_path: Path, html_path: Path | None = None) -> None:
    if not markdown_path.exists() or markdown_path.stat().st_size == 0:
        raise RuntimeError(f"Markdown report missing or empty: {markdown_path}")
    if html_path is not None and (not html_path.exists() or html_path.stat().st_size == 0):
        raise RuntimeError(f"HTML report missing or empty: {html_path}")
    if not audit_path.exists() or audit_path.stat().st_size == 0:
        raise RuntimeError(f"Audit JSON missing or empty: {audit_path}")
    json.loads(audit_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    required = ["## 执行摘要", "## 今日高信号 GitHub 项目", "## 风险与不确定性"]
    missing = [section for section in required if section not in markdown]
    if missing:
        raise RuntimeError(f"Markdown report missing sections: {missing}")
    if html_path is not None:
        rendered = html_path.read_text(encoding="utf-8")
        if "<html" not in rendered or "执行摘要" not in rendered:
            raise RuntimeError(f"HTML report missing required content: {html_path}")


def report_payload(
    *,
    report_date: str,
    timezone: str,
    queries: list[dict[str, Any]],
    candidate_count: int,
    reviews: list[dict[str, Any]],
    deep_review_limit: int,
    artifacts: dict[str, str],
    external_events: list[dict[str, Any]] | None = None,
    external_source_queries: list[dict[str, Any]] | None = None,
    external_source_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "report_date": report_date,
        "timezone": timezone,
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "queries": queries,
        "candidate_count": candidate_count,
        "deep_review_limit": deep_review_limit,
        "reviews": reviews,
        "artifacts": artifacts,
        "external_events": external_events or [],
        "external_source_queries": external_source_queries or [],
        "external_source_errors": external_source_errors or [],
        "safety": {
            "cloned_repositories": False,
            "installed_dependencies": False,
            "executed_third_party_code": False,
        },
    }
