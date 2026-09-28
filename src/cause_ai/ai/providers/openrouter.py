"""OpenRouter adapter. The API key remains server-side in environment variables."""

from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from ..prompts.investigation import system_prompt


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENROUTER_API_KEY") or None
        self.model = os.environ.get("OPENROUTER_MODEL") or None
        self.base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")

    def available(self) -> bool:
        return bool(self.api_key and self.model)

    def investigate(self, context: dict) -> dict:
        if not self.available():
            raise RuntimeError("OpenRouter configuration is absent")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": json.dumps(context, sort_keys=True)},
            ],
            "temperature": 0,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            json.dumps(payload).encode(),
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
        return json.loads(result["choices"][0]["message"]["content"])
