from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from .base import AIProvider
from ..prompts.investigation import system_prompt


class OllamaProvider:
    name = "ollama"
    def __init__(self) -> None:
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL") or None

    def available(self) -> bool:
        return bool(self.model)

    def investigate(self, context: dict) -> dict:
        if not self.model:
            raise RuntimeError("OLLAMA_MODEL is not configured")
        body = json.dumps({"model": self.model, "stream": False, "format": "json", "messages": [{"role": "system", "content": system_prompt()}, {"role": "user", "content": json.dumps(context, sort_keys=True)}]}).encode()
        request = Request(f"{self.base_url}/api/chat", body, {"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
        return json.loads(result["message"]["content"])
