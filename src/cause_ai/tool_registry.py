"""Declared, non-financial tools available to Cause AI workflows.

The registry is deliberately declarative: every operation has an owner role,
data scope, rate limit, and audit requirement.  It contains no tool capable of
moving money, changing a payment, or changing a settlement.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


TOOL_REGISTRY: tuple[dict[str, Any], ...] = (
    {"id": "detect_exceptions", "operation": "Create exception findings from normalized records",
     "roles": ["analyst", "admin"], "data_scope": "tenant-scoped normalized financial events",
     "risk_level": "MEDIUM", "rate_limit_per_minute": 30, "audit_required": True,
     "execution_mode": "read-and-create-case"},
    {"id": "evaluate_case", "operation": "Apply the active policy and deterministic risk rules",
     "roles": ["analyst", "admin"], "data_scope": "tenant-scoped case and evidence",
     "risk_level": "MEDIUM", "rate_limit_per_minute": 60, "audit_required": True,
     "execution_mode": "decision-and-route"},
    {"id": "manage_policy_lifecycle", "operation": "Propose, independently review, and activate a policy version",
     "roles": ["admin"], "data_scope": "tenant-scoped policy metadata",
     "risk_level": "HIGH", "rate_limit_per_minute": 10, "audit_required": True,
     "execution_mode": "human-authorized-control"},
    {"id": "razorpay_read_only_import", "operation": "Import normalized payment records from configured Razorpay mode",
     "roles": ["admin"], "data_scope": "configured tenant payment metadata only",
     "risk_level": "HIGH", "rate_limit_per_minute": 10, "audit_required": True,
     "execution_mode": "read-only-import"},
    {"id": "verify_resolution", "operation": "Verify a resolved department ticket against linked evidence",
     "roles": ["analyst", "admin"], "data_scope": "tenant-scoped ticket and evidence",
     "risk_level": "MEDIUM", "rate_limit_per_minute": 60, "audit_required": True,
     "execution_mode": "workflow-state-change"},
)


def controlled_tool_registry() -> list[dict[str, Any]]:
    """Return a copy so API consumers cannot mutate the declared registry."""
    return deepcopy(list(TOOL_REGISTRY))
