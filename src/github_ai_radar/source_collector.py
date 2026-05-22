from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable


FetchText = Callable[[str], str]

TRUSTED_DOMAIN_KEYWORDS = {
    "openai.com": "company",
    "anthropic.com": "company",
    "microsoft.com": "company",
    "blogs.microsoft.com": "company",
    "nvidia.com": "company",
    "nvidianews.nvidia.com": "company",
    "fda.gov": "regulatory",
    "europa.eu": "regulatory",
    "sec.gov": "regulatory",
    "nih.gov": "research",
    "nature.com": "research",
    "science.org": "research",
    "nejm.org": "research",
    "cell.com": "research",
    "investor": "company",
}

DOMAIN_HINTS = {
    "biopharma": "ai_biopharma",
    "pharma": "ai_biopharma",
    "drug": "ai_biopharma",
    "clinical": "ai_biopharma",
    "genomic": "ai_biopharma",
    "protein": "ai_biopharma",
    "finance": "ai_finance_high_tech",
    "financial": "ai_finance_high_tech",
    "chips": "ai_finance_high_tech",
    "semiconductor": "ai_finance_high_tech",
    "cloud": "ai_finance_high_tech",
    "earnings": "ai_finance_high_tech",
    "regulation": "ai_finance_high_tech",
}


@dataclass(frozen=True)
class SourceItem:
    title: str
    url: str
    published_at: str | None
    publisher: str
    summary: str
    query_name: str
    query: str
    source_type: str
    domain: str
    score: int
    facts: list[str]
    inference: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "publisher": self.publisher,
            "summary": self.summary,
            "query_name": self.query_name,
            "query": self.query,
            "source_type": self.source_type,
            "domain": self.domain,
            "score": self.score,
            "facts": self.facts,
            "inference": self.inference,
        }


def default_fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GitHub-AI-Radar/0.5 (+https://github.com/genbenbuxing/github-ai-radar)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")


def google_news_rss_url(query: str) -> str:
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"https://news.google.com/rss/search?{params}"


def source_query_url(query: str) -> str:
    if query.startswith("http://") or query.startswith("https://"):
        return query
    return google_news_rss_url(query)


def collect_external_sources(
    *,
    source_queries: list[dict[str, str]],
    topic_terms: list[dict[str, str]],
    report_date: date,
    limit: int = 10,
    fetch_text: FetchText = default_fetch_text,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query_defs = _query_defs(source_queries, topic_terms)
    raw: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "report_date": report_date.isoformat(),
        "queries": [],
        "errors": [],
    }
    items: list[SourceItem] = []
    seen: set[str] = set()

    for query_def in query_defs:
        query = query_def["query"]
        url = source_query_url(query)
        raw_query = {"name": query_def["name"], "query": query, "url": url, "items": []}
        try:
            text = fetch_text(url)
            parsed = parse_feed(text, query_name=query_def["name"], query=query, report_date=report_date)
        except Exception as exc:
            raw["errors"].append({"name": query_def["name"], "query": query, "url": url, "error": str(exc)})
            raw["queries"].append(raw_query)
            continue

        for item in parsed:
            item_dict = item.as_dict()
            raw_query["items"].append(item_dict)
            key = _canonical_key(item.url, item.title)
            if key in seen:
                continue
            seen.add(key)
            if item.score > 0:
                items.append(item)
        raw["queries"].append(raw_query)

    items.sort(key=lambda item: (item.score, item.published_at or ""), reverse=True)
    return [item.as_dict() for item in items[:limit]], raw


def parse_feed(text: str, *, query_name: str, query: str, report_date: date) -> list[SourceItem]:
    root = ET.fromstring(text.encode("utf-8"))
    nodes = list(root.findall(".//item"))
    if not nodes:
        nodes = list(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
    return [
        item
        for node in nodes
        if (item := _parse_node(node, query_name=query_name, query=query, report_date=report_date)) is not None
    ]


def _parse_node(node: ET.Element, *, query_name: str, query: str, report_date: date) -> SourceItem | None:
    title = _clean_text(_child_text(node, "title"))
    url = _extract_link(node)
    if not title or not url:
        return None
    published = _published(node)
    summary = _clean_text(_child_text(node, "description") or _child_text(node, "summary") or _child_text(node, "content"))
    publisher = _publisher(node, url)
    domain = _domain_for(query_name, query, title, summary)
    source_type = _source_type(url, publisher)
    score = _score_item(title, summary, url, publisher, query, published, report_date)
    facts = _facts(title, publisher, published, query_name)
    inference = _inference(domain, title)
    return SourceItem(
        title=title,
        url=url,
        published_at=published.isoformat() if published else None,
        publisher=publisher,
        summary=summary[:600],
        query_name=query_name,
        query=query,
        source_type=source_type,
        domain=domain,
        score=score,
        facts=facts,
        inference=inference,
    )


def _query_defs(source_queries: list[dict[str, str]], topic_terms: list[dict[str, str]]) -> list[dict[str, str]]:
    defs: list[dict[str, str]] = []
    for item in source_queries:
        name = str(item.get("name") or "source").strip()
        query = str(item.get("query") or "").strip()
        if query:
            defs.append({"name": name, "query": query})
    for item in topic_terms:
        name = str(item.get("name") or "topic_source").strip()
        query = str(item.get("query") or "").strip()
        if query:
            defs.append({"name": name, "query": f"{query} official source OR announcement OR regulation OR partnership"})
    return defs


def _child_text(node: ET.Element, name: str) -> str:
    candidates = [name, f"{{http://www.w3.org/2005/Atom}}{name}"]
    if ":" in name:
        suffix = name.split(":", 1)[1]
        candidates.extend(
            [
                f"{{http://purl.org/dc/elements/1.1/}}{suffix}",
                f"{{http://purl.org/dc/terms/}}{suffix}",
            ]
        )
    for candidate in candidates:
        found = node.find(candidate)
        if found is not None:
            return found.text or ""
    return ""


def _extract_link(node: ET.Element) -> str:
    link = _child_text(node, "link")
    if link:
        return link.strip()
    atom_link = node.find("{http://www.w3.org/2005/Atom}link")
    if atom_link is not None:
        return (atom_link.attrib.get("href") or "").strip()
    return ""


def _publisher(node: ET.Element, url: str) -> str:
    source = node.find("source")
    if source is not None and source.text:
        return _clean_text(source.text)
    return urllib.parse.urlparse(url).netloc.replace("www.", "") or "unknown"


def _published(node: ET.Element) -> datetime | None:
    raw = (
        _child_text(node, "pubDate")
        or _child_text(node, "published")
        or _child_text(node, "updated")
        or _child_text(node, "dc:date")
    )
    if not raw:
        return None
    try:
        value = parsedate_to_datetime(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _source_type(url: str, publisher: str) -> str:
    haystack = f"{url} {publisher}".lower()
    for key, value in TRUSTED_DOMAIN_KEYWORDS.items():
        if key in haystack:
            return value
    return "news"


def _score_item(
    title: str,
    summary: str,
    url: str,
    publisher: str,
    query: str,
    published: datetime | None,
    report_date: date,
) -> int:
    haystack = f"{title} {summary} {url} {publisher}".lower()
    query_words = {word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", query)}
    score = sum(2 for word in query_words if word in haystack)
    score += 10 if _source_type(url, publisher) in {"company", "regulatory", "research"} else 0
    if any(word in haystack for word in ("ai", "agent", "mcp", "drug", "clinical", "finance", "chip", "cloud", "regulation", "partnership")):
        score += 8
    if published:
        age_days = abs((report_date - published.date()).days)
        if age_days <= 7:
            score += 8
        elif age_days <= 30:
            score += 4
    return score


def _domain_for(query_name: str, query: str, title: str, summary: str) -> str:
    haystack = f"{query_name} {query} {title} {summary}".lower()
    for hint, domain in DOMAIN_HINTS.items():
        if hint in haystack:
            return domain
    return "ai_applications"


def _facts(title: str, publisher: str, published: datetime | None, query_name: str) -> list[str]:
    date_text = published.date().isoformat() if published else "日期未在 feed 中提供"
    return [
        f"{publisher} 发布或转载：{title}",
        f"发布时间：{date_text}；匹配来源查询：{query_name}",
    ]


def _inference(domain: str, title: str) -> str:
    if domain == "ai_biopharma":
        return "该事件可能影响 AI 药研、临床试验自动化、实验数据闭环或生物基础模型方向，建议结合官方材料继续跟踪。"
    if domain == "ai_finance_high_tech":
        return "该事件可能影响 AI 公司、芯片/云基础设施、资本市场、金融科技或监管环境，建议纳入后续趋势观察。"
    return "该事件可能影响 AI agent、工具调用、RAG、MCP、开发者工具或本地自动化生态，建议结合项目侧信号交叉验证。"


def _canonical_key(url: str, title: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return (parsed.netloc.lower(), parsed.path.rstrip("/").lower(), title.lower())
