"""Run the reproducible Causa benchmark without an AI provider."""

from __future__ import annotations

import json
from pathlib import Path

from .evaluator import evaluate
from .generator import SEED, generate

ROOT = Path(__file__).resolve().parents[3]


def run(write_files: bool = True) -> dict:
    scenarios, truth = generate()
    result = evaluate(scenarios, truth)
    result["seed"] = SEED
    if write_files:
        benchmark_dir = ROOT / "benchmarks"
        benchmark_dir.mkdir(exist_ok=True)
        (benchmark_dir / "causa_100_records.json").write_text(json.dumps({"seed": SEED, "scenarios": scenarios}, indent=2) + "\n", encoding="utf-8")
        (benchmark_dir / "ground_truth.json").write_text(json.dumps({"seed": SEED, "ground_truth": truth}, indent=2) + "\n", encoding="utf-8")
        (ROOT / "reports" / "benchmark_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
