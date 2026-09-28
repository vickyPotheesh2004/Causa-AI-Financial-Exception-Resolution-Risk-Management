# HTTP API

Base URL: `http://127.0.0.1:8000`. All API payloads and responses use UTF-8 JSON. The local server sets `HttpOnly`, `SameSite=Strict`, eight-hour session cookies, same-origin checks for POST requests, security headers, and generic server-error responses. Detection timing defaults to a seven-day synthetic demo window; configure it only after adopting an approved business rule.

## Session and health

| Method | Route | Authentication | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | Public | Local process health; reports synthetic-demo mode and SQLite. |
| `POST` | `/api/login` | Public | Body: `{"username":"analyst","password":"…"}`. Sets session cookie. |
| `GET` | `/api/session` | Required | Current username, role, and demo-mode flag. |
| `POST` | `/api/logout` | Required | Invalidates current in-memory session and clears cookie. |

## Cases, decisions, tickets, and audit

| Method | Route | Role | Purpose |
|---|---|---|---|
| `GET` | `/api/dashboard` | Any signed-in demo role | Case/ticket counts and synthetic records. |
| `GET` | `/api/cases` | Any signed-in demo role | Case list. Optional exact filters: `status`, `type`, `department`, `priority`, `risk`; `q` searches case text. |
| `POST` | `/api/detection/preview` | Analyst or admin | Body: `{"schema_version":"1.0|1.1","records":[…],"timing_window_days":7}`. Analyzes normalized records and returns source-linked findings without saving them. |
| `POST` | `/api/detection/commit` | Analyst or admin | Same body as preview. Persists findings, automatically runs deterministic policy/risk/decision checks, creates an evidence-rich department ticket for escalations, and audits the result in one transaction. Send an `Idempotency-Key` for request retries. A new key represents a new report and enables repeat-request correlation. |
| `GET` | `/api/cases/{case_id}` | Any signed-in demo role | Case detail, evidence, policy, risk, tickets, related audit events, and linked prior report snapshots for repeat requests. |
| `POST` | `/api/cases/{case_id}/evaluate` | Analyst or admin | Runs deterministic demo rule, risk, and decision evaluation. Include an `Idempotency-Key` header. No payment action executes. |
| `GET` | `/api/tickets` | Any signed-in demo role | Ticket list. |
| `POST` | `/api/tickets/{ticket_id}/respond` | Department or admin | Body: `{"comment":"A concise finding with next steps."}`. Comment length: 5–2,000 characters. |
| `POST` | `/api/tickets/{ticket_id}/resolve` | Department or admin | Body: `{"resolution":"Resolution explanation at least 15 characters.","evidence_ids":["EV-…"]}`. Every cited item must be verified evidence on the case. |
| `POST` | `/api/tickets/{ticket_id}/verify` | Analyst or admin | Runs a demo consistency check of recorded resolution and cited evidence. Passing verification closes the case and ticket. |
| `POST` | `/api/reminders/run` | Analyst or admin | Records one in-app synthetic reminder for each overdue active ticket that has not received one during the last 24 hours. |
| `GET` | `/api/audit?limit=100` | Any signed-in demo role | Latest tenant-demo audit records; limit is clamped to 1–500. |

## Regulatory update discovery and review

The local monitor checks allowlisted official NPCI UPI circular and RBI payment-system notification indexes. It downloads matching linked publications with size and redirect limits, saves content-addressed copies under `data/regulatory/objects`, and records SHA-256 hashes. A source with no parseable static circular links reports `PARSER_LIMITED`; an empty-looking result is not treated as healthy coverage. The current NPCI page renders its circular list dynamically, so the monitor explicitly reports that it cannot verify complete UPI coverage until a supported official feed/API is configured. The monitor does not extract legal terms, determine entity applicability, or activate policy. Review dispositions are `NEEDS_LEGAL_REVIEW`, `RELEVANT`, and `NOT_APPLICABLE`; a reviewer rationale is required and each action is audited. Before any review is recorded, the server re-hashes the staged object in bounded-memory chunks and requires an exact SHA-256 match, an in-store content-addressed path, and a regular non-symlink file. Missing, altered, unreadable, or out-of-store objects fail closed with HTTP 409. Inbox reads do not hash every stored object; this keeps the review list bounded. An item routed to legal review can later receive a final disposition, with the same integrity check.

Normalized-record contract `1.0` accepts the financial fields only. Contract `1.1` adds optional `subject_type` (`USER` or `COMPANY`), `subject_id`, and `email_id`. Identity fields must be consistent across one submitted record bundle. They are caller-supplied, unverified identifiers in this demo and must not be treated as authoritative identity proof. Repeat reports correlate on subject type plus a matching subject ID or supplied email, payment ID, and exception type. Prior case IDs, statuses, outcomes, report counts, and evidence references are retained in the case history and escalation ticket. A repeated report is escalated for human review.

Without an idempotency header, an identical bundle from the same actor is treated as a retry. With a header, repeating the same key and same request returns the original result; using the same key with a different payload returns 409. A deliberate re-report uses a new key. Every committed unverified input automatically escalates because its evidence and authority cannot satisfy auto-approval guards. `AUTO_APPROVE` requires verified evidence, no conflict, passing policy, known authority, permitted and idempotent action, low configured risk, and completed reconciliation. Approval records a governed outcome only; this app does not execute payments or refunds. Possible fraud is routed to Risk/Fraud for specialist investigation; the system does not automatically label a person or company as a fraudster. A clear policy failure is rejected only after the evidence, authority, and input integrity gates pass.

Contract `1.1` retains the `1.0` financial fields: `record_type`, `record_id`, `payment_id`, `currency`, `amount`, `occurred_at`, `status`, and boolean `suspicious_signal`; `payment` may add `expected_fee_amount` and non-negative integer `refund_attempt_count`, while `refund_request` may add `requested_amount`. Unknown fields are rejected. Unsupported record types become `UNKNOWN_EXCEPTION` findings. Currency shape, IDs, signal types, attempt counts, identities, and decimal financial calculations are validated before decisions.

| Method | Route | Role | Purpose |
|---|---|---|---|
| `GET` | `/api/regulatory/inbox` | Admin | Read source freshness/errors, captured publications, hashes, and review states. |
| `POST` | `/api/regulatory/scan` | Admin | Trigger a bounded scan of the configured official indexes. |
| `POST` | `/api/regulatory/documents/{id}/review` | Admin | Body: `{"verdict":"NEEDS_LEGAL_REVIEW","reason":"Applicability rationale of at least 15 characters"}`. This records review only; it cannot activate policy. |

The optional background monitor runs every six hours by default (minimum 15 minutes); set `CAUSE_AI_REGULATORY_MONITOR=false` to disable it or `REGULATORY_SCAN_INTERVAL_SECONDS` to change the interval. This is a single-process development scheduler, not a durable or highly available production worker. Failed scans are visible in source status and are retried at the next interval; no dedicated DLQ or alert delivery exists.

## Error response

Errors use a stable envelope:

```json
{"error":{"code":"FORBIDDEN","message":"Department or admin role is required"}}
```

Common HTTP codes are 400 validation, 401 unauthenticated, 403 forbidden or invalid origin, 404 missing route/resource, 409 invalid state, 413 oversized request, and 429 login rate limit. Unexpected internal errors are logged server-side and return a generic 500 message.

## Role and trust boundaries

API authorization is enforced in the backend, not only in the browser. The local demo accounts each carry a stored `tenant_id`; the server puts that trusted demo account value into the in-memory session, and case, ticket, audit, reminder, and detection-correlation operations scope to it. Adversarial tests cover cross-tenant HTTP visibility and service mutations. This is a repository-level isolation foundation, not production identity or database-enforced security: accounts/passwords are fixed demo fixtures, session state is process-local, and SQLite has no row-level security. The HTTP server remains local-development only and is not a production deployment target.
