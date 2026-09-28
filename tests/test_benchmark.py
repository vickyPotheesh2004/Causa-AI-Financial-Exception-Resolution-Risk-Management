import unittest

from cause_ai.benchmark.generator import SEED, generate
from cause_ai.benchmark.evaluator import evaluate


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_has_exactly_100_reproducible_scenarios(self):
        scenarios, truth = generate()
        self.assertEqual(SEED, 20260928)
        self.assertEqual(len(scenarios), 100)
        self.assertEqual(len(truth), 100)
        self.assertEqual([item["scenario_id"] for item in scenarios], [item["scenario_id"] for item in generate()[0]])

    def test_evaluator_returns_measured_metrics_and_unresolved_ids(self):
        scenarios, truth = generate()
        result = evaluate(scenarios, truth)
        self.assertEqual(result["records_processed"], 100)
        self.assertEqual(result["exceptions_expected"], 80)
        self.assertIn("precision", result)
        self.assertIn("unresolved_ids", result)
        self.assertEqual(result["ai_investigations"], 0)
