# Causa deterministic benchmark

Run `python -m cause_ai.benchmark.runner` with `PYTHONPATH=src` to regenerate the 100 synthetic scenarios, immutable ground truth, and `reports/benchmark_results.json`.

The benchmark never calls OpenRouter. It evaluates deterministic exception detection only. Metrics are generated at run time and must not be manually edited.
