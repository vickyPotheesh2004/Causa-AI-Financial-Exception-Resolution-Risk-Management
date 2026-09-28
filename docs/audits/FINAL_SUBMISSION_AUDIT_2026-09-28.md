# Causa final submission audit

## Verified release state

- Product: Causa — AI Financial Exception Resolution and Risk Management System.
- Deployment: Vercel synthetic demonstration at `https://causa-ai-financial-exception.vercel.app`.
- Data boundary: fictional synthetic records only; no payment execution or live Razorpay customer data.
- AI boundary: OpenRouter is optional and server-side only. Invalid, unavailable, rate-limited, or unconfigured provider output falls back to deterministic investigation rules.

## Architecture and financial safety

The workflow is detect, investigate, prove, risk-assess, decide, route, resolve, verify, and audit. Evidence identifiers, deterministic risk calculation, recorded policy versions, and the decision engine control financial outcomes. AI assistance is advisory and cannot authorize money movement, change policies, modify records, or change the audit chain.

## Security controls verified in tests

The automated suite covers authentication, authorization, tenant isolation, same-origin writes, session controls, request limits, path traversal resistance, HTML escaping, immutable financial events, and the append-only audit hash chain. OpenRouter keys are read from server-side environment variables and are absent from the client bundle.

## Benchmark

`python -m cause_ai.benchmark.runner` regenerates the included benchmark using deterministic seed `20260928`. The generated dataset contains 100 scenarios: 20 normal and 80 expected exception scenarios. The current result is 80 true positives, 0 false positives, 0 false negatives, 20 true negatives, precision 1.0000, recall 1.0000, F1 1.0000, match rate 1.0000, and zero unresolved IDs. This is regression coverage for the encoded synthetic rules; it is not a performance claim for real financial data.

## Deployment verification

The live health and readiness endpoints returned `ok` and `ready`. An authenticated live benchmark run returned 100 records and zero unresolved scenarios. Vercel storage remains ephemeral, so this deployment is a demonstration and does not provide durable production persistence.

## Repository hygiene

Generated PPT builds, render folders, extraction files, node modules, and benchmark console output are excluded from Git. Final documents, source, tests, benchmarks, and generated benchmark results remain tracked.

## Known limitations

- The public deployment uses ephemeral serverless SQLite storage and in-memory sessions.
- OpenRouter free model availability can change.
- No real payment execution, customer data, or production Razorpay integration is enabled.
- A production service requires durable storage, enterprise identity, observability, secret management, legal review, and company approvals.
