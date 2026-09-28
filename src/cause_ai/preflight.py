"""Fail-closed deployment preflight for a future company-owned environment."""

from __future__ import annotations

import json
import os
import sys
from typing import Mapping
from urllib.parse import urlparse


def _https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def assess_production_environment(env: Mapping[str, str] | None = None) -> dict[str, object]:
    """Return a redacted deployment assessment without printing secret values."""
    values = env or os.environ
    checks = {
        "production_environment_declared": values.get("CAUSE_AI_ENV", "").casefold() == "production",
        "postgresql_database_configured": values.get("DATABASE_URL", "").startswith(("postgresql://", "postgres://")),
        "oidc_issuer_configured": _https_url(values.get("OIDC_ISSUER", "")),
        "oidc_audience_configured": bool(values.get("OIDC_AUDIENCE", "").strip()),
        "session_signing_key_configured": len(values.get("SESSION_SIGNING_KEY", "")) >= 32,
        "https_allowed_origins_configured": bool(values.get("ALLOWED_ORIGINS", "").strip()) and all(_https_url(item.strip()) for item in values.get("ALLOWED_ORIGINS", "").split(",") if item.strip()),
        "observability_endpoint_configured": _https_url(values.get("OBSERVABILITY_ENDPOINT", "")),
        "object_storage_configured": bool(values.get("OBJECT_STORAGE_BUCKET", "").strip()),
        "durable_worker_queue_configured": _https_url(values.get("WORKER_QUEUE_URL", "")),
        "backup_plan_recorded": bool(values.get("BACKUP_PLAN_ID", "").strip()),
        "data_governance_approved": values.get("DATA_GOVERNANCE_APPROVED", "").casefold() == "true",
        "security_release_approved": values.get("SECURITY_RELEASE_APPROVED", "").casefold() == "true",
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {"ready": not blockers, "passed": [name for name, passed in checks.items() if passed],
            "blockers": blockers, "checks_passed": len(checks) - len(blockers), "checks_total": len(checks)}


def main() -> int:
    result = assess_production_environment()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
