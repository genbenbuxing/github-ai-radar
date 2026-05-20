from github_ai_radar.scheduler import build_launchd_plist


def test_launchd_plist_contains_radar_command(tmp_path):
    plist = build_launchd_plist(tmp_path, hour=10, minute=0, timezone="Asia/Shanghai")
    assert plist["Label"] == "com.github-ai-radar.daily"
    assert "github-ai-radar" in plist["ProgramArguments"][0]
    assert "--root" in plist["ProgramArguments"]
    assert str(tmp_path) in plist["ProgramArguments"]
