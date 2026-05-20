from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from github_ai_radar.config import configured_secret


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key_env: str
    timeout_seconds: int = 60
    root: Path | None = None

    @property
    def api_key(self) -> str | None:
        if self.root is not None:
            return configured_secret(self.root, self.api_key_env)
        return os.environ.get(self.api_key_env)

    @classmethod
    def from_dict(cls, data: dict[str, Any], root: Path | None = None) -> "LLMConfig":
        return cls(
            enabled=bool(data.get("enabled", False)),
            provider=str(data.get("provider", "openai_compatible")),
            base_url=str(data.get("base_url", "https://api.openai.com/v1")).rstrip("/"),
            model=str(data.get("model", "gpt-4.1-mini")),
            api_key_env=str(data.get("api_key_env", "OPENAI_API_KEY")),
            timeout_seconds=int(data.get("timeout_seconds", 60)),
            root=root,
        )


def chat_completion(config: LLMConfig, messages: list[dict[str, str]]) -> str:
    if not config.enabled:
        raise RuntimeError("LLM is disabled in config/llm.toml")
    api_key = config.api_key
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable: {config.api_key_env}")
    if config.provider != "openai_compatible":
        raise RuntimeError(f"Unsupported LLM provider: {config.provider}")

    body = json.dumps({"model": config.model, "messages": messages}).encode("utf-8")
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed: {exc.code} {detail}") from exc
    return payload["choices"][0]["message"]["content"]
