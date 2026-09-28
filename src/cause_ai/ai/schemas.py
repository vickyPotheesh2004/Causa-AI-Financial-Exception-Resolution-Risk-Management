"""Strict, untrusted-provider output contract."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class InvestigationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    investigation_summary: str = Field(min_length=1, max_length=1200)
    finding_status: Literal["CONFIRMED", "PROBABLE", "UNKNOWN", "CONFLICTING"]
    possible_root_cause: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    unknowns: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=20)
    recommended_next_steps: list[str] = Field(default_factory=list, max_length=10)
    recommended_route: Literal["AUTO_REVIEW", "DEPARTMENT_ESCALATE", "FRAUD_ESCALATE"]
    reason: str = Field(min_length=1, max_length=800)


class InvestigationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["AI_GENERATED", "DETERMINISTIC_FALLBACK", "AI_UNAVAILABLE", "AI_OUTPUT_INVALID"]
    provider: str
    model: str | None = None
    generated_at: str
    finding: InvestigationFinding
    notice: str
