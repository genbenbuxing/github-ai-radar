from __future__ import annotations

import json
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


def render_markdown(payload: dict[str, Any]) -> str:
    reviews = sorted(payload["reviews"], key=lambda item: item["score"]["score"], reverse=True)
    top = reviews[: payload.get("deep_review_limit", 10)]
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
            "本版本已经预留外部事件表和报告结构；自动新闻/公告采集将在下一阶段接入。当前报告只生成 GitHub 项目雷达，不臆造外部事件。",
            "",
            "## AI / 生物制药协作观察",
            "",
            "本版本已经预留 biopharma 事件表和报告结构；自动来源采集将在下一阶段接入。GitHub 侧已覆盖 AI drug discovery 相关仓库查询。",
            "",
            "## 风险与不确定性",
            "",
            "- README/metadata 只能判断表面可用性，不能证明项目真实可运行。",
            "- 新项目 star/fork 可能受推广影响，需要结合后续快照观察。",
            "- computer-use/browser automation 项目往往涉及敏感权限，后续试跑必须隔离。",
            "- 首次运行时 3 日/7 日/30 日增长通常历史不足。",
            "",
            "## 建议后续动作",
            "",
            "- 将 `deep_read` 项目加入 watchlist，每日追踪。",
            "- 连续运行至少 4 天后启用 3 日 star 增长作为真实排名信号。",
            "- 后续接入官方公告/监管文件/权威媒体源，补齐金融与 biopharma 事件采集。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(payload: dict[str, Any], markdown_path: Path, audit_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_report(markdown_path: Path, audit_path: Path) -> None:
    if not markdown_path.exists() or markdown_path.stat().st_size == 0:
        raise RuntimeError(f"Markdown report missing or empty: {markdown_path}")
    if not audit_path.exists() or audit_path.stat().st_size == 0:
        raise RuntimeError(f"Audit JSON missing or empty: {audit_path}")
    json.loads(audit_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    required = ["## 执行摘要", "## 今日高信号 GitHub 项目", "## 风险与不确定性"]
    missing = [section for section in required if section not in markdown]
    if missing:
        raise RuntimeError(f"Markdown report missing sections: {missing}")


def report_payload(
    *,
    report_date: str,
    timezone: str,
    queries: list[dict[str, Any]],
    candidate_count: int,
    reviews: list[dict[str, Any]],
    deep_review_limit: int,
    artifacts: dict[str, str],
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
        "external_events": [],
        "safety": {
            "cloned_repositories": False,
            "installed_dependencies": False,
            "executed_third_party_code": False,
        },
    }
