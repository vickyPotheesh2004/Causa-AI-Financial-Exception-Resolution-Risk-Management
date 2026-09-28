"""Create the versioned, synthetic 100-scenario benchmark dataset."""

from __future__ import annotations

from typing import Any

SEED = 20260928
CATEGORIES = ("NORMAL", "SETTLEMENT_MISMATCH", "REFUND_MISMATCH", "FEE_DISCREPANCY", "DUPLICATE_TRANSACTION", "MISSING_SETTLEMENT", "BANK_MISMATCH", "TIMING_EXCEPTION", "SUSPICIOUS_ACTIVITY")


def _record(kind: str, scenario: int, payment: str, amount: str, ordinal: int = 1, **extra: Any) -> dict[str, Any]:
    return {"record_type": kind, "record_id": f"BEN-{scenario:03d}-{kind.upper()}-{ordinal}", "payment_id": payment,
            "currency": "INR", "amount": amount, "occurred_at": "2026-09-01", "status": "CAPTURED", **extra}


def generate() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scenarios: list[dict[str, Any]] = []
    truth: list[dict[str, Any]] = []
    index = 0
    for category in CATEGORIES:
        for _ in range(20 if category == "NORMAL" else 10):
            index += 1
            payment_id = f"BEN-PAY-{index:03d}"
            records = [_record("payment", index, payment_id, "100.00")]
            route: str | None = None
            if category == "NORMAL":
                records.append(_record("settlement", index, payment_id, "100.00"))
            elif category == "SETTLEMENT_MISMATCH":
                records.extend([_record("fee", index, payment_id, "5.00"), _record("settlement", index, payment_id, "90.00")])
                route = "DEPARTMENT_ESCALATE"
            elif category == "REFUND_MISMATCH":
                records.extend([_record("refund_request", index, payment_id, "20.00", requested_amount="20.00"), _record("refund", index, payment_id, "10.00", status="COMPLETED"), _record("settlement", index, payment_id, "90.00")])
                route = "DEPARTMENT_ESCALATE"
            elif category == "FEE_DISCREPANCY":
                records[0]["expected_fee_amount"] = "5.00"
                records.extend([_record("fee", index, payment_id, "7.00"), _record("settlement", index, payment_id, "93.00")])
                route = "DEPARTMENT_ESCALATE"
            elif category == "DUPLICATE_TRANSACTION":
                records.append(_record("payment", index, payment_id, "100.00", ordinal=2))
                records.append(_record("settlement", index, payment_id, "200.00"))
                route = "DEPARTMENT_ESCALATE"
            elif category == "MISSING_SETTLEMENT":
                route = "DEPARTMENT_ESCALATE"
            elif category == "BANK_MISMATCH":
                records.extend([_record("settlement", index, payment_id, "100.00"), _record("bank", index, payment_id, "90.00")])
                route = "DEPARTMENT_ESCALATE"
            elif category == "TIMING_EXCEPTION":
                records.append(_record("settlement", index, payment_id, "100.00", occurred_at="2026-09-12"))
                route = "DEPARTMENT_ESCALATE"
            elif category == "SUSPICIOUS_ACTIVITY":
                records[0]["suspicious_signal"] = True
                records.append(_record("settlement", index, payment_id, "100.00"))
                route = "FRAUD_ESCALATE"
            scenario_id = f"SCN-{index:03d}"
            scenarios.append({"scenario_id": scenario_id, "category": category, "records": records})
            truth.append({"scenario_id": scenario_id, "payment_id": payment_id, "expected_exception": None if category == "NORMAL" else category, "expected_route": route})
    return scenarios, truth
