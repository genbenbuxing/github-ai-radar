from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


class GitHubClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubSearchResult:
    query_name: str
    query: str
    repositories: list[dict[str, Any]]


class GitHubClient:
    def __init__(self, gh_binary: str = "gh") -> None:
        self.gh_binary = gh_binary

    def _run_json(self, args: list[str]) -> Any:
        completed = subprocess.run(
            [self.gh_binary, *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise GitHubClientError(completed.stderr.strip() or completed.stdout.strip())
        if not completed.stdout.strip():
            return None
        return json.loads(completed.stdout)

    def auth_status(self) -> bool:
        completed = subprocess.run(
            [self.gh_binary, "auth", "status"],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.returncode == 0

    def search_repositories(self, query_name: str, query: str, limit: int) -> GitHubSearchResult:
        fields = [
            "fullName",
            "description",
            "stargazersCount",
            "forksCount",
            "language",
            "updatedAt",
            "createdAt",
            "url",
        ]
        payload = self._run_json(
            [
                "search",
                "repos",
                query,
                "--limit",
                str(limit),
                "--json",
                ",".join(fields),
            ]
        )
        return GitHubSearchResult(query_name=query_name, query=query, repositories=payload or [])

    def repository_metadata(self, full_name: str) -> dict[str, Any]:
        fields = [
            "nameWithOwner",
            "description",
            "stargazerCount",
            "forkCount",
            "createdAt",
            "updatedAt",
            "pushedAt",
            "primaryLanguage",
            "licenseInfo",
            "repositoryTopics",
            "isArchived",
            "isFork",
            "url",
            "homepageUrl",
        ]
        return self._run_json(["repo", "view", full_name, "--json", ",".join(fields)])

    def readme_head(self, full_name: str, max_chars: int = 12000) -> str:
        completed = subprocess.run(
            [
                self.gh_binary,
                "api",
                f"repos/{full_name}/readme",
                "-H",
                "Accept: application/vnd.github.raw",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return ""
        return completed.stdout[:max_chars]
