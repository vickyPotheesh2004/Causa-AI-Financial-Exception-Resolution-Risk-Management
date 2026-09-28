# Code verification checklist

Use this checklist to distinguish completed local verification from outstanding production assurance. Checked items have evidence in the current local test run; unchecked items remain open.

## Before review

- [ ] Map every requirement ID to code modules, tests, and documented behavior.
- [ ] Identify entry points, dependencies, data stores, workers, external integrations, and trust boundaries.
- [ ] Confirm synthetic test fixtures contain no real payment credentials or personal financial data.
- [ ] Review changed files and generated artifacts; remove accidental secrets and unrelated files.

## Financial correctness

- [x] Monetary values use decimal-safe types and currency-aware precision (unit-tested for current supported currencies).
- [ ] Settlement, fee, refund, adjustment, and exposure calculations have boundary and property cases.
- [ ] Missing, duplicate, reversed, partial, and out-of-order records are handled explicitly.
- [x] Calculations are deterministic and explainable from recorded inputs.
- [ ] Idempotency and transaction boundaries prevent repeated financial side effects.

## AI and evidence safety

- [ ] Model output is schema-validated; invalid output cannot alter state.
- [ ] Factual claims link to existing evidence IDs and source records.
- [ ] Unknowns, conflicts, unavailable policy, and unavailable tools have explicit fail-safe paths.
- [ ] Retrieved documents and user content are treated as untrusted data, not tool instructions.
- [ ] Tools use allowlists, scoped inputs, authorization checks, and bounded results.
- [ ] AI confidence cannot bypass evidence, policy, permission, amount limits, or human approval.

## Business rules and authorization

- [ ] Policy selection honors source, jurisdiction, version, and effective dates.
- [x] Decision outcomes cover all four outcomes and current blocker conditions in the synthetic decision engine.
- [ ] Authorization is enforced on the server for every endpoint and object operation.
- [x] Local tenant isolation is tested for HTTP/service case, ticket, and audit reads; ticket mutations; and repeat correlation.
- [ ] Complete production tenant isolation with PostgreSQL row-level policies, trusted identity mapping, and independent tests covering every query, export, and background-job path.
- [x] State machines reject tested invalid ticket transitions. Concurrency resistance remains open.

## Ticketing, verification, audit

- [ ] Routing is configurable and includes complete context without unnecessary sensitive data.
- [ ] SLA/reminder scheduling handles retries, time zones, duplicate jobs, and delivery failures.
- [ ] Resolution verification reads independent authoritative state.
- [ ] Failed verification reopens or holds the case and notifies the responsible queue.
- [ ] Audit history is append-only, actor-attributed, searchable, and protected from sensitive-data leakage.

## Error handling and security

- [x] Current validation/authentication/authorization, invalid-origin, path-traversal, rate-limit, and verification failure cases are tested. Provider, AI, timeout, and production database failures remain open.
- [ ] User responses do not expose stack traces, secrets, or internal data.
- [ ] Logs include useful correlation context and exclude or mask sensitive values.
- [ ] Dependency, secret, injection, upload, XSS/CSRF where applicable, and API abuse checks are performed.
- [ ] Configuration is externalized; example configuration contains no working secrets.

## Required verification layers

- [x] Unit tests cover current deterministic calculations, rules, risk factors, decisions, permissions, transitions, reminders, and verification.
- [x] Service tests cover current detection import and decision→ticket→resolution→verification. Real ingestion and authoritative evidence→policy remain open.
- [x] HTTP tests cover current input validation, role authorization, authentication, same-origin checks, error contracts, and authenticated tenant scoping. Database-enforced production isolation remains open.
- [ ] AI tests cover malformed output, fabricated citations, prompt injection, irrelevant context, conflicts, and tool/model failures.
- [ ] End-to-end tests cover every journey in `TEST_CASES.md`.
- [ ] Static checks, type checks, migrations, dependency/security checks, and build/startup checks are run where applicable.
- [x] Full local test suite rerun after fixes; 61 tests pass. Seeded outcomes, one-cent/exact/high discrepancy values, policy-version history, runtime exposure guards, regulatory-object integrity, allowlisted redirect rejection, and adversarial tenant-boundary cases are covered. Known unimplemented areas are listed in implementation status.

## Completion record template

| Check | Command or method | Result | Evidence / notes | Date |
|---|---|---|---|---|
| Unit, service, and HTTP tests | `python -m unittest discover -s tests -v` | Passed | 61 tests, including seeded outcomes, policy history, boundary values, runtime guards, regulatory integrity/redirect rejection, and cross-tenant service/HTTP cases | 2026-09-26 |
| Python compile | `python -m compileall -q src tests` | Passed | Current source and test modules compile | 2026-09-25 |
| JavaScript syntax | `node --check src/cause_ai/static/app.js` | Passed | Current app bundle parses | 2026-09-25 |
| Browser smoke | In-app browser | Passed | Admin inbox, parser-limited source message, and non-persisting exception preview; no browser console warnings/errors observed | 2026-09-25 |
| Automated browser E2E | Not implemented | Open | Manual smoke is not a complete automated journey suite | — |
| Production security/performance audit | Not run | Open | Requires production identity, data plane, integrations, and deployment architecture | — |

