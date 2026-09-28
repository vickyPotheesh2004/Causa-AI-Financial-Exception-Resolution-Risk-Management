from __future__ import annotations

import os
from datetime import datetime, timezone

from pydantic import ValidationError

from ..config import load_local_env
from .providers import DeterministicFallbackProvider, GeminiFreeProvider, OllamaProvider, OpenRouterProvider
from .schemas import InvestigationFinding, InvestigationResult


def _provider():
    load_local_env()
    configured = os.environ.get("AI_PROVIDER", "fallback").casefold()
    candidate = OpenRouterProvider() if configured == "openrouter" else OllamaProvider() if configured == "ollama" else GeminiFreeProvider() if configured == "gemini" else None
    return candidate if candidate and candidate.available() else DeterministicFallbackProvider()


def investigate(context: dict) -> InvestigationResult:
    provider = _provider()
    fallback = isinstance(provider, DeterministicFallbackProvider)
    try:
        finding = InvestigationFinding.model_validate(provider.investigate(context))
        valid_ids = {str(item.get("id")) for item in context.get("evidence", [])}
        if not set(finding.evidence_ids).issubset(valid_ids):
            raise ValueError("Provider cited evidence outside the controlled context")
        status = "DETERMINISTIC_FALLBACK" if fallback else "AI_GENERATED"
        notice = "AI unavailable. Causa is using deterministic investigation rules." if fallback else "AI assistance is advisory. AI confidence does not confer authority."
    except (ValidationError, ValueError, KeyError, OSError, TimeoutError):
        provider = DeterministicFallbackProvider()
        finding = InvestigationFinding.model_validate(provider.investigate(context))
        status, notice = "AI_UNAVAILABLE", "AI provider output was unavailable or invalid. Causa is using deterministic investigation rules."
    return InvestigationResult(status=status, provider=provider.name, model=provider.model, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), finding=finding, notice=notice)
