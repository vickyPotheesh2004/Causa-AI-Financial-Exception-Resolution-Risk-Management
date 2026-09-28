"""Use cases for cases, decisions, tickets, verification, and audit."""

from __future__ import annotations

import json
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import append_audit, connect, now_iso, row_case, row_ticket, verify_password
from .domain import decide, detect_exceptions, money, risk_assessment, validate_transition
from .tool_registry import controlled_tool_registry
from .ai import investigate as ai_investigate


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def authenticate(username: str, password: str) -> dict[str, str] | None:
    conn = connect()
    try:
        row = conn.execute("SELECT username,role,salt,password_hash,tenant_id FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
        if row is None or not row["tenant_id"] or not verify_password(password, row["salt"], row["password_hash"]):
            return None
        return {"username": row["username"], "role": row["role"], "tenant_id": row["tenant_id"], "session": secrets.token_urlsafe(32)}
    finally:
        conn.close()


def _policy_for(conn: sqlite3.Connection, policy_id: str, tenant_id: str) -> dict[str, Any]:
    """Resolve the tenant's active reviewed policy, then the demo baseline."""
    row = conn.execute("SELECT data_json FROM policy_proposals WHERE tenant_id=? AND policy_id=? AND state='ACTIVE' ORDER BY activated_at DESC LIMIT 1", (tenant_id, policy_id)).fetchone()
    if row is None:
        row = conn.execute("SELECT data_json FROM policies WHERE id=?", (policy_id,)).fetchone()
    return json.loads(row[0]) if row else {"id": policy_id, "status": "UNKNOWN", "source": "Unavailable"}


def _decorate_case(case: dict[str, Any], conn: sqlite3.Connection, tenant_id: str = "DEMO-MERCHANT-01") -> dict[str, Any]:
    case = dict(case)
    case["risk"] = risk_assessment(case)
    policy_id = "DEMO-FEE-003" if case["type"] == "FEE_DISCREPANCY" else "DEMO-STANDARD-001"
    case["policy"] = _policy_for(conn, policy_id, tenant_id)
    return case


def _audit(conn: sqlite3.Connection, actor: dict[str, str], action: str, object_type: str,
           object_id: str, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return append_audit(conn, actor["username"], actor["role"], action, object_type,
                        object_id, reason, details, tenant_id=actor["tenant_id"])


def _persist_financial_events(conn: sqlite3.Connection, records: list[dict[str, Any]], tenant_id: str,
                              timestamp: str, source_system: str) -> tuple[dict[str, str], int]:
    """Store normalized input immutably before deriving a case from it.

    Input remains unverified until an authorized connector/evidence workflow
    establishes authority. The immutable record prevents a source record ID
    from being silently overwritten by a later import.
    """
    event_by_record_id: dict[str, str] = {}
    newly_ingested = 0
    for record in records:
        source_record_id = str(record["record_id"])
        canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        event_id = "FEV-" + hashlib.sha256(
            f"{tenant_id}:{source_system}:{source_record_id}".encode("utf-8")
        ).hexdigest().upper()
        existing = conn.execute(
            "SELECT id,content_sha256 FROM financial_events WHERE tenant_id=? AND source_system=? AND source_record_id=?",
            (tenant_id, source_system, source_record_id),
        ).fetchone()
        if existing is not None:
            if not secrets.compare_digest(existing["content_sha256"], content_sha256):
                raise ServiceError(
                    "SOURCE_RECORD_CONFLICT",
                    "A source record ID already exists with different immutable content",
                    409,
                )
            event_by_record_id[source_record_id] = existing["id"]
            continue
        conn.execute(
            "INSERT INTO financial_events(id,tenant_id,source_system,source_record_id,record_type,payment_id,occurred_at,currency,amount,content_sha256,data_json,ingested_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id, tenant_id, source_system, source_record_id,
                str(record["record_type"]), str(record["payment_id"]), record.get("occurred_at"),
                record.get("currency"), str(record["amount"]) if record.get("amount") is not None else None,
                content_sha256, canonical, timestamp,
            ),
        )
        event_by_record_id[source_record_id] = event_id
        newly_ingested += 1
    return event_by_record_id, newly_ingested


def dashboard(tenant_id: str = "DEMO-MERCHANT-01") -> dict[str, Any]:
    conn = connect()
    try:
        cases = [_decorate_case(json.loads(row[0]), conn, tenant_id) for row in conn.execute("SELECT data_json FROM cases WHERE tenant_id=? ORDER BY id", (tenant_id,))]
        tickets = [json.loads(row[0]) for row in conn.execute("SELECT t.data_json FROM tickets t JOIN cases c ON c.id=t.case_id WHERE c.tenant_id=? ORDER BY t.created_at DESC", (tenant_id,))]
        return {
            "total_cases": len(cases), "open_cases": sum(c["status"] not in {"CLOSED", "VERIFIED"} for c in cases),
            "high_risk": sum(c["risk"]["level"] == "HIGH" for c in cases),
            "escalated": sum(c.get("decision", {}).get("outcome", "").endswith("ESCALATE") or c["status"] == "ESCALATED" for c in cases),
            "open_tickets": sum(t["status"] != "CLOSED" for t in tickets),
            "cases": cases, "tickets": tickets,
        }
    finally:
        conn.close()


def _evidence_description(case: dict[str, Any]) -> str:
    """Create a concise, evidence-attributed explanation for a decision."""
    evidence = case.get("evidence", [])
    if not evidence:
        return "No source evidence was supplied; the case cannot be safely resolved automatically."
    citations = "; ".join(
        f"{item.get('id', 'UNIDENTIFIED')} ({item.get('source_type', 'source')}, {item.get('status', 'UNKNOWN')})"
        for item in evidence
    )
    return f"The decision used {len(evidence)} source record(s): {citations}. Case evidence status: {case.get('evidence_status', 'UNKNOWN')}."


def _investigation_description(case: dict[str, Any], decision: dict[str, Any], prior_cases: list[dict[str, Any]] | None = None) -> str:
    """Create the handoff instruction that accompanies an automated escalation."""
    prior_note = ""
    if prior_cases:
        prior_note = " Review linked prior reports and their recorded outcomes before disposition."
    return (
        f"Investigate {case['title'].lower()} for payment {case.get('payment_id', 'not supplied')} "
        f"and reconcile the cited source records. Automated routing reason: {decision['reason']}"
        f"{prior_note} Do not execute a financial action until the department records a verified resolution."
    )


def list_cases(filters: dict[str, str], tenant_id: str = "DEMO-MERCHANT-01") -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute("SELECT data_json FROM cases WHERE tenant_id=? ORDER BY id", (tenant_id,)).fetchall()
        values = [_decorate_case(json.loads(r[0]), conn, tenant_id) for r in rows]
    finally:
        conn.close()
    query = filters.get("q", "").strip().casefold()
    for key, filter_key in (("status", "status"), ("type", "type"), ("department", "department"), ("priority", "priority")):
        wanted = filters.get(filter_key, "").strip().upper() if filter_key != "department" else filters.get(filter_key, "").strip().casefold()
        if wanted:
            values = [c for c in values if str(c.get(key, "")).upper() == wanted.upper()]
    if filters.get("risk"):
        values = [c for c in values if c["risk"]["level"] == filters["risk"].upper()]
    if query:
        values = [c for c in values if query in " ".join(str(c.get(k, "")) for k in ("id", "title", "type", "payment_id", "subject_id", "email_id", "summary", "department")).casefold()]
    return values


def create_detected_cases(records: list[dict[str, Any]], timing_window_days: int, actor: dict[str, str],
                          idempotency_key: str = "", schema_version: str = "1.0",
                          source_system: str = "NORMALIZED_API_DEMO") -> dict[str, Any]:
    """Persist, decide, route, and audit normalized findings in one transaction."""
    if actor["role"] not in {"analyst", "admin"}:
        raise ServiceError("FORBIDDEN", "Analyst or admin role is required to create detected cases", 403)
    if source_system not in {"NORMALIZED_API_DEMO", "RAZORPAY_PAYMENTS_API", "RAZORPAY_TEST_PAYMENTS_API"}:
        raise ServiceError("VALIDATION_ERROR", "Unknown normalized financial source")
    try:
        canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ServiceError("VALIDATION_ERROR", "Source records are not valid JSON values") from exc
    if idempotency_key and (len(idempotency_key) > 120 or any(ord(ch) < 33 or ord(ch) > 126 for ch in idempotency_key)):
        raise ServiceError("VALIDATION_ERROR", "Idempotency-Key is invalid")
    input_hash = hashlib.sha256(f"{schema_version}:{timing_window_days}:".encode() + canonical.encode("utf-8")).hexdigest()
    fingerprint = idempotency_key or input_hash
    run_hash = hashlib.sha256(f"{schema_version}:{source_system}:{actor['tenant_id']}:{actor['username']}:{fingerprint}".encode()).hexdigest()
    try:
        findings = detect_exceptions(records, timing_window_days, schema_version)
    except ValueError as exc:
        raise ServiceError("VALIDATION_ERROR", str(exc)) from exc
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        tenant_id = actor["tenant_id"]
        existing = conn.execute("SELECT response_json FROM detection_runs WHERE run_hash=? AND tenant_id=?", (run_hash, tenant_id)).fetchone()
        if existing:
            response = json.loads(existing[0])
            if response.get("input_sha256", input_hash) != input_hash:
                raise ServiceError("IDEMPOTENCY_CONFLICT", "This Idempotency-Key was already used with a different request", 409)
            response["duplicate_run"] = True
            return response
        current_year = datetime.now(timezone.utc).year
        highest = 0
        timestamp = now_iso()
        source_event_by_id, newly_ingested = _persist_financial_events(conn, records, tenant_id, timestamp, source_system)
        if newly_ingested:
            _audit(conn, actor, "FINANCIAL_EVENTS_INGESTED", "financial_event_batch", run_hash,
                   "Normalized input records were stored as immutable unverified financial events",
                   {"source_system": source_system, "record_count": newly_ingested})
        for row in conn.execute("SELECT id FROM cases"):
            prefix = f"EXC-{current_year}-"
            if row[0].startswith(prefix) and row[0][len(prefix):].isdigit():
                highest = max(highest, int(row[0][len(prefix):]))
        source_by_id = {str(record.get("record_id")): record for record in records}
        created_ids: list[str] = []
        outcomes: list[dict[str, Any]] = []
        queue_by_type = {
            "SUSPICIOUS_ACTIVITY": "Risk/Fraud", "REFUND_MISMATCH": "Refund Ops",
            "DUPLICATE_TRANSACTION": "Payment Ops", "BANK_MISMATCH": "Settlement Ops",
            "MISSING_SETTLEMENT": "Settlement Ops", "SETTLEMENT_MISMATCH": "Settlement Ops",
            "ADJUSTMENT_DISCREPANCY": "Settlement Ops", "FEE_DISCREPANCY": "Settlement Ops",
            "TIMING_EXCEPTION": "Settlement Ops", "UNKNOWN_EXCEPTION": "Finance Operations",
        }
        for finding in findings:
            highest += 1
            case_id = f"EXC-{current_year}-{highest:06d}"
            prior_cases: list[dict[str, Any]] = []
            if finding.get("subject_id") or finding.get("email_id"):
                for prior_row in conn.execute("SELECT id,data_json,updated_at FROM cases WHERE tenant_id=? ORDER BY created_at,id", (tenant_id,)):
                    prior = json.loads(prior_row["data_json"])
                    same_subject = (bool(finding.get("subject_id")) and prior.get("subject_id") == finding.get("subject_id")) or (bool(finding.get("email_id")) and str(prior.get("email_id", "")).casefold() == str(finding.get("email_id", "")).casefold())
                    if (same_subject and prior.get("subject_type") == finding.get("subject_type")
                            and prior.get("payment_id") == finding["payment_id"]
                            and prior.get("type") == finding["type"]):
                        prior_cases.append({"id": prior["id"], "status": prior["status"],
                                            "outcome": prior.get("decision", {}).get("outcome"),
                                            "report_count": int(prior.get("report_count", 1)),
                                            "updated_at": prior_row["updated_at"], "amount": prior.get("amount"),
                                            "evidence_ids": [item.get("id") for item in prior.get("evidence", [])]})
            evidence = []
            for source_id in finding["evidence_ids"]:
                record = source_by_id.get(source_id, {})
                evidence.append({
                    "id": f"EV-{case_id}-{source_id}",
                    "fact": f"Unverified normalized {record.get('record_type', 'source')} record {source_id} for payment {finding['payment_id']}",
                    "source_type": str(record.get("record_type", "unknown")),
                    "source_id": source_id,
                    "financial_event_id": source_event_by_id.get(source_id),
                    "authority": ("PROVIDER_API_RETRIEVED_PENDING_RECONCILIATION"
                                  if source_system == "RAZORPAY_PAYMENTS_API"
                                  else "PROVIDER_TEST_API_RETRIEVED_PENDING_RECONCILIATION"
                                  if source_system == "RAZORPAY_TEST_PAYMENTS_API"
                                  else "UNVERIFIED_USER_SUPPLIED_SYNTHETIC_DATA"),
                    "status": "UNVERIFIED",
                    "timestamp": str(record.get("occurred_at", timestamp)),
                })
            amount = money(finding["amount"], finding["currency"])
            priority = "HIGH" if finding["type"] == "SUSPICIOUS_ACTIVITY" or amount >= 100000 else "MEDIUM" if amount >= 25000 else "LOW"
            case = {
                "id": case_id, "type": finding["type"], "title": finding["type"].replace("_", " ").title(),
                "payment_id": finding["payment_id"], "currency": finding["currency"], "amount": str(amount),
                "subject_type": finding.get("subject_type"), "subject_id": finding.get("subject_id"), "email_id": finding.get("email_id"),
                "identity_status": "UNVERIFIED" if finding.get("subject_id") or finding.get("email_id") else "NOT_PROVIDED",
                "priority": priority, "evidence_status": "UNVERIFIED", "status": "DETECTED",
                "report_count": max((item["report_count"] for item in prior_cases), default=0) + 1,
                "department": "Risk/Fraud" if finding["type"] == "SUSPICIOUS_ACTIVITY" else queue_by_type.get(finding["type"], "Finance Operations"),
                "related_cases": [item["id"] for item in prior_cases], "subject_history": prior_cases,
                "repeat_request": ({"prior_case_id": prior_cases[-1]["id"], "prior_status": prior_cases[-1]["status"],
                                    "prior_outcome": prior_cases[-1]["outcome"], "report_count": len(prior_cases) + 1}
                                   if prior_cases else None),
                "category": "Detected from supplied source records", "action_permitted": False,
                "authority_known": False, "summary": finding["summary"], "evidence": evidence,
                "registered_at": timestamp,
                "timeline": [{"time": timestamp, "event": "Exception detected from normalized input", "source": "User-supplied synthetic record preview"}],
                "detection_run": run_hash,
            }
            policy_id = "DEMO-FEE-003" if case["type"] == "FEE_DISCREPANCY" else "DEMO-STANDARD-001"
            policy_row = conn.execute("SELECT data_json FROM policies WHERE id=?", (policy_id,)).fetchone()
            policy = json.loads(policy_row[0]) if policy_row else {"id": policy_id, "version": "UNKNOWN", "status": "UNKNOWN"}
            risk = risk_assessment(case)
            decision = decide(case, policy, risk)
            if prior_cases:
                if decision["outcome"] not in {"FRAUD_ESCALATE", "DEPARTMENT_ESCALATE"}:
                    decision["outcome"] = "DEPARTMENT_ESCALATE"
                decision["reason"] += " This request also matches prior reports; review the linked case history before disposition."
                decision["blockers"] = sorted(set(decision.get("blockers", [])) | {"REPEAT_REQUEST_REVIEW"})
            decision.update({"policy_id": policy.get("id"), "policy_version": policy.get("version"),
                             "risk_level": risk["level"], "created_at": timestamp, "automated": True,
                             "evidence_description": _evidence_description(case)})
            case["decision"], case["risk"], case["policy"] = decision, risk, policy
            case["status"] = "APPROVED" if decision["outcome"] == "AUTO_APPROVE" else "REJECTED" if decision["outcome"] == "REJECT" else "ESCALATED"
            case["timeline"].append({"time": timestamp, "event": "Automated governed decision", "source": "Deterministic decision engine"})
            ticket = None
            if decision["outcome"].endswith("ESCALATE"):
                ticket_id = "TKT-" + secrets.token_hex(5).upper()
                ticket = {"id": ticket_id, "case_id": case_id, "status": "CREATED", "department": case["department"],
                          "priority": "HIGH" if risk["level"] == "HIGH" or case["type"] == "SUSPICIOUS_ACTIVITY" else "MEDIUM" if risk["level"] == "MEDIUM" else "LOW",
                          "summary": "; ".join([case["title"], decision["reason"], "Evidence status: " + case["evidence_status"]]),
                          "investigation_data": {"finding": finding["summary"], "payment_id": case["payment_id"],
                                                 "amount": case["amount"], "currency": case["currency"],
                                                 "evidence": evidence, "risk": risk, "policy": policy,
                                                 "decision": decision, "prior_cases": prior_cases,
                                                 "required_action": _investigation_description(case, decision, prior_cases)},
                          "investigation_description": _investigation_description(case, decision, prior_cases),
                          "related_case_ids": [item["id"] for item in prior_cases],
                          "sla_due": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds"),
                          "reminders_sent": 0, "created_by": actor["username"], "created_at": timestamp, "comments": []}
                case["tickets"] = [ticket]
            conn.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)", (case_id, tenant_id, case["status"], json.dumps(case), timestamp, timestamp))
            if ticket:
                conn.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?)", (ticket["id"], case_id, ticket["status"], ticket["department"], ticket["priority"], json.dumps(ticket), timestamp, timestamp))
            for prior in prior_cases:
                old_row = conn.execute("SELECT data_json FROM cases WHERE id=? AND tenant_id=?", (prior["id"], tenant_id)).fetchone()
                if old_row is None:
                    raise ServiceError("NOT_FOUND", "Related case was not found in this tenant", 404)
                old_case = json.loads(old_row[0])
                old_case["report_count"] = len(prior_cases) + 1
                old_case["latest_reported_at"] = timestamp
                old_case.setdefault("related_cases", [])
                if case_id not in old_case["related_cases"]:
                    old_case["related_cases"].append(case_id)
                conn.execute("UPDATE cases SET data_json=?,updated_at=? WHERE id=? AND tenant_id=?", (json.dumps(old_case), timestamp, prior["id"], tenant_id))
                _audit(conn, actor, "REPEAT_REQUEST_LINKED", "case", prior["id"],
                       "A repeat report was linked under the same supplied subject identity", {"new_case_id": case_id, "report_count": old_case["report_count"]})
            _audit(conn, actor, "CASE_CREATED_FROM_DETECTION", "case", case_id,
                   "Automated detection and governed decision completed; evidence remains unverified", {"type": case["type"], "source_record_count": len(evidence), "outcome": decision["outcome"], "related_case_ids": [item["id"] for item in prior_cases]})
            _audit(conn, actor, "AUTOMATED_DECISION", "case", case_id, decision["reason"],
                   {"outcome": decision["outcome"], "risk": risk["level"], "policy_id": policy.get("id"), "ticket_id": ticket["id"] if ticket else None})
            if prior_cases:
                _audit(conn, actor, "REPEAT_REQUEST_ESCALATED", "case", case_id,
                       "Repeat request routed with prior case states and investigation references", {"prior_case_ids": [item["id"] for item in prior_cases], "outcome": decision["outcome"]})
            created_ids.append(case_id)
            outcomes.append({"case_id": case_id, "outcome": decision["outcome"], "status": case["status"],
                             "ticket_id": ticket["id"] if ticket else None, "prior_case_ids": [item["id"] for item in prior_cases]})
        response = {"created": created_ids, "count": len(created_ids), "duplicate_run": False,
                    "financial_events_ingested": newly_ingested,
                    "source_system": source_system,
                    "evidence_status": "UNVERIFIED", "decision_required": False, "outcomes": outcomes,
                    "input_sha256": input_hash}
        conn.execute("INSERT INTO detection_runs(run_hash,tenant_id,actor,response_json,created_at) VALUES(?,?,?,?,?)",
                     (run_hash, tenant_id, actor["username"], json.dumps(response), timestamp))
        conn.commit()
        return response
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_case(case_id: str, tenant_id: str = "DEMO-MERCHANT-01") -> dict[str, Any] | None:
    conn = connect()
    try:
        case = row_case(conn.execute("SELECT data_json FROM cases WHERE id=? AND tenant_id=?", (case_id, tenant_id)).fetchone())
        if case is None:
            return None
        case = _decorate_case(case, conn, tenant_id)
        case["tickets"] = [json.loads(r[0]) for r in conn.execute("SELECT t.data_json FROM tickets t JOIN cases c ON c.id=t.case_id WHERE t.case_id=? AND c.tenant_id=? ORDER BY t.created_at", (case_id, tenant_id))]
        case["audit"] = _audit_for(conn, "case", case_id, tenant_id)
        for ticket in case["tickets"]:
            case["audit"].extend(_audit_for(conn, "ticket", ticket["id"], tenant_id))
        case["audit"].sort(key=lambda item: item["created_at"])
        return case
    finally:
        conn.close()


def list_tickets(tenant_id: str = "DEMO-MERCHANT-01") -> list[dict[str, Any]]:
    conn = connect()
    try:
        return [json.loads(r[0]) for r in conn.execute("SELECT t.data_json FROM tickets t JOIN cases c ON c.id=t.case_id WHERE c.tenant_id=? ORDER BY CASE t.priority WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END, t.created_at", (tenant_id,))]
    finally:
        conn.close()


def _audit_for(conn: sqlite3.Connection, object_type: str, object_id: str, tenant_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM audit_events WHERE object_type=? AND object_id=? AND tenant_id=? ORDER BY seq", (object_type, object_id, tenant_id)).fetchall()
    return [{"id": r["id"], "actor": r["actor"], "role": r["actor_role"], "action": r["action"],
             "object_type": r["object_type"], "object_id": r["object_id"], "reason": r["reason"],
             "details": json.loads(r["details_json"]), "created_at": r["created_at"]} for r in rows]


def audit_log(limit: int = 100, tenant_id: str = "DEMO-MERCHANT-01") -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM audit_events WHERE tenant_id=? ORDER BY seq DESC LIMIT ?", (tenant_id, min(max(limit, 1), 500))).fetchall()
        return [{"id": r["id"], "actor": r["actor"], "role": r["actor_role"], "action": r["action"],
                 "object_type": r["object_type"], "object_id": r["object_id"], "reason": r["reason"],
                 "details": json.loads(r["details_json"]), "created_at": r["created_at"]} for r in rows]
    finally:
        conn.close()


def audit_integrity_status(actor: dict[str, str]) -> dict[str, Any]:
    if actor["role"] != "admin":
        raise ServiceError("FORBIDDEN", "Admin role is required to verify audit integrity", 403)
    conn = connect()
    try:
        rows = conn.execute("SELECT a.*,i.sequence,i.previous_sha256,i.event_sha256 FROM audit_events a JOIN audit_integrity i ON i.audit_event_id=a.id WHERE a.tenant_id=? ORDER BY i.sequence", (actor["tenant_id"],)).fetchall()
        expected_previous: str | None = None
        valid = True
        for row in rows:
            event = {"id": row["id"], "tenant_id": row["tenant_id"], "actor": row["actor"], "actor_role": row["actor_role"], "action": row["action"], "object_type": row["object_type"], "object_id": row["object_id"], "reason": row["reason"], "details": json.loads(row["details_json"]), "created_at": row["created_at"]}
            digest = hashlib.sha256(json.dumps({**event, "previous_sha256": expected_previous}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if row["previous_sha256"] != expected_previous or row["event_sha256"] != digest:
                valid = False
                break
            expected_previous = digest
        total = conn.execute("SELECT COUNT(*) FROM audit_events WHERE tenant_id=?", (actor["tenant_id"],)).fetchone()[0]
        return {"valid": valid, "verified_events": len(rows), "total_events": total,
                "coverage": "COMPLETE" if len(rows) == total else "FROM_SCHEMA_V5_FORWARD",
                "tail_sha256": expected_previous}
    finally:
        conn.close()


def list_policy_proposals(actor: dict[str, str]) -> list[dict[str, Any]]:
    if actor["role"] != "admin":
        raise ServiceError("FORBIDDEN", "Admin role is required to view policy proposals", 403)
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM policy_proposals WHERE tenant_id=? ORDER BY created_at DESC", (actor["tenant_id"],)).fetchall()
        return [{"id": r["id"], "policy_id": r["policy_id"], "version": r["version"], "status": r["policy_status"],
                 "source": r["source"], "effective_from": r["effective_from"], "state": r["state"],
                 "proposal": json.loads(r["data_json"]), "created_by": r["created_by"], "created_at": r["created_at"],
                 "reviewed_by": r["reviewed_by"], "reviewed_at": r["reviewed_at"], "review_reason": r["review_reason"],
                 "activated_by": r["activated_by"], "activated_at": r["activated_at"]} for r in rows]
    finally:
        conn.close()


def _policy_input(policy_id: str, version: str, status: str, source: str, description: str, effective_from: str) -> None:
    import re
    if not re.fullmatch(r"[A-Z][A-Z0-9-]{2,79}", policy_id):
        raise ServiceError("VALIDATION_ERROR", "policy_id must use uppercase letters, digits, and hyphens")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}(?:-[A-Za-z0-9.]+)?", version):
        raise ServiceError("VALIDATION_ERROR", "version must be a semantic version such as 1.0")
    if status not in {"PASS", "FAIL", "UNKNOWN"}:
        raise ServiceError("VALIDATION_ERROR", "status must be PASS, FAIL, or UNKNOWN")
    if len(source.strip()) < 8 or len(description.strip()) < 15:
        raise ServiceError("VALIDATION_ERROR", "source and description must provide sufficient review context")
    try:
        datetime.fromisoformat(effective_from.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ServiceError("VALIDATION_ERROR", "effective_from must be an ISO-8601 date or timestamp") from exc


def propose_policy(actor: dict[str, str], policy_id: str, version: str, status: str, source: str,
                   description: str, effective_from: str, rationale: str) -> dict[str, Any]:
    if actor["role"] != "admin":
        raise ServiceError("FORBIDDEN", "Admin role is required to propose a policy", 403)
    policy_id, version, status = policy_id.strip().upper(), version.strip(), status.strip().upper()
    _policy_input(policy_id, version, status, source, description, effective_from)
    if len(rationale.strip()) < 15:
        raise ServiceError("VALIDATION_ERROR", "rationale must provide sufficient change context")
    proposal_id, timestamp = "POL-" + secrets.token_hex(8).upper(), now_iso()
    payload = {"id": policy_id, "version": version, "status": status, "source": source.strip(),
               "description": description.strip(), "effective_from": effective_from, "rationale": rationale.strip()}
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("INSERT INTO policy_proposals(id,tenant_id,policy_id,version,policy_status,source,effective_from,data_json,state,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         (proposal_id, actor["tenant_id"], policy_id, version, status, source.strip(), effective_from, json.dumps(payload), "DRAFT", actor["username"], timestamp))
        except sqlite3.IntegrityError as exc:
            raise ServiceError("POLICY_VERSION_EXISTS", "That policy version already exists for this tenant", 409) from exc
        _audit(conn, actor, "POLICY_PROPOSED", "policy_proposal", proposal_id, rationale.strip(), {"policy_id": policy_id, "version": version})
        conn.commit()
        return {**payload, "id": proposal_id, "policy_id": policy_id, "state": "DRAFT",
                "created_by": actor["username"], "created_at": timestamp}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def review_policy_proposal(actor: dict[str, str], proposal_id: str, verdict: str, reason: str) -> dict[str, Any]:
    if actor["role"] != "admin":
        raise ServiceError("FORBIDDEN", "Admin role is required to review a policy", 403)
    verdict = verdict.strip().upper()
    if verdict not in {"APPROVE", "REJECT"} or len(reason.strip()) < 15:
        raise ServiceError("VALIDATION_ERROR", "A verdict and a detailed review reason are required")
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM policy_proposals WHERE id=? AND tenant_id=?", (proposal_id, actor["tenant_id"])).fetchone()
        if row is None:
            raise ServiceError("NOT_FOUND", "Policy proposal was not found", 404)
        if row["state"] != "DRAFT":
            raise ServiceError("INVALID_STATE", "Only a draft policy proposal can be reviewed", 409)
        if row["created_by"] == actor["username"]:
            raise ServiceError("SEGREGATION_OF_DUTIES", "A different admin must review this policy proposal", 409)
        state, timestamp = ("APPROVED" if verdict == "APPROVE" else "REJECTED"), now_iso()
        conn.execute("UPDATE policy_proposals SET state=?,reviewed_by=?,reviewed_at=?,review_reason=? WHERE id=?", (state, actor["username"], timestamp, reason.strip(), proposal_id))
        _audit(conn, actor, "POLICY_REVIEWED", "policy_proposal", proposal_id, reason.strip(), {"verdict": verdict})
        conn.commit()
        return {"id": proposal_id, "state": state, "reviewed_by": actor["username"], "reviewed_at": timestamp}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def activate_policy_proposal(actor: dict[str, str], proposal_id: str) -> dict[str, Any]:
    if actor["role"] != "admin":
        raise ServiceError("FORBIDDEN", "Admin role is required to activate a policy", 403)
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM policy_proposals WHERE id=? AND tenant_id=?", (proposal_id, actor["tenant_id"])).fetchone()
        if row is None:
            raise ServiceError("NOT_FOUND", "Policy proposal was not found", 404)
        if row["state"] != "APPROVED":
            raise ServiceError("INVALID_STATE", "Only an independently approved policy can be activated", 409)
        if row["reviewed_by"] == actor["username"]:
            raise ServiceError("SEGREGATION_OF_DUTIES", "A different admin must activate the approved policy", 409)
        timestamp, payload = now_iso(), json.loads(row["data_json"])
        try:
            effective_at = datetime.fromisoformat(row["effective_from"].replace("Z", "+00:00"))
            if effective_at.tzinfo is None:
                effective_at = effective_at.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ServiceError("VALIDATION_ERROR", "Stored effective_from is invalid") from exc
        if effective_at > datetime.now(timezone.utc):
            raise ServiceError("EFFECTIVE_DATE_PENDING", "A policy cannot be activated before its effective date", 409)
        conn.execute("UPDATE policy_proposals SET state='SUPERSEDED' WHERE tenant_id=? AND policy_id=? AND state='ACTIVE'", (actor["tenant_id"], row["policy_id"]))
        conn.execute("UPDATE policy_proposals SET state='ACTIVE',activated_by=?,activated_at=? WHERE id=?", (actor["username"], timestamp, proposal_id))
        _audit(conn, actor, "POLICY_ACTIVATED", "policy_proposal", proposal_id, "Independently reviewed policy version activated", {"policy_id": row["policy_id"], "version": row["version"]})
        conn.commit()
        return {"id": proposal_id, "policy_id": row["policy_id"], "version": row["version"], "state": "ACTIVE", "activated_at": timestamp}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def evaluate_case(case_id: str, actor: dict[str, str], idempotency_key: str = "") -> dict[str, Any]:
    if actor["role"] not in {"analyst", "admin"}:
        raise ServiceError("FORBIDDEN", "Analyst or admin role is required", 403)
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        scoped_key = f"{actor['username']}:{case_id}:{idempotency_key}" if idempotency_key else ""
        if idempotency_key:
            prior = conn.execute("SELECT response_json FROM idempotency WHERE key=? AND actor=?", (scoped_key, actor["username"])).fetchone()
            if prior:
                decision = json.loads(prior[0])
                case = row_case(conn.execute("SELECT data_json FROM cases WHERE id=? AND tenant_id=?", (case_id, actor["tenant_id"])).fetchone())
                if case is None:
                    raise ServiceError("NOT_FOUND", "Case was not found", 404)
                case = _decorate_case(case, conn, actor["tenant_id"])
                case["tickets"] = [json.loads(r[0]) for r in conn.execute("SELECT t.data_json FROM tickets t JOIN cases c ON c.id=t.case_id WHERE t.case_id=? AND c.tenant_id=? ORDER BY t.created_at", (case_id, actor["tenant_id"]))]
                return {"case": case, "decision": decision, "risk": case["risk"]}
        case = row_case(conn.execute("SELECT data_json FROM cases WHERE id=? AND tenant_id=?", (case_id, actor["tenant_id"])).fetchone())
        if case is None:
            raise ServiceError("NOT_FOUND", "Case was not found", 404)
        if case.get("decision"):
            decision = case["decision"]
            if idempotency_key:
                conn.execute("INSERT INTO idempotency VALUES(?,?,?,?)", (scoped_key, actor["username"], json.dumps(decision), now_iso()))
                conn.commit()
            case = _decorate_case(case, conn, actor["tenant_id"])
            case["tickets"] = [json.loads(r[0]) for r in conn.execute("SELECT t.data_json FROM tickets t JOIN cases c ON c.id=t.case_id WHERE t.case_id=? AND c.tenant_id=? ORDER BY t.created_at", (case_id, actor["tenant_id"]))]
            return {"case": case, "decision": decision, "risk": case["risk"]}
        policy_id = "DEMO-FEE-003" if case["type"] == "FEE_DISCREPANCY" else "DEMO-STANDARD-001"
        policy = _policy_for(conn, policy_id, actor["tenant_id"])
        risk = risk_assessment(case)
        decision = decide(case, policy, risk)
        decision.update({"policy_id": policy.get("id"), "policy_version": policy.get("version"), "risk_level": risk["level"], "created_at": now_iso(),
                         "automated": actor["username"] == "system-automation", "evidence_description": _evidence_description(case)})
        case["decision"] = decision
        case["risk"] = risk
        if decision["outcome"].endswith("ESCALATE"):
            case["status"] = "ESCALATED"
            ticket_id = "TKT-" + secrets.token_hex(5).upper()
            ticket = {"id": ticket_id, "case_id": case_id, "status": "CREATED", "department": case["department"],
                      "priority": "HIGH" if risk["level"] == "HIGH" else "MEDIUM" if risk["level"] == "MEDIUM" else "LOW",
                      "summary": "; ".join([case["title"], decision["reason"], "Evidence status: " + case["evidence_status"]]),
                      "investigation_description": _investigation_description(case, decision),
                      "sla_due": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds"), "reminders_sent": 0, "created_by": actor["username"], "created_at": now_iso(), "comments": []}
            conn.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?)", (ticket_id, case_id, ticket["status"], ticket["department"], ticket["priority"], json.dumps(ticket), ticket["created_at"], ticket["created_at"]))
            case.setdefault("tickets", []).append(ticket)
        else:
            case["status"] = "APPROVED" if decision["outcome"] == "AUTO_APPROVE" else "REJECTED" if decision["outcome"] == "REJECT" else "DECISION_READY"
        timestamp = now_iso()
        conn.execute("UPDATE cases SET status=?, data_json=?, updated_at=? WHERE id=? AND tenant_id=?", (case["status"], json.dumps(case), timestamp, case_id, actor["tenant_id"]))
        _audit(conn, actor, "CASE_EVALUATED", "case", case_id, decision["reason"], {"outcome": decision["outcome"], "risk": risk["level"], "policy_id": policy.get("id")})
        if idempotency_key:
            conn.execute("INSERT INTO idempotency VALUES(?,?,?,?)", (scoped_key, actor["username"], json.dumps(decision), timestamp))
        conn.commit()
        return {"case": case, "decision": decision, "risk": risk}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def auto_evaluate_pending_cases(tenant_id: str = "DEMO-MERCHANT-01") -> dict[str, Any]:
    """Evaluate legacy pending cases during controlled startup without user interaction.

    The detector already evaluates new cases atomically. This fills the same
    deterministic decision record for older imported or seeded cases that have
    no decision yet. Escalations still create a department ticket; no financial
    side effect is executed by this function.
    """
    actor = {"username": "system-automation", "role": "admin", "tenant_id": tenant_id}
    conn = connect()
    try:
        rows = conn.execute("SELECT id FROM cases WHERE tenant_id=?", (tenant_id,)).fetchall()
        pending = [row["id"] for row in rows if not (row_case(conn.execute("SELECT data_json FROM cases WHERE id=? AND tenant_id=?", (row["id"], tenant_id)).fetchone()) or {}).get("decision")]
    finally:
        conn.close()
    outcomes = []
    for case_id in pending:
        result = evaluate_case(case_id, actor, f"startup-auto-{case_id}")
        outcomes.append({"case_id": case_id, "outcome": result["decision"]["outcome"]})
    return {"evaluated": len(outcomes), "outcomes": outcomes}


def investigate_case(case_id: str, actor: dict[str, str]) -> dict[str, Any]:
    """Generate bounded advisory investigation output from controlled case data."""
    if actor["role"] not in {"analyst", "admin", "department"}:
        raise ServiceError("FORBIDDEN", "An authorized workspace role is required", 403)
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        case = row_case(conn.execute("SELECT data_json FROM cases WHERE id=? AND tenant_id=?", (case_id, actor["tenant_id"])).fetchone())
        if case is None:
            raise ServiceError("NOT_FOUND", "Case was not found", 404)
        existing = case.get("ai_investigation")
        if existing:
            return existing
        policy_id = "DEMO-FEE-003" if case["type"] == "FEE_DISCREPANCY" else "DEMO-STANDARD-001"
        context = {"exception": {key: case.get(key) for key in ("id", "type", "title", "summary", "payment_id", "amount", "currency", "status")},
                   "financial_events": [{"id": item.get("financial_event_id"), "source_id": item.get("source_id"), "source_type": item.get("source_type"), "status": item.get("status")} for item in case.get("evidence", [])],
                   "evidence": case.get("evidence", []), "risk": risk_assessment(case), "policies": [_policy_for(conn, policy_id, actor["tenant_id"])],
                   "timeline": case.get("timeline", []), "decision": case.get("decision", {})}
        result = ai_investigate(context).model_dump(mode="json")
        case["ai_investigation"] = result
        timestamp = now_iso()
        case.setdefault("timeline", []).append({"time": timestamp, "event": "Investigation assistance generated", "source": result["provider"]})
        conn.execute("UPDATE cases SET data_json=?, updated_at=? WHERE id=? AND tenant_id=?", (json.dumps(case), timestamp, case_id, actor["tenant_id"]))
        _audit(conn, actor, "AI_INVESTIGATION_GENERATED", "case", case_id, result["notice"], {"provider": result["provider"], "status": result["status"], "evidence_ids": result["finding"]["evidence_ids"]})
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ticket_in_tx(conn: sqlite3.Connection, ticket_id: str, tenant_id: str) -> dict[str, Any]:
    ticket = row_ticket(conn.execute("SELECT t.data_json FROM tickets t JOIN cases c ON c.id=t.case_id WHERE t.id=? AND c.tenant_id=?", (ticket_id, tenant_id)).fetchone())
    if ticket is None:
        raise ServiceError("NOT_FOUND", "Ticket was not found", 404)
    return ticket


def respond_to_ticket(ticket_id: str, actor: dict[str, str], comment: str) -> dict[str, Any]:
    if actor["role"] not in {"department", "admin"}:
        raise ServiceError("FORBIDDEN", "Department or admin role is required", 403)
    comment = comment.strip()
    if not 5 <= len(comment) <= 2000:
        raise ServiceError("VALIDATION_ERROR", "Response must be between 5 and 2,000 characters")
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ticket = _ticket_in_tx(conn, ticket_id, actor["tenant_id"])
        if ticket["status"] in {"ASSIGNED", "CREATED"}:
            validate_transition(ticket["status"], "OPEN")
            ticket["status"] = "OPEN"
        if ticket["status"] != "UNDER_REVIEW":
            validate_transition(ticket["status"], "RESPONDED")
            ticket["status"] = "RESPONDED"
            validate_transition(ticket["status"], "UNDER_REVIEW")
            ticket["status"] = "UNDER_REVIEW"
        ticket.setdefault("comments", []).append({"actor": actor["username"], "text": comment, "created_at": now_iso()})
        ticket["updated_at"] = now_iso()
        conn.execute("UPDATE tickets SET status=?,data_json=?,updated_at=? WHERE id=? AND case_id IN (SELECT id FROM cases WHERE tenant_id=?)", (ticket["status"], json.dumps(ticket), ticket["updated_at"], ticket_id, actor["tenant_id"]))
        _audit(conn, actor, "DEPARTMENT_RESPONSE", "ticket", ticket_id, "Department response recorded", {"comment": comment})
        conn.commit()
        return ticket
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def resolve_ticket(ticket_id: str, actor: dict[str, str], resolution: str, evidence_ids: list[str]) -> dict[str, Any]:
    if actor["role"] not in {"department", "admin"}:
        raise ServiceError("FORBIDDEN", "Department or admin role is required", 403)
    resolution = resolution.strip()
    if not 15 <= len(resolution) <= 2000:
        raise ServiceError("VALIDATION_ERROR", "Resolution must be between 15 and 2,000 characters")
    if not evidence_ids or len(evidence_ids) > 20 or any(not isinstance(x, str) for x in evidence_ids):
        raise ServiceError("VALIDATION_ERROR", "Select at least one valid evidence item")
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ticket = _ticket_in_tx(conn, ticket_id, actor["tenant_id"])
        case = row_case(conn.execute("SELECT data_json FROM cases WHERE id=? AND tenant_id=?", (ticket["case_id"], actor["tenant_id"])).fetchone())
        if case is None:
            raise ServiceError("NOT_FOUND", "Case was not found", 404)
        valid = {item["id"] for item in case.get("evidence", []) if item["status"] == "VERIFIED"}
        if not set(evidence_ids).issubset(valid):
            raise ServiceError("VALIDATION_ERROR", "Resolution citations must refer to verified evidence for this case")
        validate_transition(ticket["status"], "RESOLVED")
        ticket["status"] = "RESOLVED"
        ticket["resolution"] = {"text": resolution, "evidence_ids": sorted(set(evidence_ids)), "actor": actor["username"], "created_at": now_iso()}
        ticket["updated_at"] = now_iso()
        conn.execute("UPDATE tickets SET status=?,data_json=?,updated_at=? WHERE id=? AND case_id IN (SELECT id FROM cases WHERE tenant_id=?)", (ticket["status"], json.dumps(ticket), ticket["updated_at"], ticket_id, actor["tenant_id"]))
        case["resolution"] = ticket["resolution"]
        case["status"] = "RESOLVED"
        conn.execute("UPDATE cases SET status=?,data_json=?,updated_at=? WHERE id=? AND tenant_id=?", (case["status"], json.dumps(case), now_iso(), case["id"], actor["tenant_id"]))
        _audit(conn, actor, "RESOLUTION_SUBMITTED", "ticket", ticket_id, resolution, {"evidence_ids": ticket["resolution"]["evidence_ids"]})
        conn.commit()
        return {"ticket": ticket, "case": case}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_ticket(ticket_id: str, actor: dict[str, str]) -> dict[str, Any]:
    if actor["role"] not in {"analyst", "admin"}:
        raise ServiceError("FORBIDDEN", "Analyst or admin role is required to verify a resolution", 403)
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ticket = _ticket_in_tx(conn, ticket_id, actor["tenant_id"])
        if ticket["status"] != "RESOLVED" or not ticket.get("resolution"):
            raise ServiceError("INVALID_STATE", "Only a submitted resolution can be verified", 409)
        case = row_case(conn.execute("SELECT data_json FROM cases WHERE id=? AND tenant_id=?", (ticket["case_id"], actor["tenant_id"])).fetchone())
        if case is None:
            raise ServiceError("NOT_FOUND", "Case was not found", 404)
        verified_ids = {item["id"] for item in case.get("evidence", []) if item["status"] == "VERIFIED"}
        citations_valid = bool(ticket["resolution"]["evidence_ids"]) and set(ticket["resolution"]["evidence_ids"]).issubset(verified_ids)
        resolution_valid = len(ticket["resolution"]["text"].strip()) >= 15
        passed = citations_valid and resolution_valid
        result = {"status": "PASSED" if passed else "FAILED", "checks": {"verified_evidence_cited": citations_valid, "resolution_recorded": resolution_valid},
                  "method": "Independent synthetic demo consistency check; no external financial system is connected.", "verified_by": actor["username"], "created_at": now_iso()}
        ticket["verification"] = result
        target = "VERIFIED" if passed else "OPEN"
        validate_transition(ticket["status"], target)
        ticket["status"] = target
        ticket["updated_at"] = now_iso()
        case["verification"] = result
        case["status"] = "VERIFIED" if passed else "ESCALATED"
        conn.execute("UPDATE tickets SET status=?,data_json=?,updated_at=? WHERE id=? AND case_id IN (SELECT id FROM cases WHERE tenant_id=?)", (ticket["status"], json.dumps(ticket), ticket["updated_at"], ticket_id, actor["tenant_id"]))
        conn.execute("UPDATE cases SET status=?,data_json=?,updated_at=? WHERE id=? AND tenant_id=?", (case["status"], json.dumps(case), now_iso(), case["id"], actor["tenant_id"]))
        _audit(conn, actor, "RESOLUTION_VERIFICATION_" + result["status"], "ticket", ticket_id, result["method"], result)
        if passed:
            validate_transition(ticket["status"], "CLOSED")
            ticket["status"] = "CLOSED"
            ticket["updated_at"] = now_iso()
            case["status"] = "CLOSED"
            conn.execute("UPDATE tickets SET status=?,data_json=?,updated_at=? WHERE id=? AND case_id IN (SELECT id FROM cases WHERE tenant_id=?)", (ticket["status"], json.dumps(ticket), ticket["updated_at"], ticket_id, actor["tenant_id"]))
            conn.execute("UPDATE cases SET status=?,data_json=?,updated_at=? WHERE id=? AND tenant_id=?", (case["status"], json.dumps(case), now_iso(), case["id"], actor["tenant_id"]))
            _audit(conn, actor, "TICKET_CLOSED", "ticket", ticket_id, "Resolution passed independent demo verification", {"verification_status": result["status"]})
        conn.commit()
        return {"ticket": ticket, "case": case, "verification": result}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_reminders(actor: dict[str, str], now: datetime | None = None) -> dict[str, Any]:
    """Record at most one overdue reminder per ticket per 24-hour slot."""
    if actor["role"] not in {"admin", "analyst"}:
        raise ServiceError("FORBIDDEN", "Analyst or admin role is required to run reminders", 403)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ServiceError("VALIDATION_ERROR", "Reminder time must include a timezone")
    conn = connect()
    created: list[dict[str, Any]] = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT t.id,t.data_json FROM tickets t JOIN cases c ON c.id=t.case_id WHERE c.tenant_id=? AND t.status NOT IN ('RESOLVED','VERIFIED','CLOSED')", (actor["tenant_id"],)).fetchall()
        for row in rows:
            ticket = json.loads(row["data_json"])
            if not ticket.get("sla_due"):
                continue
            try:
                due = datetime.fromisoformat(ticket["sla_due"])
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if current < due:
                continue
            reminders = ticket.setdefault("reminders", [])
            last_sent = datetime.fromisoformat(reminders[-1]["sent_at"]) if reminders else due - timedelta(days=1)
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if current - last_sent < timedelta(days=1):
                continue
            reminder = {"id": f"RMD-{ticket['id']}-{len(reminders)+1}", "sent_at": current.isoformat(timespec="seconds"),
                        "channel": "in-app demo notification", "recipient_queue": ticket["department"],
                        "message": "Ticket is overdue; department response is required."}
            reminders.append(reminder)
            ticket["reminders_sent"] = len(reminders)
            ticket["updated_at"] = now_iso()
            conn.execute("UPDATE tickets SET data_json=?,updated_at=? WHERE id=? AND case_id IN (SELECT id FROM cases WHERE tenant_id=?)", (json.dumps(ticket), ticket["updated_at"], ticket["id"], actor["tenant_id"]))
            _audit(conn, actor, "SLA_REMINDER_RECORDED", "ticket", ticket["id"], "Ticket exceeded its configured SLA", reminder)
            created.append(reminder)
        conn.commit()
        return {"created": created, "count": len(created)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
