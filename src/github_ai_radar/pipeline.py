from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from github_ai_radar.config import load_config, render_query
from github_ai_radar.github_client import GitHubClient
from github_ai_radar.paths import RadarPaths
from github_ai_radar.reporter import report_payload, verify_report, write_report
from github_ai_radar.scorer import score_repository
from github_ai_radar.storage import (
    add_run_artifact,
    complete_run,
    compute_growth,
    create_run,
    initialize,
    record_review,
    upsert_repository,
    upsert_snapshot,
)


STAGES = [
    "init",
    "github_search",
    "github_readme_review",
    "scoring",
    "markdown_render",
    "audit_json_render",
    "final_verify",
    "completed",
]


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _normalize_search_repo(repo: dict) -> dict:
    return {
        "full_name": repo["fullName"],
        "url": repo["url"],
        "description": repo.get("description") or "",
        "language": repo.get("language") or "",
        "license_key": None,
        "created_at": repo.get("createdAt"),
        "updated_at": repo.get("updatedAt"),
        "pushed_at": repo.get("updatedAt"),
        "stars": repo.get("stargazersCount") or 0,
        "forks": repo.get("forksCount") or 0,
        "open_issues": None,
        "topics": [],
        "is_archived": False,
        "is_fork": False,
        "homepage_url": "",
    }


def _merge_metadata(repo: dict, metadata: dict) -> dict:
    topics = [item["name"] for item in metadata.get("repositoryTopics") or []]
    language = metadata.get("primaryLanguage") or {}
    license_info = metadata.get("licenseInfo") or {}
    merged = dict(repo)
    merged.update(
        {
            "full_name": metadata.get("nameWithOwner") or repo["full_name"],
            "url": metadata.get("url") or repo["url"],
            "description": metadata.get("description") or repo.get("description") or "",
            "language": language.get("name") or repo.get("language") or "",
            "license_key": license_info.get("key"),
            "created_at": metadata.get("createdAt") or repo.get("created_at"),
            "updated_at": metadata.get("updatedAt") or repo.get("updated_at"),
            "pushed_at": metadata.get("pushedAt") or repo.get("pushed_at"),
            "stars": metadata.get("stargazerCount") or repo.get("stars") or 0,
            "forks": metadata.get("forkCount") or repo.get("forks") or 0,
            "topics": topics,
            "is_archived": bool(metadata.get("isArchived")),
            "is_fork": bool(metadata.get("isFork")),
            "homepage_url": metadata.get("homepageUrl") or "",
        }
    )
    return merged


def run_once(
    root: Path,
    *,
    timezone: str = "Asia/Shanghai",
    max_candidates: int | None = None,
    deep_review_limit: int | None = None,
    trigger_type: str = "manual",
) -> dict:
    paths = RadarPaths.from_root(root)
    paths.ensure()
    initialize(paths.database)
    app_config = load_config(root)
    tz = ZoneInfo(timezone)
    report_day = datetime.now(tz).date()
    report_date = report_day.isoformat()
    state_path = paths.state_dir / f"{report_date}.state.json"
    markdown_path = paths.reports_dir / f"{report_date}.md"
    audit_path = paths.reports_dir / f"{report_date}.audit.json"
    raw_github_path = paths.raw_dir / "github" / f"{report_date}.json"

    state = {
        "report_date": report_date,
        "status": "running",
        "stages": [],
        "last_successful_stage": None,
        "errors": [],
    }
    _write_state(state_path, state)

    run_id = create_run(paths.database, report_date, trigger_type, str(state_path))
    client = GitHubClient()
    if not client.auth_status():
        raise RuntimeError("GitHub CLI is not authenticated. Run: gh auth login")

    limit_total = max_candidates or int(app_config.radar.get("max_candidates_per_run", 100))
    review_limit = deep_review_limit or int(app_config.radar.get("deep_review_limit", 10))
    query_limit = max(1, min(20, limit_total // max(1, len(app_config.github_queries)) + 1))

    state["stages"].append({"name": "init", "status": "completed", "completed_at": datetime.utcnow().isoformat() + "Z"})
    state["last_successful_stage"] = "init"
    _write_state(state_path, state)

    raw_results = []
    candidates: dict[str, dict] = {}
    rendered_queries = []
    query_defs = list(app_config.github_queries)
    for topic in app_config.topics:
        if not topic.get("enabled"):
            continue
        for index, term in enumerate(topic.get("github_terms") or []):
            query_defs.append(
                {
                    "name": f"topic_{topic.get('name', 'custom')}_{index + 1}",
                    "query": f"{term} pushed:>=${{date_minus_30}} stars:>=10 archived:false fork:false",
                }
            )

    for query_def in query_defs:
        query = render_query(query_def["query"], report_day)
        rendered_queries.append({"name": query_def["name"], "query": query})
        result = client.search_repositories(query_def["name"], query, query_limit)
        raw_results.append({"name": result.query_name, "query": result.query, "repositories": result.repositories})
        for item in result.repositories:
            normalized = _normalize_search_repo(item)
            candidates.setdefault(normalized["full_name"], normalized)
            if len(candidates) >= limit_total:
                break
        if len(candidates) >= limit_total:
            break
    raw_github_path.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    add_run_artifact(paths.database, run_id, "raw_github", str(raw_github_path))
    state["stages"].append(
        {
            "name": "github_search",
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "candidate_count": len(candidates),
            "raw_path": str(raw_github_path),
        }
    )
    state["last_successful_stage"] = "github_search"
    _write_state(state_path, state)

    for repo in candidates.values():
        repo_id = upsert_repository(paths.database, repo, report_date)
        upsert_snapshot(paths.database, repo_id, report_date, repo, entered_candidate_pool=True)

    ranked_for_review = sorted(candidates.values(), key=lambda item: int(item.get("stars") or 0), reverse=True)[:review_limit]
    reviews = []
    for repo in ranked_for_review:
        try:
            metadata = client.repository_metadata(repo["full_name"])
            repo = _merge_metadata(repo, metadata)
        except Exception as exc:  # keep daily run alive when one repo fails
            state["errors"].append({"repo": repo["full_name"], "stage": "metadata", "error": str(exc)})
        readme = client.readme_head(repo["full_name"])
        repo_id = upsert_repository(paths.database, repo, report_date)
        upsert_snapshot(paths.database, repo_id, report_date, repo, entered_candidate_pool=True)
        growth = compute_growth(paths.database, repo_id, report_date)
        score = score_repository(repo, readme, growth, report_day, app_config.weights, app_config.penalties)
        record_review(paths.database, repo_id, run_id, score)
        reviews.append(
            {
                "repo": repo,
                "readme_excerpt": readme[:1000],
                "score": {
                    "score": score.score,
                    "recommendation": score.recommendation,
                    "scoring": score.scoring,
                    "readme_quality": score.readme_quality,
                    "usability_notes": score.usability_notes,
                    "risk_notes": score.risk_notes,
                },
            }
        )
    state["stages"].append(
        {
            "name": "github_readme_review",
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "review_count": len(reviews),
        }
    )
    state["last_successful_stage"] = "github_readme_review"
    state["stages"].append({"name": "scoring", "status": "completed", "completed_at": datetime.utcnow().isoformat() + "Z"})
    state["last_successful_stage"] = "scoring"
    _write_state(state_path, state)

    payload = report_payload(
        report_date=report_date,
        timezone=timezone,
        queries=rendered_queries,
        candidate_count=len(candidates),
        reviews=reviews,
        deep_review_limit=review_limit,
        artifacts={
            "markdown": str(markdown_path),
            "audit_json": str(audit_path),
            "state": str(state_path),
            "raw_github": str(raw_github_path),
        },
    )
    write_report(payload, markdown_path, audit_path)
    add_run_artifact(paths.database, run_id, "markdown", str(markdown_path))
    add_run_artifact(paths.database, run_id, "audit_json", str(audit_path))
    state["stages"].append({"name": "markdown_render", "status": "completed", "completed_at": datetime.utcnow().isoformat() + "Z", "path": str(markdown_path)})
    state["stages"].append({"name": "audit_json_render", "status": "completed", "completed_at": datetime.utcnow().isoformat() + "Z", "path": str(audit_path)})
    state["last_successful_stage"] = "audit_json_render"
    _write_state(state_path, state)

    verify_report(markdown_path, audit_path)
    state["stages"].append({"name": "final_verify", "status": "completed", "completed_at": datetime.utcnow().isoformat() + "Z"})
    state["stages"].append({"name": "completed", "status": "completed", "completed_at": datetime.utcnow().isoformat() + "Z"})
    state["last_successful_stage"] = "completed"
    state["status"] = "completed"
    _write_state(state_path, state)
    complete_run(paths.database, run_id, "completed")
    return {
        "report_date": report_date,
        "candidate_count": len(candidates),
        "review_count": len(reviews),
        "markdown": str(markdown_path),
        "audit_json": str(audit_path),
        "state": str(state_path),
    }
