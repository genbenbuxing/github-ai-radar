from datetime import date

from github_ai_radar.source_collector import collect_external_sources, google_news_rss_url, parse_feed


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>NVIDIA announces AI cloud finance partnership</title>
      <link>https://nvidianews.nvidia.com/news/ai-cloud-finance</link>
      <source url="https://nvidianews.nvidia.com/">NVIDIA Newsroom</source>
      <pubDate>Fri, 22 May 2026 08:00:00 GMT</pubDate>
      <description>AI cloud capital expenditure and finance market update.</description>
    </item>
    <item>
      <title>Biopharma AI drug discovery clinical collaboration expands</title>
      <link>https://www.examplepharma.com/news/ai-drug-discovery</link>
      <source>Example Pharma</source>
      <pubDate>Thu, 21 May 2026 08:00:00 GMT</pubDate>
      <description>Protein design and clinical trial automation partnership.</description>
    </item>
  </channel>
</rss>
"""


def test_parse_feed_scores_and_classifies_source_items():
    items = parse_feed(
        RSS,
        query_name="finance_high_tech",
        query="AI finance chips cloud official",
        report_date=date(2026, 5, 22),
    )

    assert len(items) == 2
    assert items[0].title == "NVIDIA announces AI cloud finance partnership"
    assert items[0].domain == "ai_finance_high_tech"
    assert items[0].source_type == "company"
    assert items[0].score > 0
    assert items[0].facts
    assert "推断" not in items[0].inference


def test_collect_external_sources_uses_feed_urls_and_topic_terms():
    fetched_urls = []

    def fetcher(url: str) -> str:
        fetched_urls.append(url)
        return RSS

    events, raw = collect_external_sources(
        source_queries=[{"name": "direct_feed", "query": "https://example.com/feed.xml"}],
        topic_terms=[{"name": "biopharma", "query": "AI drug discovery partnership"}],
        report_date=date(2026, 5, 22),
        fetch_text=fetcher,
    )

    assert fetched_urls[0] == "https://example.com/feed.xml"
    assert fetched_urls[1] == google_news_rss_url(
        "AI drug discovery partnership official source OR announcement OR regulation OR partnership"
    )
    assert raw["errors"] == []
    assert raw["queries"][0]["items"]
    assert len(events) == 2
