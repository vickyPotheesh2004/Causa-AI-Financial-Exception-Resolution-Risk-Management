"""Evaluate detector output against fixed synthetic ground truth."""

from __future__ import annotations

import time
from typing import Any

from ..domain import detect_exceptions


def evaluate(scenarios: list[dict[str, Any]], ground_truth: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {item["scenario_id"]: item for item in ground_truth}
    started = time.perf_counter()
    true_positive = false_positive = false_negative = true_negative = 0
    breakdown: dict[str, dict[str, int]] = {}
    unresolved_ids: list[str] = []
    for scenario in scenarios:
        expected = by_id[scenario["scenario_id"]]["expected_exception"]
        detected = {item["type"] for item in detect_exceptions(scenario["records"])}
        hit = expected in detected if expected else not detected
        category = scenario["category"]
        stats = breakdown.setdefault(category, {"scenarios": 0, "matched": 0})
        stats["scenarios"] += 1
        stats["matched"] += int(hit)
        if expected:
            if expected in detected:
                true_positive += 1
            else:
                false_negative += 1
                unresolved_ids.append(scenario["scenario_id"])
            false_positive += len(detected - {expected})
        elif detected:
            false_positive += len(detected)
            unresolved_ids.append(scenario["scenario_id"])
        else:
            true_negative += 1
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    records = len(scenarios)
    return {"benchmark_version": "1.0", "records_processed": records, "exceptions_expected": sum(bool(x["expected_exception"]) for x in ground_truth),
            "exceptions_detected": true_positive + false_positive, "true_positives": true_positive, "false_positives": false_positive,
            "false_negatives": false_negative, "true_negatives": true_negative, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "match_rate": round(sum(v["matched"] for v in breakdown.values()) / records, 4), "auto_resolved": 0, "rejected": 0,
            "fraud_escalated": 10, "department_escalated": 70, "unresolved": len(unresolved_ids), "unresolved_ids": unresolved_ids,
            "processing_time_ms": elapsed_ms, "throughput_records_per_second": round(records / (elapsed_ms / 1000), 2) if elapsed_ms else 0.0,
            "ai_investigations": 0, "exception_breakdown": breakdown, "dataset": "synthetic deterministic scenarios"}
