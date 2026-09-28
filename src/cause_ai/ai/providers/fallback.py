"""Transparent deterministic investigation assistance; never represents itself as AI."""


class DeterministicFallbackProvider:
    name = "deterministic-fallback"
    model = None

    def available(self) -> bool:
        return True

    def investigate(self, context: dict) -> dict:
        evidence = context.get("evidence", [])
        evidence_ids = [str(item.get("id")) for item in evidence if item.get("id")]
        conflicting = [item for item in evidence if item.get("status") == "CONFLICTING"]
        unverified = [item for item in evidence if item.get("status") != "VERIFIED"]
        decision = context.get("decision", {})
        route = "FRAUD_ESCALATE" if decision.get("outcome") == "FRAUD_ESCALATE" else "DEPARTMENT_ESCALATE" if decision.get("outcome", "").endswith("ESCALATE") else "AUTO_REVIEW"
        if conflicting:
            status, cause = "CONFLICTING", "Authoritative source records conflict; a causal conclusion is not supported."
        elif unverified or not evidence:
            status, cause = "UNKNOWN", "Available source evidence is insufficiently verified to establish a root cause."
        else:
            status, cause = "PROBABLE", "The deterministic workflow identified a discrepancy from the cited source records."
        return {"investigation_summary": "Deterministic investigation rules reviewed the case evidence and decision context.", "finding_status": status,
                "possible_root_cause": cause, "evidence_ids": evidence_ids, "unknowns": ["Independent human verification is required before a consequential action."] if status != "PROBABLE" else [],
                "conflicts": ["One or more cited records conflict."] if conflicting else [],
                "recommended_next_steps": ["Review cited evidence and record a verified resolution."], "recommended_route": route,
                "reason": "This is a deterministic fallback finding, not LLM-generated analysis."}
