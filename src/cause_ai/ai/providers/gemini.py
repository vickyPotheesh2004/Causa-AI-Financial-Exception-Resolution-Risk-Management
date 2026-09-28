from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from ..prompts.investigation import system_prompt


class GeminiFreeProvider:
    name = "gemini"
    def __init__(self) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY") or None
        self.model = os.environ.get("GEMINI_MODEL") or None

    def available(self) -> bool:
        return bool(self.api_key and self.model)

    def investigate(self, context: dict) -> dict:
        if not self.available():
            raise RuntimeError("Gemini free-tier configuration is absent")
        payload = {"system_instruction": {"parts": [{"text": system_prompt()}]}, "contents": [{"parts": [{"text": json.dumps(context, sort_keys=True)}]}], "generationConfig": {"responseMimeType": "application/json"}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        request = Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
        return json.loads(result["candidates"][0]["content"]["parts"][0]["text"])
