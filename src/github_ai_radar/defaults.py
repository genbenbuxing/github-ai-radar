RADAR_TOML = """[radar]
timezone = "Asia/Shanghai"
report_time = "10:00"
report_style = "standard"
max_candidates_per_run = 100
deep_review_limit = 10
read_only = true

[paths]
data_dir = "data"
reports_dir = "reports/github-radar"
database = "data/radar.sqlite"

[domains.ai_applications]
enabled = true
keywords = [
  "ai agent",
  "agentic ai",
  "computer use",
  "browser automation",
  "image recognition",
  "vision language model",
  "ocr agent",
  "memory agent",
  "rag",
  "mcp",
  "workflow automation",
  "developer tools"
]

[domains.finance_high_tech]
enabled = true
keywords = [
  "AI chips",
  "AI cloud",
  "agentic AI enterprise",
  "AI capital expenditure",
  "semiconductor AI",
  "AI regulation finance",
  "AI fintech"
]

[domains.biopharma_ai]
enabled = true
keywords = [
  "AI drug discovery",
  "biology foundation model",
  "protein design",
  "genomics AI",
  "clinical trial AI",
  "pharma AI collaboration",
  "BioNeMo",
  "AI biopharma"
]

[filters]
exclude_archived = true
exclude_forks = true
minimum_stars_for_mature_search = 50
new_project_window_days = 14
active_pushed_window_days = 30

[watchlist]
deep_read_interval_days = 1
watch_interval_days = 3
trial_later_interval_days = 7
"""

QUERIES_TOML = """[[github_queries]]
name = "new_agentic_ai"
query = "agentic ai created:>=${date_minus_14} pushed:>=${date_minus_7} stars:>=5 archived:false fork:false"

[[github_queries]]
name = "ai_agent_topic"
query = "topic:ai-agent pushed:>=${date_minus_30} stars:>=100 archived:false fork:false"

[[github_queries]]
name = "mcp_agents"
query = "mcp agent pushed:>=${date_minus_30} stars:>=50 archived:false fork:false"

[[github_queries]]
name = "computer_use"
query = "computer use ai agent pushed:>=${date_minus_30} stars:>=10 archived:false fork:false"

[[github_queries]]
name = "vision_agents"
query = "vision language model ocr agent pushed:>=${date_minus_30} stars:>=20 archived:false fork:false"

[[github_queries]]
name = "memory_agents"
query = "memory agent rag pushed:>=${date_minus_30} stars:>=50 archived:false fork:false"

[[github_queries]]
name = "ai_drug_discovery"
query = "AI drug discovery pushed:>=${date_minus_120} stars:>=50 archived:false fork:false"

# Reserved for the next external-source collector. Current reports do not use
# source_queries; the dashboard shows them as planned fields to avoid implying
# that news, filings, announcements, or papers are being collected today.
[[source_queries]]
name = "finance_high_tech"
query = "AI high technology finance chips cloud earnings regulation latest official source"

[[source_queries]]
name = "biopharma_ai"
query = "AI drug discovery biopharma collaboration clinical trials foundation model official source"
"""

SCORING_TOML = """[weights]
domain_relevance = 20
practical_usability_evidence = 15
readme_documentation_clarity = 12
maintenance_activity = 12
community_signal = 10
three_day_star_growth = 10
license_friendliness = 8
novelty = 8
safety_compliance_control = 5

[penalties]
archived = 100
fork_or_mirror = 30
thin_readme = 15
unclear_license = 8
stale_repository = 15
trading_bot_noise = 20
marketing_only = 12
sensitive_permissions = 15
abnormal_star_fork_ratio = 10
keyword_stuffing = 10

[growth]
three_day_growth_min_history_days = 3
seven_day_growth_min_history_days = 7
thirty_day_growth_min_history_days = 30
"""

TOPICS_TOML = """# Current reports use github_terms immediately. source_terms are saved
# as planning fields for the next external-source collector.

[[topics]]
name = "ai_applications"
enabled = true
description = "AI applications, agents, local operation, memory, vision, RAG, MCP, workflow automation, and developer tooling."
github_terms = [
  "agentic ai",
  "ai agent",
  "computer use",
  "browser automation",
  "vision language model",
  "memory agent",
  "mcp",
  "rag",
  "workflow automation"
]
source_terms = [
  "agentic AI application",
  "AI agent platform",
  "computer use agent",
  "AI memory infrastructure"
]

[[topics]]
name = "finance_high_tech"
enabled = true
description = "International finance events tied to AI and high technology."
github_terms = [
  "ai fintech",
  "ai risk management",
  "ai market research",
  "financial agent"
]
source_terms = [
  "AI chips earnings",
  "AI cloud capital expenditure",
  "AI regulation capital markets",
  "semiconductor AI finance"
]

[[topics]]
name = "biopharma_ai"
enabled = true
description = "Biopharma and AI collaboration, drug discovery, clinical development, and biology foundation models."
github_terms = [
  "AI drug discovery",
  "biology foundation model",
  "protein design",
  "genomics AI",
  "clinical trial AI"
]
source_terms = [
  "AI drug discovery partnership",
  "biopharma AI collaboration",
  "biology foundation model",
  "clinical trial AI regulation"
]

[[topics]]
name = "custom"
enabled = false
description = "User-defined extra direction. Enable and edit as needed."
github_terms = [
  "example keyword"
]
source_terms = [
  "example external source query"
]
"""

LLM_TOML_EXAMPLE = """[llm]
enabled = false
provider = "openai_compatible"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"
api_key_env = "OPENAI_API_KEY"
timeout_seconds = 60

# Copy this file to config/llm.toml for personal use.
# Never commit config/llm.toml with real API keys.
"""

DEFAULT_FILES = {
    "radar.toml": RADAR_TOML,
    "queries.toml": QUERIES_TOML,
    "scoring.toml": SCORING_TOML,
    "topics.toml": TOPICS_TOML,
    "llm.toml.example": LLM_TOML_EXAMPLE,
}
