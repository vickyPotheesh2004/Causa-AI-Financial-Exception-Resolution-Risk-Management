# Implementation status and audit limits

## Current status

A local synthetic-data prototype exists. It includes a browser dashboard, searchable exception queue and detail view, a deterministic detector for ten exception classes over normalized JSON bundles, preview and idempotent commit, automatic governed decisions at commit, evidence-rich escalation tickets, repeat-report links/history, deterministic demo risk and policy evaluations, four decision outcomes, role-gated ticket handling, append-only SQLite audit events, on-demand overdue reminders, resolution submission, and demo verification after valid evidence citations. Auto-approval requires verified evidence, a passing rule, known authority, permitted and idempotent action, low risk, and reconciled financial state. Suspicious activity routes to specialist investigation without confirming fraud. No money movement is implemented.

## AI usage in the current build

No generative AI, machine-learning model, or external AI provider is called by the current application. Exception detection, risk scoring, policy checks, and outcomes are deterministic code; the “AI” product name does not mean a model is currently involved. The planned production AI is limited to evidence-grounded case summarization and advisory extraction of candidate regulatory clauses/amounts with source citations. It must go through a redacting, schema-validating gateway and remain advisory until a human reviewer approves any change. That gateway and those model behaviors are not implemented.

## Implemented and locally verified

| Area | Evidence |
|---|---|
| Runtime exposure guard | `server.py:serve` rejects unsupported environment profiles and any non-loopback bind before database initialization. Runtime safety tests cover both failures. This is an accident-prevention control only; it does not implement production mode or certify the demo safe for real data. |
| Decimal-safe money parsing and settlement arithmetic | Unit tests cover settlement math, rounding, invalid/non-finite values, precision overflow, and currency checks. |
| Decision guards | Unit tests cover all outcomes and blockers for missing/unverified/conflicting evidence, policy failure, risk, permissions, unknown conversion, and suspicious activity. |
| Persistence and audit | SQLite schema enables foreign keys; audit update/delete triggers reject mutation; service tests cover repeat requests and event history. |
| Roles and sessions | HTTP tests cover login, invalid credentials, unauthenticated requests, analyst vs department permissions, and same-origin checks. |
| Department lifecycle | Service test covers evaluation → ticket → response → evidence-cited resolution → independent demo consistency check → closure. |
| Reminders | Tests cover overdue scheduling, 24-hour duplicate suppression, and role authorization. |
| Detection workflow | Unit and HTTP tests cover the ten exception classes, strict schema 1.0/1.1 input, preview, role permissions, unverified identity/evidence, atomic decision/ticket creation, same-key replay, and changed-payload conflict. |
| Local tenant boundary foundation | The local user row has tenant assignment; the server session derives it from the authenticated account; API/service case, ticket, audit, repeat-correlation, and reminder operations apply tenant filters. Adversarial service and HTTP tests pass. PostgreSQL row-level security and production identity mapping are not implemented. |
| Automated outcomes and escalation | Detection commit runs deterministic decision controls and records one outcome; escalations create tickets with finding, evidence, risk, policy, requested action, and prior-case context. Service tests exercise ordinary and possible-fraud routing. |
| Repeat-report history | Same supplied user/company ID or email, payment ID, and issue type links prior report IDs/status/outcomes, increments count, records append-only correlation audits, and routes the repeat for review. Caller-provided identity remains unverified. |
| Auto-approval safety | Verified evidence, passing policy, authority, permission, idempotent action, low risk, and explicit `RECONCILED` state are required; the seeded shortfall remains blocked. Approval records an outcome; there is no action execution. |
| Risk signal input | Suspicious-signal fields must be JSON booleans; string values are rejected and cannot be treated as true by truthiness. |
| Normalized input contract | Detection accepts schema 1.0 and 1.1; version 1.1 adds optional consistent subject type/ID/email fields. Typed field allowlists reject unknown columns and malformed currency/signal/count/identity data. |
| Live regulatory source audit | The app was run against both configured official sites. RBI source discovery staged individual notification pages. NPCI's UPI page renders circular cards dynamically; the standard-library source parser cannot enumerate the current circular PDFs and reports `PARSER_LIMITED`. UPI update coverage is therefore not complete pending a supported API/feed connector. |
| Current persisted regulatory-source check | Read-only audit of the running local service's database found its latest automatic check at `2026-09-25T14:44:39Z`: RBI PSS `OK` with no newly changed documents; NPCI UPI `PARSER_LIMITED`. Existing content-addressed RBI captures include `Digital Payments – E-mandate Framework, 2026` (21 Apr 2026; official circular PDF reference retained) and `Master Directions on Authorisation to operate a Payment System` (15 Jun 2026; official circular PDF reference retained), each stored with SHA-256. A live browser visit to the [NPCI UPI circular listing](https://www.npci.org.in/circulars/upi) displayed FY 2026–27 entries including OC 237, OC 186A, and OC 227A, while the backend HTTP parser still receives an index shell with no PDF links. Opening OC 186A's view action revealed a direct official PDF URL, confirming the data is available in the rendered browser but not to the current background collector. |
| Regulatory publication discovery | A bounded background/manual monitor checks allowlisted NPCI UPI and RBI PSS indexes, hashes and stores linked publications, filters generic indexes, canonicalizes HTML for duplicate detection, and exposes an admin-only review inbox. Before recording a review, the server re-hashes the object and validates its content-addressed in-store path; tampered, missing, symlinked, or out-of-store objects are rejected and the verified hash is audited. Mocked-source tests cover deduplication, hashing, allowlisting, integrity failures, review authorization, and the no-policy-activation boundary. No legal extraction or policy activation is possible. |
| Browser UI | Local browser review covered sign-in, dashboard, opening a case, evaluating and routing it, department finding and resolution, analyst verification, and final closed state. The overlapping sign-in panel visual defect found in that review was corrected. Detection preview and draft import were also verified in the browser. |
| Local documentation | Run commands, routes, demo credentials, requirements, project boundaries, and task status are documented. |
| Policy lifecycle and tool governance | Tenant-scoped policy proposals require independent review and activation, respect effective dates, resolve per tenant, and audit every transition. A controlled tool registry excludes payment and settlement actions. |
| Delivery controls | A non-root, read-only demo container, loopback-only Compose configuration, CI verification workflow, and secret-safe 12-control production preflight are included. Docker execution requires a company or developer Docker runtime. |

## Not production complete

The following parts of the original project brief are **not implemented** and must not be represented as complete:

- Real connectors or ingestion for payments, bank statements, provider fees, refunds, adjustments, or merchant source files.
- Live connectors, file import jobs, source-system reconciliation, and general raw ledger ingestion; the built-in detector requires a normalized JSON record array.
- Canonical financial event-graph generation, source-authenticated cross-report identity, robust fuzzy issue correlation, or evidence verification/update workflows. The demo only correlates exact supplied subject/payment/issue keys; detector input is normalized JSON.
- Production policy administration, policy precedence review, compliance/legal validation, and authoritative current policy ingestion.
- Production authentication, identity lifecycle, granular department assignment, database-enforced tenant isolation, or persistent sessions. Local query-scoped tenant isolation is implemented and tested, but it is not a production security boundary.
- Background workers, outbound email/Slack notifications, configurable SLA administration, reminder delivery guarantees, or escalation schedules.
- External LLM/agent workflow, structured model response validation, prompt-injection evaluation, tool sandboxing, or benchmarked model performance.
- Financial side-effect execution, provider idempotency, or verification against authoritative external system state.
- Production-grade schema migrations, backups, deployment packaging, monitoring, high availability, or audited security certification.
- Complete frontend accessibility, browser compatibility, or automated browser-driven E2E suite.
- The implemented regulatory monitor is only an official-index discovery and human-review queue. It does not classify drafts/amendments/withdrawals, extract clauses or amounts, resolve legal entity applicability, activate policy versions, send freshness alerts, or provide a durable multi-instance scheduler/DLQ. It must not be treated as automatic legal compliance.

## Audit conclusion

This is a working, locally runnable educational/demo prototype for the synthetic workflow. It is not a production financial operations system and has not been audited for production use. The tests verify the code paths named above; they do not establish legal compliance, financial correctness against live records, security certification, or performance against the requested buildathon dataset.

The production architecture, AI boundaries, and full regulatory source update lifecycle are specified in `INDUSTRY_GRADE_TARGET_DESIGN.md`; only the limited discovery and review inbox is implemented. Regulatory discovery stages official publications automatically, but applicability and activation must remain governed by authorized compliance review.

## Next implementation dependencies

1. Select and document authoritative source schemas and expected exception fixtures for real provider and bank exports.
2. Implement source-specific ingestion, durable event linking, and report correlation around the existing normalized-record detector.
3. Normalize durable domain entities and add versioned migrations and database constraints.
4. Add evidence and policy administration with change review and historical reproducibility.
5. Add tenant-aware identity and queue-level authorization before accepting non-synthetic data.
6. Connect and evaluate a bounded AI investigation service, then add adversarial and citation-grounding tests.
7. Add background job delivery and configurable SLA handling.
8. Verify resolutions against a source connector before any real-world use.


