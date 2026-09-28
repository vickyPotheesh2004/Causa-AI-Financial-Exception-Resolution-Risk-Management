# Cause AI implementation audit

**Audit date:** 26 September 2026  
**Build reviewed:** local synthetic-data application after automated decision and repeat-report work  
**Readiness score:** **38/100 for production launch**

## Audit conclusion

The requested decision and repeat-report workflow is implemented and verified in the local application. Each committed exception now receives one deterministic outcome in the same SQLite transaction. Escalations create department tickets with the finding, evidence references, policy result, risk factors, requested action, and any prior case snapshot. Repeat reports retain the prior case ID, status, outcome, evidence references, report count, and audit link. A transport retry with the same idempotency key has no duplicate effect; changed content under the same key returns HTTP 409.

The application is still a local synthetic-data prototype and is not ready to accept real company or customer data, make a live financial decision, or submit regulated reports. The repository's detailed remaining task register is [TASKS.md](../TASKS.md).

## Readiness score

This score measures readiness against the requested industry-grade company deployment target, not whether the local demo starts or whether these tests pass.

| Area | Score | Evidence and remaining gap |
|---|---:|---|
| Case workflow and deterministic decision controls | 15/25 | Ten exception classes, automatic commit-time decision, fail-closed evidence gates, repeat escalation, fraud specialist routing, and tickets exist. Normalized source input is still synthetic/untrusted; action execution is absent. |
| Data plane, integrations, identity, and privacy | 7/25 | Local user-to-tenant assignment and query/session scoping now have adversarial service/HTTP tests. Storage is still SQLite/JSON; no enterprise identity lifecycle, database row-level security, bank/provider connectors, verified financial identity, normalized ledger, or production retention controls. |
| Policy, risk, and regulatory governance | 6/20 | Explainable demo risk and an audited source-review inbox exist; policy administration, applicability approval, effective versions, calibration, and regulatory coverage/activation are incomplete. |
| Scalability, operations, and deployment | 2/15 | Single-process local HTTP server and periodic in-process source scan only; no durable workers, production database, HA, operational SLOs, alerting, backups, CI/CD, or disaster recovery. |
| Verification, testing, and audit evidence | 8/15 | Sixty-one automated tests include cross-tenant API/service regressions, fresh/legacy schema migration tests, pre-review regulatory object integrity, and pre-follow official-source redirect rejection. No automated browser suite, live-source integration certification, performance/load, penetration, recovery, or independent production audit. |
| **Total** | **38/100** | **Do not launch with live financial or personal data.** |

## Implemented and verified in this audit

- Contract 1.1 accepts optional `USER`/`COMPANY` identity, subject ID, and email; conflicting identities in one input bundle are rejected. These fields remain unverified and are not identity proof.
- Detection commit records one deterministic outcome and any required ticket atomically. AUTO_APPROVE requires verified evidence, no blocking conflict, passing policy, known authority, permitted and idempotent action, low risk, and explicit reconciliation.
- Possible fraud signals create `FRAUD_ESCALATE` investigations in the Risk/Fraud queue. They do not label a person or company as a fraudster. A sourced, applicable policy failure may be rejected only after evidence and authority gates pass.
- New reports with the same supplied subject ID or email, payment ID, and issue type are linked and escalated with prior case state. A deliberate re-report must use a new idempotency key; a replay must reuse its original key.
- The case page shows linked previous report IDs, states, and outcomes. The escalation ticket stores the related investigation context. Case linkage and repeat escalation are audited.
- `.\test.ps1`: **61 tests passed** after adding adversarial tenant isolation, schema-version migration, and pre-follow regulatory redirect-rejection coverage to the runtime-boundary, seeded-case, discrepancy-boundary, policy-history, and regulatory-object integrity regressions.
- Local tenant-context foundation: user rows now hold `tenant_id`; the server restores that value from the authenticated account, and case/ticket/audit/detection/reminder paths scope reads and writes to it. Adversarial service and HTTP tests verify another tenant cannot see cases, tickets, or audit rows, retrieve a case, mutate a ticket, or correlate a repeated request to a case in another tenant. Fresh and version 1 user schemas both reach schema version 2. The suite now has **61 passing tests**. This does not provide production-grade trust: authentication remains fixed demo credentials with in-memory sessions, caller-independent organization provisioning is absent, and the database is SQLite without row-level security.
- The actual local SQLite file was backed up with SQLite's online backup API and migrated from schema version 1 to 2. Post-migration inspection verified the three demo users have `DEMO-MERCHANT-01`, with 9 cases, 5 tickets, and 20 regulatory documents retained. The older local process was then replaced: PID 18868 started on 26 September 2026 at 00:50:22, loopback-only on port 8000. Live health, login, session, and dashboard checks returned HTTP 200; login/session expose the authenticated tenant and the dashboard returned 9 cases and 5 open tickets. The backup is ignored by Git under `data/backups/`.
- A fresh official-source poll on 26 September 2026 returned RBI PSS `OK` with zero newly captured documents and NPCI UPI `PARSER_LIMITED`. The NPCI static page remains an application shell; inspecting its public JavaScript identified internal circular endpoints but did not yield an authorized, stable server-side feed. The collector therefore continues to report incomplete coverage. Redirects from an allowed source are now rejected before the HTTP client follows a destination outside the RBI/NPCI HTTPS allowlist.
- Production dependency inspection on 26 September 2026 found no PostgreSQL client/server/container runtime, no listener on port 5432, and no configured database, OIDC/SAML, payment-provider, bank, or UPI connector environment variables. These are external launch dependencies, not code quality defects: production data-plane, identity, reconciliation, and deployment assurance cannot be implemented or certified without authorized target systems and their accountable owners.
- Browser review: signed into the local synthetic workspace, confirmed Case ID plus company/user ID and Email ID in the priority queue, and confirmed the case detail shows its current decision, evidence, risk, and ticket.
- A run of the full test suite found an order-dependent regulatory test assertion that selected an arbitrary newest item when timestamps tied. The assertion now selects by the expected publication URL; the suite then passed.

## Decision and fraud boundary

The source project specification says a suspicious signal calls for specialist investigation and warns against asserting fraud without an authorized determination. RBI's 2024 fraud-risk directions announcement states that regulated entities must apply principles of natural justice before classifying persons or entities as fraud. Applicability depends on the eventual operating entity and must be reviewed by counsel/compliance; this product does not make that legal determination. The current implementation therefore auto-routes possible fraud, while rejection is reserved for a clear configured rule failure that passes evidence and authority checks. [RBI's 2024 revised fraud-risk directions announcement](https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=58294)

## Complete pending work

The following are still open in the project's detailed task register:

| Task IDs | Pending work |
|---|---|
| 2.2 | Replace JSON-backed financial entities with normalized relational models, migrations, and full constraints. |
| 3.1, 3.3 | Source-specific raw ingestion and data quality; canonical financial event graph and robust report correlation beyond exact demo identity/payment/type matching. |
| 3.4, 3.5 | Evidence verification/update interface; administrable, effective-dated, precedence-aware policy engine. |
| 4.1, 4.3, 4.5 | Configurable queue routing; durable reminder scheduler, delivery/retry/escalation; authoritative resolution verification and reopen flow. |
| 5.6 | Admin screens for policy, users, queues, SLAs, and reports. |
| 6.3 | Automated browser end-to-end tests for employee and department journeys. |
| 8.8 | Replace supplied identity values with authenticated provider/customer identity and tenant-scoped authorization before real data or cross-report correlation is enabled. |
| 9.1–9.7 | Select entity/product applicability with counsel; finish source polling, dynamic NPCI coverage, freshness alerts/retries/DLQ, cited rule extraction, approved version activation/rollback, calibrated risk dimensions, and benchmark metrics. Initial 9.2a discovery/review is implemented but does not close 9.2. |
| 10.1–10.7 | PostgreSQL and migrations; adversarial tenant isolation; OIDC/SSO/MFA and scoped roles; validated provider/bank ingestion; evidence-backed live actions and authoritative verification; durable workers; threat, privacy, penetration, accessibility, disaster-recovery, load, and security sign-off. |
| 11.1–11.6 | Isolated AI gateway; evidence-grounded agents with prompt-injection controls; model risk governance; scalable deployment and observability; automated contract/resilience/security/performance/regulatory replay suites; customer acceptance and launch gates. |

## Material limitations and risks

### Cross-tenant isolation audit finding (production controls still incomplete)

The demo now enforces tenant filtering at its HTTP/service boundary for user-visible case and ticket data. Authentication maps a stored local account to its tenant, and adversarial tests cover dashboard/list/detail/audit reads and ticket mutation. This narrows the earlier finding, but is not sufficient for production: fixed demo passwords and process-local sessions are not trusted enterprise identity; test/service calls can pass tenant IDs directly; SQLite has no RLS safety net; and shared regulatory and policy controls have no tenant applicability model. Keep Phase 10.2 and 10.3 open until trusted identity mapping, database-enforced isolation, and independent adversarial testing are complete. Source implementation: `src/cause_ai/database.py` users tenant migration and `append_audit`; `src/cause_ai/server.py` `_actor()` and authenticated API dispatch; `src/cause_ai/service.py` tenant-scoped reads/writes and `_ticket_in_tx()`; `tests/test_cause_ai.py` the two tenant isolation tests.

- Repeat correlation trusts caller-supplied IDs for demo matching; a spoofed or shared email can cause a false link. Do not enable it for real customer data until identity is authenticated and tenant-scoped.
- All imported evidence is unverified. Consequently, the current import path escalates; it cannot safely demonstrate an automatic approval against real authoritative records.
- `AUTO_APPROVE` is a recorded decision only. No refund, settlement, payment, account block, or regulatory report is executed.
- The current audit is append-only through application/database triggers, not cryptographically tamper-evident against an administrator with access to the SQLite file.
- No generative AI or ML model is currently used. Detection, risk, and decisioning are deterministic Python logic.
- The local regulatory monitor does not determine legal applicability or activate policy. NPCI's current circular listing remains parser-limited, as separately recorded in the implementation status.

## Final disposition

The requested feature slice passes its current automated and browser checks. Production release remains **not approved by engineering evidence** until the open security, identity, data-source, policy/legal, operational, and independent-verification gates above are completed and signed off.

## Follow-up production-readiness recheck — 2026-09-25

- Current readiness is **38/100** after the tested local tenant-context foundation. The runtime guard prevents accidental exposure of this demo but does not deliver PostgreSQL/RLS, trusted identity lifecycle, authoritative payment data, complete official source capture, deployment operations, or independent assurance. Do not launch with real financial or personal data.
- `serve()` now refuses any `CAUSE_AI_ENV` except `demo`, and refuses non-loopback bind hosts before database initialization. Regressions cover both blocked launch paths.
- Verification: **56 automated tests pass**; `python -m compileall -q src tests` passes; `node --check src/cause_ai/static/app.js` passes; TODO/FIXME/NotImplemented scan returns no matches.
- No payment, bank, customer, or company production data source is configured in the workspace. Seeded cases and existing local records remain synthetic/demo data. Do not use them as real-data validation evidence.
- Official-source check: the [NPCI UPI circular index](https://www.npci.org.in/circulars/upi) lists FY 2026–27 material, including new circulars; this confirms the source is active but not that Cause AI captures all current entries. The product monitor remains parser-limited for its dynamically rendered listing. [RBI's payment and settlement notification index](https://www.rbi.org.in/Scripts/FS_Notification.aspx?fn=9) is a public source index; index access alone does not establish legal applicability or complete coverage.
- Read-only inspection of the currently running local app's regulatory database found the monitor's latest poll at `2026-09-25T14:44:39Z`: RBI PSS `OK`, zero new changes; NPCI UPI `PARSER_LIMITED`. RBI capture records contain original publication body text and references to the original circular PDFs, with SHA-256 hashes. Two captured examples are [Digital Payments – E-mandate Framework, 2026](https://www.rbi.org.in/Scripts/FS_Notification.aspx?Id=13374&fn=9&Mode=0) (21 Apr 2026) and [Master Directions on Authorisation to operate a Payment System](https://www.rbi.org.in/Scripts/FS_Notification.aspx?Id=13502&fn=9&Mode=0) (15 Jun 2026). These are real public regulatory publications, not payment/customer records, and they remain pending human review.
- Regulatory review now re-hashes staged content immediately before a review write. It rejects changed/missing/unreadable objects, invalid references, symlinks, and paths outside the object store; the review audit records the verified digest. Inbox listing does not hash the full object corpus or disclose stored filesystem paths.
- The local port-8000 server was verified healthy and loopback-only after a restart attempt was rejected by the desktop command policy (`blocked by policy`, with no more specific rationale). Its PID predates this change, so the currently running process must be manually restarted to load the updated regulatory review handler. Until then, the new guard is verified in code/tests but is not active in that running process.
- The [NPCI UPI circular index](https://www.npci.org.in/circulars/upi) lists FY 2026–27 material, but no NPCI circular bytes were captured by this monitor. Its listing coverage remains incomplete. Direct shell fetch attempts during this turn received HTTP 403; existing RBI source captures and status were read locally without mutating application data.
- A live read-only browser inspection of that official NPCI page rendered OC 237, OC 186A, and OC 227A entries for FY 2026–27. The same page's static backend response remained a 12.6 KB shell with no PDF links, and the collector correctly stayed `PARSER_LIMITED`. This proves a browser-visible feed exists but does not provide a supported production backend endpoint or complete collector implementation. One view action exposed OC 186A's official PDF URL; no file was downloaded or staged in this audit.
- Outstanding launch blockers remain the entire open list in `docs/TASKS.md`, particularly 8.8, 9.1–9.7, 10.1–10.7, and 11.1–11.6. A production launch score is not a compliance approval or a guarantee of suitability.
