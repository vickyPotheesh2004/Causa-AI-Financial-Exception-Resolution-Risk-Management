"""Deterministic, provider-independent domain rules for Cause AI."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

DECISION_OUTCOMES = {
    "AUTO_APPROVE",
    "REJECT",
    "FRAUD_ESCALATE",
    "DEPARTMENT_ESCALATE",
}
ACTIVE_CASE_STATES = {"DETECTED", "INVESTIGATING", "DECISION_READY", "ESCALATED", "RESOLVED"}
TICKET_TRANSITIONS = {
    "CREATED": {"ASSIGNED", "OPEN"},
    "ASSIGNED": {"OPEN", "WAITING_FOR_RESPONSE"},
    "OPEN": {"WAITING_FOR_RESPONSE", "RESPONDED", "RESOLVED"},
    "WAITING_FOR_RESPONSE": {"RESPONDED", "OPEN"},
    "RESPONDED": {"UNDER_REVIEW", "OPEN", "RESOLVED"},
    "UNDER_REVIEW": {"OPEN", "RESOLVED"},
    "RESOLVED": {"VERIFIED", "OPEN"},
    "VERIFIED": {"CLOSED", "OPEN"},
    "CLOSED": set(),
}

_IDENTITY_RECORD_FIELDS = {"subject_type", "subject_id", "email_id"}
_COMMON_RECORD_FIELDS = {"record_type", "record_id", "payment_id", "currency", "amount", "occurred_at", "status", "suspicious_signal"}
_RECORD_TYPE_FIELDS = {
    "payment": _COMMON_RECORD_FIELDS | {"expected_fee_amount", "refund_attempt_count"},
    "fee": _COMMON_RECORD_FIELDS,
    "refund": _COMMON_RECORD_FIELDS,
    "refund_request": _COMMON_RECORD_FIELDS | {"requested_amount"},
    "adjustment": _COMMON_RECORD_FIELDS,
    "settlement": _COMMON_RECORD_FIELDS,
    "bank": _COMMON_RECORD_FIELDS,
    "report": _COMMON_RECORD_FIELDS,
}


def money(value: Any, currency: str = "INR") -> Decimal:
    """Parse an amount using Decimal and quantize according to configured currency."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Amount must be a valid decimal number") from exc
    if not amount.is_finite():
        raise ValueError("Amount must be finite")
    if currency not in {"INR", "USD", "EUR", "GBP"}:
        raise ValueError("Unsupported currency")
    try:
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Amount exceeds the supported precision") from exc


def calculate_expected_settlement(payment: Any, fees: Any, refunds: Any = 0, adjustments: Any = 0) -> Decimal:
    return money(payment) - money(fees) - money(refunds) + money(adjustments)


def risk_assessment(case: dict[str, Any]) -> dict[str, Any]:
    """Produce transparent risk dimensions and evidence-linked reasons."""
    amount = money(case.get("amount", "0"))
    score = 10
    factors: list[dict[str, str]] = []

    def add(points: int, dimension: str, explanation: str, evidence_id: str = "") -> None:
        nonlocal score
        score += points
        factors.append({"dimension": dimension, "points": str(points), "explanation": explanation, "evidence_id": evidence_id})

    currency = case.get("currency", "INR")
    if currency != "INR":
        add(25, "financial", f"Risk thresholds are INR-denominated; no {currency} conversion is configured")
    elif amount >= Decimal("100000"):
        add(35, "financial", "Exposure is at least INR 100,000", "EV-" + case["id"] + "-payment")
    elif amount >= Decimal("25000"):
        add(20, "financial", "Exposure is at least INR 25,000", "EV-" + case["id"] + "-payment")
    elif amount >= Decimal("5000"):
        add(10, "financial", "Exposure is at least INR 5,000", "EV-" + case["id"] + "-payment")
    if case.get("type") == "SUSPICIOUS_ACTIVITY":
        add(40, "fraud", "Suspicious activity requires specialist review", "EV-" + case["id"] + "-signal")
    if case.get("evidence_status") != "VERIFIED":
        add(25, "compliance", "Evidence is unverified, conflicting, or incomplete")
    if int(case.get("report_count", 1)) >= 3:
        add(15, "operational", "The issue has been reported repeatedly")
    score = min(score, 100)
    level = "HIGH" if score >= 70 else "MEDIUM" if score >= 40 else "LOW"
    return {"score": score, "level": level, "factors": factors}


def decide(case: dict[str, Any], policy: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    """Return one safe, evidence-aware decision; never execute a financial action."""
    blockers: list[str] = []
    evidence_status = case.get("evidence_status", "UNKNOWN")
    if evidence_status not in {"VERIFIED", "CONFLICTING"}:
        blockers.append("INSUFFICIENT_EVIDENCE")
    if evidence_status == "CONFLICTING":
        blockers.append("CONFLICTING_EVIDENCE")
    policy_status = policy.get("status", "UNKNOWN")
    if policy_status not in {"PASS", "FAIL"}:
        blockers.append("POLICY_" + (policy_status if policy_status in {"UNKNOWN", "CONFLICT"} else "UNKNOWN"))
    if not case.get("authority_known", False):
        blockers.append("AUTHORITY_UNKNOWN")
    if case.get("currency", "INR") != "INR":
        blockers.append("CURRENCY_CONVERSION_UNAVAILABLE")
    if case.get("type") == "SUSPICIOUS_ACTIVITY":
        return {"outcome": "FRAUD_ESCALATE", "reason": "Possible suspicious activity requires specialist investigation.", "blockers": blockers}
    if blockers:
        return {"outcome": "DEPARTMENT_ESCALATE", "reason": "The case needs human review before a safe decision can be made.", "blockers": blockers}
    if policy_status == "FAIL":
        return {"outcome": "REJECT", "reason": "The supplied request fails the configured demo rule.", "blockers": []}
    if (risk["level"] == "LOW" and policy_status == "PASS" and case.get("action_permitted", False)
            and case.get("reconciliation_status") != "RECONCILED"):
        return {"outcome": "DEPARTMENT_ESCALATE", "reason": "Financial reconciliation is unresolved; an authorized reviewer must confirm the exception is resolved.", "blockers": ["RECONCILIATION_UNRESOLVED"]}
    if not case.get("action_permitted", False):
        blockers.append("ACTION_NOT_PERMITTED")
    if not case.get("action_idempotent", False):
        blockers.append("ACTION_NOT_IDEMPOTENT")
    if blockers:
        return {"outcome": "DEPARTMENT_ESCALATE", "reason": "The case needs human review before a safe action can be approved.", "blockers": blockers}
    if risk["level"] == "LOW" and case.get("action_permitted", False) and case.get("action_idempotent", False) and policy_status == "PASS":
        return {"outcome": "AUTO_APPROVE", "reason": "Demo criteria pass; no financial action is executed by this demo.", "blockers": []}
    return {"outcome": "DEPARTMENT_ESCALATE", "reason": "Configured review is required for this case.", "blockers": ["MANUAL_REVIEW_REQUIRED"]}


def validate_transition(current: str, target: str) -> None:
    if target not in TICKET_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid ticket transition: {current} -> {target}")


def detect_exceptions(records: list[dict[str, Any]], timing_window_days: int = 7, schema_version: str = "1.0") -> list[dict[str, Any]]:
    """Detect explainable anomalies from normalized synthetic financial records.

    Accepted record_type values: payment, fee, refund, refund_request, adjustment,
    settlement, bank, and report. This function does not create or execute actions.
    """
    if not isinstance(records, list) or not records or len(records) > 5000:
        raise ValueError("Provide between 1 and 5,000 normalized source records")
    if isinstance(timing_window_days, bool) or not isinstance(timing_window_days, int) or not 0 <= timing_window_days <= 365:
        raise ValueError("timing_window_days must be between 0 and 365")
    if schema_version not in {"1.0", "1.1"}:
        raise ValueError("schema_version must be 1.0 or 1.1")
    allowed = {"payment", "fee", "refund", "refund_request", "adjustment", "settlement", "bank", "report"}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unknown: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    identities: set[tuple[str, str, str]] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Record {index + 1} must be an object")
        kind = str(record.get("record_type", "")).strip().lower()
        if kind in _RECORD_TYPE_FIELDS:
            allowed_fields = _RECORD_TYPE_FIELDS[kind] | (_IDENTITY_RECORD_FIELDS if schema_version == "1.1" else set())
            extra_fields = set(record) - allowed_fields
            if extra_fields:
                names = ", ".join(sorted(str(name)[:80] for name in extra_fields)[:10])
                raise ValueError(f"Record {index + 1} has unsupported {kind} field(s): {names}")
        else:
            allowed_fields = _COMMON_RECORD_FIELDS | (_IDENTITY_RECORD_FIELDS if schema_version == "1.1" else set())
            extra_fields = set(record) - allowed_fields
            if extra_fields:
                names = ", ".join(sorted(str(name)[:80] for name in extra_fields)[:10])
                raise ValueError(f"Record {index + 1} has unsupported field(s): {names}")
        payment_id = str(record.get("payment_id", "")).strip()
        record_id = str(record.get("record_id", "")).strip()
        if not kind or not payment_id or not record_id:
            raise ValueError(f"Record {index + 1} requires record_type, payment_id, and record_id")
        if len(kind) > 60 or len(payment_id) > 120 or len(record_id) > 120:
            raise ValueError(f"Record {index + 1} has an identifier that exceeds its allowed length")
        if "suspicious_signal" in record and not isinstance(record["suspicious_signal"], bool):
            raise ValueError(f"Record {index + 1} suspicious_signal must be a JSON boolean")
        for field in ("record_type", "record_id", "payment_id", "currency", "occurred_at", "status"):
            if field in record and not isinstance(record[field], str):
                raise ValueError(f"Record {index + 1} {field} must be a string")
        if "currency" in record and (not record["currency"].strip() or len(record["currency"]) != 3 or not record["currency"].isalpha()):
            raise ValueError(f"Record {index + 1} currency must be a three-letter alphabetic code")
        if any(field in record and not isinstance(record[field], str) for field in _IDENTITY_RECORD_FIELDS):
            raise ValueError(f"Record {index + 1} identity fields must be strings")
        if any(field in record and len(record[field]) > limit for field, limit in (("subject_type", 10), ("subject_id", 120), ("email_id", 254))):
            raise ValueError(f"Record {index + 1} has an identity field that exceeds its allowed length")
        subject_type, subject_id, email_id = (record.get(field, "").strip() for field in ("subject_type", "subject_id", "email_id"))
        if subject_type and subject_type.upper() not in {"USER", "COMPANY"}:
            raise ValueError(f"Record {index + 1} subject_type must be USER or COMPANY")
        if subject_id and not subject_type:
            raise ValueError(f"Record {index + 1} subject_type is required when subject_id is supplied")
        if email_id and (email_id.count("@") != 1 or email_id.startswith("@") or email_id.endswith("@")):
            raise ValueError(f"Record {index + 1} email_id must be a valid email-shaped identifier")
        if subject_type or subject_id or email_id:
            identities.add((subject_type.upper(), subject_id, email_id.casefold()))
        if "refund_attempt_count" in record and (isinstance(record["refund_attempt_count"], bool) or not isinstance(record["refund_attempt_count"], int) or record["refund_attempt_count"] < 0):
            raise ValueError(f"Record {index + 1} refund_attempt_count must be a non-negative integer")
        if record_id in seen_record_ids:
            raise ValueError(f"Duplicate source record ID: {record_id}")
        seen_record_ids.add(record_id)
        if kind not in allowed:
            unknown.append({"record_type": kind, "payment_id": payment_id, "evidence_ids": [record_id], "summary": f"Unrecognized source record type: {kind}"})
        else:
            groups[payment_id].append(record)

    if len(identities) > 1:
        raise ValueError("All identity fields in one input bundle must refer to the same user or company")
    identity = next(iter(identities), ("", "", ""))
    identity_fields = {"subject_type": identity[0] or None, "subject_id": identity[1] or None, "email_id": identity[2] or None}

    findings: list[dict[str, Any]] = []

    def emit(kind: str, payment_id: str, currency_code: str, amount: Decimal,
             involved: list[dict[str, Any]], summary: str) -> None:
        findings.append({"type": kind, "payment_id": payment_id, "currency": currency_code,
                         "amount": str(money(amount, currency_code)),
                         "evidence_ids": sorted({str(r["record_id"]) for r in involved}),
                         "summary": summary, **identity_fields})

    for payment_id, items in groups.items():
        payments = [r for r in items if str(r["record_type"]).lower() == "payment"]
        settlements = [r for r in items if str(r["record_type"]).lower() == "settlement"]
        fees = [r for r in items if str(r["record_type"]).lower() == "fee"]
        refunds = [r for r in items if str(r["record_type"]).lower() in {"refund", "refund_request"}]
        adjustments = [r for r in items if str(r["record_type"]).lower() == "adjustment"]
        banks = [r for r in items if str(r["record_type"]).lower() == "bank"]
        reports = [r for r in items if str(r["record_type"]).lower() == "report"]
        if not payments:
            emit("UNKNOWN_EXCEPTION", payment_id, "INR", Decimal("0"), items, "No authoritative payment record was found for this group.")
            continue
        currencies = {str(r.get("currency", "INR")).upper() for r in items if r.get("amount") is not None}
        if len(currencies) > 1 or (currencies and next(iter(currencies)) not in {"INR", "USD", "EUR", "GBP"}):
            emit("UNKNOWN_EXCEPTION", payment_id, "INR", Decimal("0"), items, "Source currencies conflict or are unsupported; calculation was not attempted.")
            continue
        currency_code = next(iter(currencies), "INR")
        try:
            payment_amounts = [money(r["amount"], currency_code) for r in payments]
            fee_total = sum((money(r["amount"], currency_code) for r in fees), Decimal("0.00"))
            refund_total = sum((money(r.get("amount", r.get("requested_amount", "0")), currency_code) for r in refunds if str(r.get("record_type")).lower() == "refund"), Decimal("0.00"))
            adjustment_total = sum((money(r["amount"], currency_code) for r in adjustments), Decimal("0.00"))
            settlement_total = sum((money(r["amount"], currency_code) for r in settlements), Decimal("0.00"))
            bank_total = sum((money(r["amount"], currency_code) for r in banks), Decimal("0.00"))
        except (KeyError, ValueError, InvalidOperation):
            emit("UNKNOWN_EXCEPTION", payment_id, currency_code, Decimal("0"), items, "One or more source amounts are missing or invalid; calculation was not attempted.")
            continue
        payment_total = sum(payment_amounts, Decimal("0.00"))
        if len(payments) > 1:
            emit("DUPLICATE_TRANSACTION", payment_id, currency_code, max(payment_amounts), payments, f"{len(payments)} payment records share the same payment reference.")
        try:
            requested_refunds = sum((money(r.get("requested_amount", r.get("amount", "0")), currency_code) for r in refunds if str(r.get("record_type")).lower() == "refund_request"), Decimal("0.00"))
        except (ValueError, InvalidOperation):
            emit("UNKNOWN_EXCEPTION", payment_id, currency_code, Decimal("0"), refunds, "Requested refund amount is invalid; comparison was not attempted.")
            requested_refunds = Decimal("0.00")
        if any(str(r.get("status", "")).upper() not in {"SUCCEEDED", "COMPLETED"} for r in refunds) or (requested_refunds > 0 and requested_refunds != refund_total):
            emit("REFUND_MISMATCH", payment_id, currency_code, abs(requested_refunds - refund_total), refunds, "Requested and completed refund amounts do not agree or a refund remains unresolved.")
        for payment in payments:
            expected_fee = payment.get("expected_fee_amount")
            if expected_fee is not None and money(expected_fee, currency_code) != fee_total:
                emit("FEE_DISCREPANCY", payment_id, currency_code, abs(money(expected_fee, currency_code) - fee_total), [payment, *fees], "Recorded fees differ from the supplied expected fee amount.")
        if not settlements and str(payments[0].get("status", "CAPTURED")).upper() in {"CAPTURED", "SUCCEEDED", "COMPLETED"}:
            emit("MISSING_SETTLEMENT", payment_id, currency_code, payment_total, payments, "A captured payment has no linked settlement record.")
        elif settlements:
            expected_settlement = calculate_expected_settlement(payment_total, fee_total, refund_total, adjustment_total)
            if settlement_total != expected_settlement:
                kind = "ADJUSTMENT_DISCREPANCY" if adjustments else "SETTLEMENT_MISMATCH"
                emit(kind, payment_id, currency_code, abs(settlement_total - expected_settlement), [*payments, *fees, *refunds, *adjustments, *settlements], f"Expected settlement {expected_settlement}; source settlements total {settlement_total}.")
            if banks and bank_total != settlement_total:
                emit("BANK_MISMATCH", payment_id, currency_code, abs(bank_total - settlement_total), [*settlements, *banks], f"Bank entries total {bank_total}; source settlements total {settlement_total}.")
            payment_dates = [str(r.get("occurred_at", ""))[:10] for r in payments if r.get("occurred_at")]
            settlement_dates = [str(r.get("occurred_at", ""))[:10] for r in settlements if r.get("occurred_at")]
            try:
                if payment_dates and settlement_dates and (date.fromisoformat(settlement_dates[0]) - date.fromisoformat(payment_dates[0])).days > timing_window_days:
                    emit("TIMING_EXCEPTION", payment_id, currency_code, settlement_total, [payments[0], settlements[0]], f"Settlement occurred more than {timing_window_days} days after payment.")
            except ValueError:
                emit("UNKNOWN_EXCEPTION", payment_id, currency_code, Decimal("0"), [payments[0], settlements[0]], "Payment or settlement date is invalid; timing comparison was not attempted.")
        try:
            attempts = max([len(refunds), len(reports), *[int(r.get("refund_attempt_count", 0)) for r in payments]])
        except (ValueError, TypeError):
            emit("UNKNOWN_EXCEPTION", payment_id, currency_code, Decimal("0"), payments, "Refund attempt count is invalid; suspicious activity could not be evaluated.")
            attempts = 0
        suspicious = any(r.get("suspicious_signal", False) is True for r in items) or attempts >= 4
        if suspicious:
            emit("SUSPICIOUS_ACTIVITY", payment_id, currency_code, payment_total, [*payments, *refunds, *reports], "A source marked suspicious activity or at least four refund/report attempts require specialist review.")
    for item in unknown:
        findings.append({"type": "UNKNOWN_EXCEPTION", "payment_id": item["payment_id"], "currency": "INR", "amount": "0.00", "evidence_ids": item["evidence_ids"], "summary": item["summary"], **identity_fields})
    return findings
