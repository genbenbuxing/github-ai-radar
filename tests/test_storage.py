from github_ai_radar.storage import initialize, table_counts


def test_initialize_creates_tables(tmp_path):
    database = tmp_path / "radar.sqlite"
    initialize(database)
    counts = table_counts(database)
    assert counts["repositories"] == 0
    assert counts["repo_snapshots"] == 0
    assert counts["runs"] == 0
