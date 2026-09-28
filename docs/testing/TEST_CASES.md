# Verification test cases

This catalog contains both implemented local acceptance cases and planned production cases. Implemented tests use synthetic fixtures only. Unimplemented cases remain product requirements, not evidence of current behavior.

## Implemented automated coverage — 2026-09-25

| Coverage | Verification |
|---|---|
| Decimal settlement and currency calculations | Unit tests cover calculation, rounding, invalid/non-finite values, unsupported currency, and precision limits. |
| Exception detection | Unit tests cover the configured exception classes, source references, malformed amounts, dates, duplicate IDs, suspicious indicators, and unknown fields. |
| Decision safety | Unit tests cover all decision outcomes, evidence and policy blockers, risk escalation, permission gates, unknown conversions, every seeded case, one-cent/exact/high discrepancy boundaries, historical policy-version snapshots, and the unresolved seeded shortfall regression. |
| Case and ticket lifecycle | Service tests cover evaluation, idempotency, response, evidence-cited resolution, verification, and closure. |
| Security/API boundaries | HTTP tests cover authentication, role denial, cross-origin rejection, path traversal, input versioning, payload validation, and append-only audit controls. |
| Regulatory discovery/review | Mock-source tests cover official host allowlisting and pre-follow redirect rejection, bounded source failure reporting, PDF capture/hash, HTML canonical deduplication, dynamic NPCI parser limitation, admin-only review, audit trail, and no policy activation. |
| Regulatory evidence integrity | Review tests tamper with staged bytes and try missing/out-of-store paths; all are rejected with HTTP 409. Valid content is re-hashed before the reviewer decision and audit row are committed. Inbox metadata never exposes the stored filesystem path. |
| Browser workflow | Manual in-app verification covers admin inbox rendering, source status/error visibility, sign-in, and a non-persisting normalized settlement preview. No automated browser E2E suite exists. |

Final run: `python -m unittest discover -s tests -v` — 61 tests passed. Python compile and Node JavaScript syntax checks passed. Local tenant visibility, ticket mutation, repeat correlation, and pre-follow regulatory redirect rejection are covered. This does not satisfy planned connectors, SSO, PostgreSQL row-level tenant controls, AI-provider, performance, or production E2E cases below.

## Test case format

Each case states setup, action, and expected result. Automated coverage should include unit tests for deterministic logic, integration tests across services, API authorization tests, AI/tool contract tests, and end-to-end user journeys.

## Detection and data integrity

| ID | Scenario and setup | Action | Expected result |
|---|---|---|---|
| DET-01 | Captured payment 10,000; fee 250; expected settlement 9,750; settlement 9,500. | Run detector. | Settlement mismatch of 250 is created with calculation inputs and source links. |
| DET-02 | Same source record arrives twice with the same source identity. | Ingest both copies. | One canonical record remains; duplicate ingestion is recorded or safely ignored. |
| DET-03 | Record has missing amount or unsupported currency. | Ingest and investigate. | Data quality fails with explicit reason; amount is not guessed and auto-approval is blocked. |
| DET-04 | Payment has no linked settlement within configured window. | Run detection. | Missing settlement exception is created only under configured timing rules. |
| DET-05 | Same supplied subject ID/email, payment, and issue are submitted under a new idempotency key. | Commit the repeat report. | New case is escalated with prior case ID/status/outcome and investigation snapshot; prior report count and links update; all writes are audited. Implemented in demo. |
| DET-06 | Reports have a different subject, payment ID, or issue type. | Commit each report. | No repeat link is created; each request retains its own identity history. Identity supplied by source remains explicitly unverified. |
| DET-07 | Records contain invalid timestamps, orphan references, or conflicting statuses. | Run data quality checks. | Each defect is visible and traceable; affected decisions are held from unsafe automation. |

## Evidence, investigation, and policy

| ID | Scenario and setup | Action | Expected result |
|---|---|---|---|
| EVD-01 | Authoritative payment source confirms a captured payment. | Ask investigator for payment status. | Finding cites source ID and timestamp; no unsupported detail is added. |
| EVD-02 | Required settlement record is absent. | Ask investigator for root cause. | Root cause is UNKNOWN or DATA_INSUFFICIENT; no plausible explanation is fabricated. |
| EVD-03 | Bank and settlement records conflict. | Evaluate evidence. | Conflict is explicit, both sources are retained, and auto-resolution is blocked. |
| EVD-04 | AI returns a fact with an unknown evidence ID. | Validate structured finding. | Finding is rejected or quarantined; no decision uses the invalid citation. |
| EVD-05 | Retrieved text contains instructions to bypass controls. | Process as untrusted source content. | Text is treated as data; permissions, tools, and policy remain unchanged. |
| POL-01 | Two policy versions have different effective dates. | Evaluate cases before and after the change. | Each case uses the version effective at its relevant decision time; version and source are recorded. |
| POL-02 | No applicable policy can be retrieved. | Evaluate decision. | Result is POLICY_UNAVAILABLE and outcome escalates; no rule is invented. |
| POL-03 | Two applicable rules conflict. | Evaluate decision. | Result is CONFLICT; precedence or owner resolution is required before auto-action. |
| POL-04 | Request clearly violates a sourced, applicable rule. | Evaluate decision. | REJECT includes failed rule, version, evidence, source, and reason. |

## Risk, decisions, and permissions

| ID | Scenario and setup | Action | Expected result |
|---|---|---|---|
| RSK-01 | Large discrepancy plus repeated unresolved reports. | Calculate risk. | Explainable factors raise configured dimensions and each factor has provenance. |
| RSK-02 | Low risk score but evidence is incomplete. | Evaluate outcome. | No auto-approval; incomplete evidence causes escalation or a safe hold. |
| DEC-01 | Complete verified evidence, passing rules, reconciled calculation, known authority, permitted and idempotent low-risk action, and no conflicts. | Evaluate decision. | AUTO_APPROVE is eligible; local demo records approval only and has no execution integration. |
| DEC-02 | Clearly prohibited request with sufficient supporting evidence. | Evaluate decision. | REJECT is returned with sourced explanation; it is not used for generic errors. |
| DEC-03 | Suspicious indicators exist but fraud is unconfirmed. | Evaluate decision or commit detection. | FRAUD_ESCALATE creates/uses the Risk/Fraud queue and requests investigation; it does not declare confirmed fraud. |
| DEC-04 | Evidence conflict, unclear authority, high-risk review requirement, or permission limit is present. | Evaluate decision. | DEPARTMENT_ESCALATE; no consequential action executes. |
| DEC-05 | AI confidence is high but there is no supporting evidence. | Evaluate decision. | Confidence does not substitute for evidence; automatic resolution is blocked. |
| DEC-06 | User lacks required role or tenant access. | Attempt decision/action. | Server rejects access; no data leak, state change, or action occurs. |
| DEC-07 | Same financial action is submitted twice with the same idempotency key. | Submit duplicate request. | At most one effect occurs; duplicate response is stable and audited. |
| DEC-08 | Calculation crosses currency/rounding or precision boundaries. | Recompute through supported decimal rules. | Deterministic decimal result matches documented currency precision; binary floating-point drift is absent. |
| DEC-09 | Same detection request is retried with the same key; then the same key is reused with changed content. | Commit each request. | First retry returns the original result; changed input with the same key returns 409 and has no side effects. |

## Tickets, resolution, verification, audit

| ID | Scenario and setup | Action | Expected result |
|---|---|---|---|
| TKT-01 | Department escalation is required. | Create ticket. | Configured queue receives a prepared package with issue, impact, risk, evidence, rules, and requested work. |
| TKT-02 | Ticket is in CREATED state. | Attempt an illegal transition to CLOSED. | Transition is rejected and no audit history is overwritten. |
| TKT-03 | Ticket SLA becomes overdue without response. | Run reminder worker. | Reminder is sent once per configured schedule; escalation and delivery are auditable. |
| TKT-04 | Same ticket-creation request is retried. | Submit retry. | Duplicate ticket is not created when idempotency rules apply. |
| RES-01 | Department submits a resolution with supporting evidence. | Verify outcome independently. | Verification checks expected state against authoritative records before closure. |
| RES-02 | Submitted resolution does not appear in authoritative records. | Verify outcome. | Verification fails; case reopens or remains active and department is notified. |
| RES-03 | Department finding differs from earlier AI finding. | Record department finding. | Both findings, actors, times, reasons, and evidence remain visible; AI history is not overwritten. |
| AUD-01 | Any actor performs an action or transition. | Inspect audit record. | Actor, timestamp, action, target, reason, and relevant evidence/policy references are searchable. |
| AUD-02 | Caller attempts to edit or delete a prior audit event. | Attempt mutation. | Mutation is denied; correction, if permitted, is appended as a new event. |
| SRCH-01 | Search for unresolved high-risk settlement cases over a configured amount. | Submit query. | Results match backend filters, tenant boundaries, statuses, amount, and risk criteria. |

## Minimum end-to-end journeys

1. **Safe resolution:** detect mismatch → investigate → verify evidence → pass policy → low risk → validate permission → resolve → independently verify → close and audit.
2. **Invalid request:** gather evidence → identify applicable failed rule → reject with source and explanation → preserve audit event.
3. **Possible fraud:** detect anomaly → show evidence-linked risk factors → fraud escalation → specialist review → documented resolution → verification.
4. **Insufficient evidence:** identify missing records → mark unknown → department ticket → request evidence → resume investigation after response.
5. **Conflicting records:** preserve both records → block automatic action → department finding → resolve conflict → verify.
6. **Repeated issue and overdue work:** correlate reports → increase configured operational priority → create ticket → send reminders/escalation → respond and resolve.
7. **Failed verification:** record proposed resolution → fail independent check → reopen → notify owner → audit.

## Evaluation metrics

Use a documented labeled dataset and report counts, thresholds, and slices. Track exception precision and recall by type, false-positive cost, false-negative cost, decision outcome accuracy, evidence citation validity, escalation appropriateness, verification failure rate, processing throughput, and latency. Do not report a single accuracy percentage without the underlying test set definition and confusion matrix.

