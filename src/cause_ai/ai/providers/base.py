from __future__ import annotations

from typing import Protocol


class AIProvider(Protocol):
    name: str
    model: str | None

    def available(self) -> bool: ...
    def investigate(self, context: dict) -> dict: ...
