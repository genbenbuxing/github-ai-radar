from github_ai_radar.config import ensure_default_config, load_config, llm_status


def test_default_config_can_be_created(tmp_path):
    written = ensure_default_config(tmp_path)
    assert {path.name for path in written} >= {
        "radar.toml",
        "queries.toml",
        "scoring.toml",
        "topics.toml",
        "llm.toml.example",
    }
    config = load_config(tmp_path)
    assert config.github_queries
    assert config.topics
    status = llm_status(tmp_path)
    assert status["configured"] is False
    assert status["example_exists"] is True
