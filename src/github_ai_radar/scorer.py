from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RepoScore:
    score: int
    recommendation: str
    scoring: dict[str, Any]
    readme_quality: str
    usability_notes: str
    risk_notes: str


DOMAIN_TERMS = [
    "agent",
    "agentic",
    "computer use",
    "browser",
    "automation",
    "vision",
    "image",
    "ocr",
    "memory",
    "rag",
    "mcp",
    "workflow",
    "drug discovery",
    "biopharma",
    "clinical",
    "genomics",
]

NOISE_TERMS = [
    "trading bot",
    "forex",
    "binance",
    "gate.io",
    "crypto bot",
]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _bounded(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _readme_quality(readme: str) -> tuple[str, int]:
    lower = readme.lower()
    score = 0
    if len(readme) > 2000:
        score += 4
    elif len(readme) > 800:
        score += 2
    if "install" in lower or "quick start" in lower or "quickstart" in lower:
        score += 3
    if "usage" in lower or "example" in lower:
        score += 2
    if "license" in lower:
        score += 1
    if score >= 8:
        return "strong", score
    if score >= 5:
        return "adequate", score
    if score >= 2:
        return "thin", score
    return "missing_or_very_thin", score


def score_repository(
    repo: dict[str, Any],
    readme: str,
    growth: dict[str, Any],
    report_date: date,
    weights: dict[str, int],
    penalties: dict[str, int],
) -> RepoScore:
    text = " ".join(
        str(part or "")
        for part in [
            repo.get("full_name"),
            repo.get("nameWithOwner"),
            repo.get("description"),
            repo.get("language"),
            " ".join(repo.get("topics") or []),
            readme[:2000],
        ]
    ).lower()
    stars = int(repo.get("stars") or repo.get("stargazerCount") or 0)
    forks = int(repo.get("forks") or repo.get("forkCount") or 0)
    pushed_at = _parse_dt(repo.get("pushed_at") or repo.get("pushedAt"))
    created_at = _parse_dt(repo.get("created_at") or repo.get("createdAt"))
    license_key = repo.get("license_key") or repo.get("license")

    domain_hits = sum(1 for term in DOMAIN_TERMS if term in text)
    domain_score = _bounded(domain_hits * 4, 0, weights.get("domain_relevance", 20))

    readme_label, readme_raw = _readme_quality(readme)
    readme_score = _bounded(readme_raw + 3, 0, weights.get("readme_documentation_clarity", 12))

    practical_score = 0
    practical_terms = ["quickstart", "quick start", "install", "usage", "example", "docs", "docker", "pip install", "npm"]
    practical_score += min(12, sum(2 for term in practical_terms if term in text))
    if repo.get("homepage_url") or repo.get("homepageUrl"):
        practical_score += 2
    practical_score = _bounded(practical_score, 0, weights.get("practical_usability_evidence", 15))

    maintenance_score = 0
    if pushed_at:
        age_days = (datetime.now(timezone.utc) - pushed_at).days
        if age_days <= 7:
            maintenance_score = 12
        elif age_days <= 30:
            maintenance_score = 9
        elif age_days <= 90:
            maintenance_score = 5
        else:
            maintenance_score = 1
    maintenance_score = _bounded(maintenance_score, 0, weights.get("maintenance_activity", 12))

    community_score = 0
    if stars >= 10000:
        community_score = 10
    elif stars >= 1000:
        community_score = 8
    elif stars >= 100:
        community_score = 5
    elif stars >= 10:
        community_score = 2
    community_score = _bounded(community_score, 0, weights.get("community_signal", 10))

    growth_score = 0
    growth_detail = growth.get("3d", {})
    if growth_detail.get("status") == "ok":
        delta = int(growth_detail.get("delta") or 0)
        growth_score = _bounded(delta // 10, 0, weights.get("three_day_star_growth", 10))

    license_score = weights.get("license_friendliness", 8) if license_key in {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause"} else 2

    novelty_score = 0
    if created_at:
        created_days = (datetime.now(timezone.utc) - created_at).days
        if created_days <= 30:
            novelty_score = 8
        elif created_days <= 180:
            novelty_score = 5
        else:
            novelty_score = 2

    safety_score = weights.get("safety_compliance_control", 5)
    risk_notes: list[str] = []
    penalty_total = 0
    if repo.get("is_archived") or repo.get("isArchived"):
        penalty_total += penalties.get("archived", 100)
        risk_notes.append("archived repository")
    if repo.get("is_fork") or repo.get("isFork"):
        penalty_total += penalties.get("fork_or_mirror", 30)
        risk_notes.append("fork or mirror")
    if readme_label in {"thin", "missing_or_very_thin"}:
        penalty_total += penalties.get("thin_readme", 15)
        risk_notes.append("thin README")
    if not license_key:
        penalty_total += penalties.get("unclear_license", 8)
        risk_notes.append("unclear license")
    if any(term in text for term in NOISE_TERMS):
        penalty_total += penalties.get("trading_bot_noise", 20)
        risk_notes.append("trading-bot/crypto noise")
    if forks > stars and stars > 0:
        penalty_total += penalties.get("abnormal_star_fork_ratio", 10)
        risk_notes.append("fork count exceeds stars")
    if any(term in text for term in ["cookie", "browser session", "skip_permissions", "desktop control"]):
        penalty_total += penalties.get("sensitive_permissions", 15)
        risk_notes.append("requires sensitive browser or desktop permissions")
        safety_score = max(0, safety_score - 3)

    raw_score = (
        domain_score
        + practical_score
        + readme_score
        + maintenance_score
        + community_score
        + growth_score
        + license_score
        + novelty_score
        + safety_score
        - penalty_total
    )
    score = _bounded(raw_score, 0, 100)
    if score >= 80:
        recommendation = "deep_read"
    elif score >= 65:
        recommendation = "watch"
    elif score >= 45:
        recommendation = "observe"
    else:
        recommendation = "ignore"

    scoring = {
        "domain_relevance": domain_score,
        "practical_usability_evidence": practical_score,
        "readme_documentation_clarity": readme_score,
        "maintenance_activity": maintenance_score,
        "community_signal": community_score,
        "three_day_star_growth": growth_score,
        "license_friendliness": license_score,
        "novelty": novelty_score,
        "safety_compliance_control": safety_score,
        "penalties": penalty_total,
        "growth": growth,
        "report_date": report_date.isoformat(),
    }
    usability_notes = "README suggests usable quickstart/examples." if practical_score >= 8 else "Usability evidence is limited in README/metadata."
    return RepoScore(
        score=score,
        recommendation=recommendation,
        scoring=scoring,
        readme_quality=readme_label,
        usability_notes=usability_notes,
        risk_notes="; ".join(risk_notes) if risk_notes else "No major read-only risk signal found.",
    )
