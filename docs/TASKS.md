# Cause AI implementation task list

Tasks are checked only when their deliverable exists and acceptance evidence has been recorded. This checklist distinguishes the working local demo from the larger production-oriented brief.

> **Production status:** Cause AI is not yet suitable for company production use. The newly approved target design in `INDUSTRY_GRADE_TARGET_DESIGN.md` is a blueprint; open production controls below must be delivered and audited before live data or money-related decisions are enabled.

## Phase 0 — Scope and baseline

- [x] 0.1 Preserve the supplied project report and source specifications.
- [x] 0.2 Confirm starting workspace and verify all seven pasted specifications byte-for-byte.
- [x] 0.3 Select a standard-library Python, SQLite, and browser UI stack for the local demo; record boundaries in `docs/IMPLEMENTATION_STATUS.md`.
- [x] 0.4 Link requirements to source files and tests in `docs/TRACEABILITY.md`.

## Phase 1 — Runnable project skeleton

- [x] 1.1 Create a clean application package and project-local ignore/configuration files.
- [x] 1.2 Document reproducible setup, run, seed-on-first-start, and test commands.
- [x] 1.3 Add local health route, structured HTTP logging, safe API errors, and security headers.
- [x] 1.4 Add synthetic examples for mismatched, duplicate, missing, conflicting, suspicious, and other representative cases.

## Phase 2 — Demo domain and persistence

- [x] 2.1 Model demo cases, evidence, policies, tickets, users, idempotency keys, and audit events.
- [ ] 2.2 Normalize all financial entities, add schema migrations, and complete relational constraints. Current case/ticket details remain JSON-backed.
- [x] 2.3 Implement decimal-safe INR calculations, supported-currency validation, and input checks.
- [x] 2.4 Make audit append-only and case evaluation idempotent within a transaction.

## Phase 3 — Evidence, risk, and decisions

- [ ] 3.1 Ingest and normalize raw source records with provenance and data-quality outcomes.
- [x] 3.2 Detect all ten required exception classes from normalized source-record bundles; preview and draft-case commit are tested. Live source connectors remain open.
- [ ] 3.3 Build persistent event graph links and correlate repeated issue reports across separate inputs.
- [x] 3.3a Add demo repeat-report correlation for schema 1.1 by supplied subject ID/email, payment ID, and issue type; persist linked prior case snapshots, report counts, department escalation, and append-only audit references. Acceptance: replay uses the same idempotency key without duplicate side effects; a new key records a repeat with prior status and ticket investigation context. Tests: `test_detection_automatically_escalates_and_links_repeat_request_history`.
- [x] 3.4 Record source IDs, authority labels, timestamps, and unverified/verified/conflicting states; imported evidence is safely marked unverified. Evidence update UI remains open.
- [ ] 3.5 Build an administrable versioned policy engine with effective-date and precedence handling. Demo rules are implemented only.
- [x] 3.6 Add explainable deterministic demo risk factors and safe currency-conversion blockers.
- [x] 3.7 Implement all four demo outcomes with evidence, policy, risk, authority, permission, and escalation guards.

## Phase 4 — Ticket, reminder, and resolution lifecycle

- [ ] 4.1 Make department routing configurable by policy and maintainers. Current demo queues are fixture values.
- [x] 4.2 Enforce valid ticket transitions and record attributed audit events.
- [ ] 4.3 Implement a background scheduler, delivery retries, configurable SLAs, and escalation rules. Manual in-app reminder recording is implemented.
- [x] 4.4 Preserve department comments alongside earlier case and AI fields; demo AI findings are not generated.
- [ ] 4.5 Verify submitted outcomes against authoritative records and implement evidence update/reopen flows. Current check is local demo consistency only.

## Phase 5 — User interface and API

- [x] 5.1 Create dashboard and searchable/filterable exception queue.
- [x] 5.2 Create case evidence, timeline, risk, policy, decision, ticket, and audit workspace.
- [x] 5.3 Create department response and resolution workflow in the shared case workspace.
- [x] 5.4 Document and implement the local JSON API routes in `docs/API.md`.
- [x] 5.5 Add sign-in, empty/error states, role-specific actions, and responsive layout; review the rendered browser workflow.
- [ ] 5.6 Add full admin policy/user/queue/SLA/report configuration screens.

## Phase 6 — Automated quality and security

- [x] 6.1 Unit-test decimal math, evidence guardrails, risk, decisions, permissions, and ticket states.
- [x] 6.2 Integration-test SQLite persistence and evaluate → ticket → response → resolution → verification flow.
- [ ] 6.3 Add an automated browser E2E suite for every product journey. One workflow was manually exercised in the browser.
- [x] 6.4 Test authentication, roles, cross-origin POST rejection, audit immutability, bad inputs, and idempotency.
- [x] 6.5 Run full automated tests, Python compilation, JavaScript syntax check, and final workspace audit. Record the final evidence below.
- [x] 6.6 Perform final file-by-file review and rerun regressions after fixes.

## Phase 7 — Documentation and delivery audit

- [x] 7.1 Document exact local setup and test commands matching the current prototype.
- [x] 7.2 Keep requirements, architecture, API, tests, source material, and implementation limitations organized.
- [x] 7.3 Record final outputs and known gaps after the closing workspace audit.
- [x] 7.4 Confirm intended files, no secrets, and the correct fresh synthetic demo state.

## Phase 8 — Close verified decision and input defects

- [x] 8.1 Require explicit reconciled state before auto-approval; add a regression for the seeded settlement shortfall.
- [x] 8.2 Reject non-boolean `suspicious_signal` values so a string such as `"false"` cannot trigger fraud escalation.
- [x] 8.3 Require version `1.0` on normalized-record API bundles; validate record-type-specific allowlists, identifiers, currency shape, boolean fraud signal, and integer attempt counts; invalid monetary data remains an explicit unknown finding.
- [x] 8.4 Add regression coverage for all eight seeded cases, exact/one-cent/high discrepancy boundaries, stable replay, and the policy version used by a historical decision. Acceptance: seeded outcomes match expected guarded results; every escalation has a ticket; historical decision versions remain unchanged after later policy edits. Tests: `test_every_seeded_case_has_one_governed_outcome_and_escalations_have_tickets`, `test_settlement_discrepancy_zero_cent_and_high_boundaries`, `test_decision_keeps_the_policy_version_used_at_evaluation`.
- [x] 8.5 Run deterministic decision rules automatically in the detection commit transaction; record APPROVED/REJECTED/ESCALATED and create a department investigation ticket with evidence, policy, risk, and related-case context when escalation is required. Acceptance: every committed finding has exactly one governed outcome and required escalation/ticket/audit rows commit atomically. Tests: automated escalation, fraud routing, repeat linking, domain outcome-boundary tests.
- [x] 8.6 Add optional versioned user/company/email identity metadata with consistency validation, explicit UNVERIFIED status, same-key idempotency conflict checks, and previous-case history in the investigation workspace. Acceptance: identities are never invented, conflicting identity bundles reject validation, and repeat reports retain previous IDs/status/outcome. Tests: schema version and identity validation plus repeat-report service workflow.
- [x] 8.7 Route possible suspicious/fraud signals directly to the Risk/Fraud queue without declaring a person/entity fraudulent; reject only evidence-supported explicit policy failures after evidence and authority gates. Acceptance: suspicious-signal import yields FRAUD_ESCALATE and an investigation ticket; no automatic fraud label is written. Tests: fraud escalation boundary and clear policy failure case.
- [ ] 8.8 Replace caller-supplied identity with authenticated provider/customer identity and tenant-scoped authorization before any real PII or cross-report correlation is enabled.

## Phase 9 — Risk, policy, and regulatory control plane

- [ ] 9.1 Define entity-role and product applicability with counsel/compliance; identify the first target customer profile.
- [ ] 9.2 Implement source registry, official-source polling, immutable document capture, checksums, freshness alerts, retries, and dead-letter handling.
- [x] 9.2a Implement initial allowlisted NPCI/RBI source registry, bounded polling, content-addressed capture with SHA-256, admin review inbox, append-only review audit, and mocked tests. Production retries, alerting, durable workers, and DLQ remain open under 9.2.
- [x] 9.2b Verify staged publication bytes, SHA-256, and content-addressed in-store path before recording any review; reject missing, modified, unreadable, symlinked, or out-of-store content. Acceptance: bad bytes/paths remain unreviewed, every review audit references the checked hash, and inbox reads do not perform unbounded whole-corpus hashing. Tests: `test_regulatory_review_fails_closed_on_changed_missing_or_out_of_store_content`, `test_regulatory_review_is_authorized_audited_and_never_activates_policy`.
- [x] 9.2c Reject an official-source redirect before the HTTP client follows it if the destination leaves the RBI/NPCI HTTPS allowlist. Acceptance: a relative official-host redirect remains permitted; an untrusted or local-network redirect raises before any request to that destination. Test: `test_regulatory_redirect_is_rejected_before_following_untrusted_host`.
- [ ] 9.3 Implement draft/final/withdrawn classification, amendment linking, page-cited extraction, and applicability review.
- [ ] 9.4 Implement policy rule versioning, effective dates, tenant/product/rail/category scope, dual approval, regression replay, activation, rollback, and kill switch.
- [ ] 9.5 Keep AI clause extraction advisory only; validate outputs against a strict schema and require a compliance owner to approve applicability and activation.
- [ ] 9.6 Replace the single score with explainable financial, fraud, operational, compliance, and customer-impact dimensions plus history, calibration, drift monitoring, and threshold governance.
- [ ] 9.7 Add benchmark datasets and report precision, recall, false-positive cost, coverage, and throughput by risk segment.

## Phase 10 — Production data plane and security

- [ ] 10.1 Replace SQLite/JSON source of truth with PostgreSQL relational models, migrations, constraints, transaction outbox, and point-in-time recovery.
- [ ] 10.2 Complete production tenant isolation with PostgreSQL row-level controls, trusted identity-to-tenant mapping, and independent adversarial coverage.
- [x] 10.2a Add tenant assignment to stored local users; derive tenant from the authenticated server session; scope case, ticket, audit, detection correlation, and reminder access; add migration and adversarial cross-tenant regressions. Acceptance: a second tenant cannot list, retrieve, mutate, or see another tenant's cases, tickets, or audit rows, and both new and v1 databases report schema version 2. Verified by `test_tenant_isolation_covers_dashboard_cases_tickets_audit_and_ticket_mutations`, `test_http_tenant_is_taken_from_authenticated_user_and_scopes_all_case_routes`, `test_existing_v1_user_schema_migrates_to_demo_tenant`, and `test_fresh_database_records_current_schema_version`. This closes only the repository's local query/session foundation; it does not complete production identity, database RLS, or independent security assurance.
- [ ] 10.3 Add enterprise OIDC/SSO, MFA, scoped roles/attributes, department assignment, provisioning/deprovisioning, key rotation, and audited admin controls.
- [ ] 10.4 Build validated provider/bank/merchant ingestion adapters with reconciliation, replay, idempotency, PII minimization, and source-health monitoring.
- [ ] 10.5 Add authoritative resolution verification, evidence lifecycle/verification UI, corrections/reopen, and bounded authorization for any external action.
- [ ] 10.6 Add durable event workers, retry/DLQ, configurable SLA schedules and notifications, back-pressure, and operation runbooks.
- [ ] 10.7 Complete threat modeling, privacy impact review, penetration testing, accessibility review, disaster recovery, load testing, and security sign-off.

## Phase 11 — Governed AI and scalable release

- [ ] 11.1 Add an AI gateway with provider isolation, model inventory, redaction, schema validation, citations, budgets, timeouts, and audit lineage.
- [ ] 11.2 Add evidence-grounded investigation/planning and adversarial prompt-injection tests; prevent models from changing policies or taking money actions.
- [ ] 11.3 Validate any predictive risk models through model-risk governance, calibration, fairness/drift testing, and shadow rollout.
- [ ] 11.4 Deploy stateless API and worker tiers with tenant quotas, observability, SLOs, backup/restore, regional recovery, CI/CD, SBOM, signed artifacts, and staged rollout.
- [ ] 11.5 Add automated browser E2E, contract, integration, resilience, security, performance, and historical regulatory replay suites.
- [ ] 11.6 Complete launch gates and customer acceptance against the selected legal/business role and operational profile.

## Final verification record — 2026-09-25

- `python -m compileall -q src tests`: passed.
- `python -m unittest discover -s tests -v`: 61 tests passed after seeded-decision, policy-history, discrepancy-boundary, regulatory-object integrity, official-source redirect, and cross-tenant service/HTTP regressions (all domain, service, and HTTP tests).
- `node --check src/cause_ai/static/app.js`: passed.
- Browser workflow: signed in, previewed a normalized settlement mismatch, imported one draft, confirmed it appeared in the queue with unverified evidence; demo database was then restored to 8 seeded cases.
- HTTP tests include login/role authorization, CSRF origin check, static path traversal, health/static delivery, detection preview and commit, idempotency, audit append-only behavior, and ticket lifecycle.
- Source review: no inline style attributes in client code; no TODO/FIXME/NotImplemented markers in application source. Only style= match is the regression assertion that forbids it.
- Runtime endpoint: `http://127.0.0.1:8000` (local-only). Demo credentials are documented in the README.
- Phase 8 auto-approval reconciliation guard, strict suspicious-signal typing, and versioned/typed normalized-record input contract are implemented and tested.
- No AI model is currently called. Detection, risk, and decisions are deterministic; the governed AI tasks in Phase 11 remain open and must not be described as deployed.
- Initial official-source regulatory discovery, content-addressed raw content plus SHA-256, normalized HTML duplicate fingerprint, admin review queue, review audit, and no-policy-activation boundary are implemented and tested with mocked source content.
- Live source audit confirms the RBI notification index returns individual notification links. NPCI’s official UPI circular page renders its circular list dynamically and exposes no candidate links to this standard-library HTTP parser; the app now flags `PARSER_LIMITED` instead of claiming healthy coverage. An approved NPCI feed/API or maintained connector is still required for complete live UPI coverage.
- Remaining: production integrations, complete regulatory-source coverage and approved policy activation, tenant-aware authentication, source-specific ingestion, persistent normalized entities/migrations, evidence verification UI, policy administration, external AI, background notifications, authoritative financial verification, and automated browser E2E are not implemented.

These checks establish a working local synthetic demo, not production financial, legal, or security assurance.

## Phase 12 — Prevent accidental production exposure

- [x] 12.1 Refuse unsupported runtime profiles and non-loopback demo binding. Acceptance: startup fails before database initialization when `CAUSE_AI_ENV` is not `demo` or host is not loopback. Tests: `RuntimeSafetyTests.test_server_refuses_production_profile_until_controls_exist`, `RuntimeSafetyTests.test_demo_server_refuses_non_loopback_binding`.
- [x] 12.2 Repeat full code verification after tenant-scoping, regulatory redirect, and cross-tenant regressions. Evidence: 61 tests passed; Python compilation, browser JavaScript syntax check, and `git diff --check` passed.
- [ ] 12.3 Build and independently certify a production deployment. Blocked by all production work in phases 2–11 plus selection/access to the actual identity, cloud, database, payment/bank/provider systems, legal entity role, and operational owners. Runtime blocking is a safety control, not a production implementation.
- [x] 12.4 Reload the local server on port 8000 so it loads the latest Python code. The old PID 9604 was stopped and PID 18868 started at 2026-09-26 00:50:22. Live health, login, session, and dashboard checks passed; login/session now expose the stored `tenant_id` and the dashboard returned 9 cases and 5 open tickets. The process remains loopback-only and demo-only.
- [x] 12.5 Back up and migrate the local SQLite database to schema v2. A SQLite online backup was stored under `data/backups/`; user tenant assignments are `DEMO-MERCHANT-01`; verification found 9 cases, 5 tickets, and 20 regulatory documents preserved. Health/login/dashboard checks returned HTTP 200 after migration, and the later server reload exposed tenant-scoped sessions.
- [ ] 12.6 Provision and certify the real production dependencies. Evidence checked 26 September 2026: no PostgreSQL client/server/container runtime or port 5432 listener exists; no database, OIDC/SAML, payment-provider, bank, or UPI connector configuration is present. This blocks PostgreSQL/RLS migration, enterprise authentication, real-data ingestion/reconciliation, and production deployment verification. It requires authorized environments and accountable owners; it cannot be satisfied by synthetic records or local code alone.

## Automated decision and repeat-report verification — 2026-09-25

- Detection commit now evaluates each finding in the same database transaction using deterministic evidence, configured demo policy, risk, authority, permission, idempotency, and reconciliation gates.
- Unverified imported data automatically receives a department or Risk/Fraud escalation and a ticket containing its investigation findings, evidence references, policy, risk, decision reason, requested action, and any prior-case snapshots.
- A v1.1 record bundle may carry optional subject type, ID, and email. These caller-supplied identities are explicitly marked unverified; they are not identity proof. Repeats link on same subject ID or supplied email, payment ID, and exception type.
- Stable request idempotency keys prevent network retries from creating duplicate cases. A deliberate repeat submission must use a new key; key reuse with changed input returns HTTP 409.
- A fraud signal results in specialist investigation, not an automatic fraud classification. A clear configured policy failure is rejected only after evidence/authority blockers are clear. AUTO_APPROVE requires all tested gates, including idempotent action and completed reconciliation, and does not execute a payment action.
- This behavior is implemented within the local SQLite/JSON demo. Authenticated identities, source-authoritative evidence, production policies, human due-process case handling, tenant controls, and real external actions remain disabled and pending.
