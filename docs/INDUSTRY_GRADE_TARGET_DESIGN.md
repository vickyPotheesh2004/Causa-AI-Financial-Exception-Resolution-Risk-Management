# Cause AI industry-grade target design

## Purpose and present status

This document defines the production target for Cause AI as an Indian payments operations and exception-management platform. It expands the local prototype into a secure, multi-tenant, auditable service that can support financial institutions and payment-system participants. It is an implementation blueprint, not evidence that production controls already exist. The current application remains a local synthetic-data prototype until the production work in `TASKS.md` is delivered and independently verified.

The first deployment must identify the contracting entity and its role. A SaaS vendor, bank, Payment Aggregator, PSP bank, TPAP, and NPCI member can have different obligations. The platform must record applicability per customer, product, payment rail, role, geography, and transaction type; it must never assume that every RBI or NPCI instrument applies to every tenant.

## Regulatory awareness and controlled updates

Cause AI should automatically discover and stage changes from an approved source register. It must not automatically convert an AI interpretation into an active control or legal conclusion. Monitoring can be automated; legal applicability, rule interpretation, and activation must have accountable human approval.

### Update pipeline

1. **Source register:** compliance owners configure official sources, source jurisdiction, issuer, document family, canonical URL, permitted retrieval method, polling interval, and source owner. Initial India sources include RBI notifications, master directions and circulars; NPCI UPI circulars; Gazette notifications; and other sources only when counsel confirms relevance. Sources are allow-listed and retrieved over TLS.
2. **Change detection:** scheduled workers poll source indexes and known document URLs using conditional requests where supported. Store retrieval time, source publication date, source URL, response metadata, content hash, and original bytes in immutable/versioned object storage. Retry transient failures, report stale sources, and route parsing failures to a dead-letter queue. Never silently treat a failed poll as “no change.”
3. **Document classification:** distinguish final directions, amendments, addenda, draft consultations, FAQs, press releases, guidance, and withdrawn/superseded notices. Link amendments and identify likely replaced clauses. Draft proposals must never be activated as binding requirements.
4. **Extraction:** document parsing/OCR produces a reviewable text rendition linked to page/paragraph citations. Preserve the original PDF/HTML and its checksum. Extract candidate entities such as issuer, reference number, issue/effective dates, affected entities, product/rail, thresholds, conditions, reporting duties, and supersession links.
5. **Applicability and impact:** resolve applicability against each tenant's approved entity role, authorizations, payment products, membership/contract status, geography, merchant category, transaction type, authentication method, and operational workflows. Unknown applicability means “review required,” not “not applicable.”
6. **Draft rule generation:** AI may propose structured rule changes and a plain-language impact summary with exact source citations. A deterministic schema validator checks types, required dimensions, date ranges, units, currency, threshold scope, and internal consistency. It must not infer missing thresholds or silently merge conflicting provisions.
7. **Compliance review:** a qualified reviewer checks the original source, scope, extracted clauses, predecessor/successor relationships, applicability, customer impact, implementation plan, and test evidence. A second approver is required for high-impact financial limits, authentication, fraud handling, or customer-liability rules. Record reviewer identities, decisions, reasons, and timestamps.
8. **Versioned activation:** approved rules are immutable versions with `draft → review → approved → scheduled → active → superseded/withdrawn` states. Activation is effective-dated and tenant-scoped. A kill switch and rollback to the last approved version must be available and audited. A deployed rule package is signed and has a reproducible version identifier.
9. **Continuous assurance:** run rule regression suites, boundary tests, conflict tests, historical replay, and a shadow evaluation before activation. Alert on missed deadlines, stale source feeds, conflicting rules, rule coverage gaps, and failed deployments. Record exactly which versions were applied to every decision.

### Policy data model

Every rule needs at minimum: rule ID and version; source document ID, issuer, URL, hash, and pinpoint citation; status (draft/final/withdrawn); jurisdiction; applicable entity roles and participant memberships; rail/product; merchant category and eligibility conditions; transaction kind; amount and cumulative limits with currency/window; authentication/exception conditions; issue/effective/expiry dates; predecessor/successor; interpretation rationale; reviewer and approver; test suite/version; activation and rollback records.

Transaction caps cannot be represented by a single global UPI number. NPCI's UPI OC 185B addendum (28 August 2025), for example, provides different per-transaction and 24-hour cumulative limits for different merchant categories/use cases, has verified-merchant conditions, and says issuing banks must maintain cumulative limits. Rule evaluation therefore needs category, eligibility, member-bank settings, payment context, and time-window dimensions.

If no active, approved, applicable rule can be determined, Cause AI must produce `POLICY_REVIEW_REQUIRED` and block any consequential automated action. It must not fall back to a stale or generic limit.

## Target architecture

Use a modular, event-driven platform with stateless APIs and independently scalable workers. Do not split into microservices solely for fashion; keep domain modules in a modular monolith initially, with explicit APIs and event contracts so high-volume domains can be separated when measured load warrants it.

```text
Official regulatory sources      Bank / PSP / merchant sources
          │                                     │
          ▼                                     ▼
Regulatory monitor + review       Connector gateway + ingestion
          │                                     │
          └──────────────┬──────────────────────┘
                         ▼
                  Durable event bus
        ┌────────────────┼──────────────────┐
        ▼                ▼                  ▼
Normalization      Exception engine     Policy pipeline
        │                │                  │
        └────────────────┼──────────────────┘
                         ▼
              Case / evidence / risk APIs
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Workflow       AI gateway      Audit service
          │              │              │
          └──────────────┼──────────────┘
                         ▼
       Tenant-aware UI, department workspace, reports
```

### Production components

- **Web:** TypeScript/React application with accessible employee, department, compliance, auditor, and tenant-admin workspaces.
- **API:** Python/FastAPI services with Pydantic request/response models, OpenAPI contracts, explicit authorization dependencies, versioned endpoints, rate limits, and idempotency on every mutating operation.
- **System of record:** PostgreSQL with relational financial events, cases, evidence, policies, decisions, tickets, tenant keys, migrations, constraints, point-in-time recovery, and tenant row-level security. Tenant ID is mandatory at every repository boundary. SQLite is local-only.
- **Eventing/workers:** durable managed Kafka-compatible event bus or equivalent, transactional outbox, retry policy, idempotent consumers, dead-letter queues, replay controls, back-pressure, and scheduled workflow engine. Redis is a cache/coordination aid only, never financial truth.
- **Evidence/documents:** encrypted object storage with versioning, retention/legal hold, malware scanning, content hashes, access logging, and immutable retention controls where contract/regulation requires them.
- **Search/reporting:** tenant-filtered relational search first; add a search index or warehouse only with defined consistency, deletion, and access-control contracts.
- **AI gateway:** model/provider abstraction, approved model inventory, regional routing, request/response schemas, timeout and token budgets, redaction, tenant isolation, prompt-injection controls, and feature flags. No provider receives payment credentials or unnecessary personal data.
- **Security/operations:** SSO/OIDC, MFA, RBAC plus scoped attributes, KMS-managed secrets and keys, encryption in transit/at rest, private networking, WAF/API gateway, centralized secrets, SIEM, OpenTelemetry traces/metrics/logs, SLOs, incident response, backup/restore drills, vulnerability management, SBOM, signed builds, and controlled deployment environments.

## AI usage and decision boundaries

| Stage | AI role | Deterministic / human control |
|---|---|---|
| Regulatory change intake | Classify document type; extract candidate clauses; summarize impact; propose a structured rule draft with citations. | Official bytes/hash, source hierarchy, applicability schema, rule validation, legal interpretation, approval, activation, and rollback remain controlled and auditable. No AI auto-publishes policy. |
| Record investigation | Suggest relevant source lookups, likely missing links, root-cause hypotheses, and next evidence to collect. | Connectors enforce tenant/data scope; finance calculations use decimal-safe deterministic services; source facts retain provenance and authority labels. |
| Evidence synthesis | Draft a concise case explanation and cite evidence IDs/pages/records. | Citation existence and scope are validated; unsupported claims are blocked or labeled unknown/conflicting. User-provided record text is untrusted data, never instructions. |
| Risk | Optionally rank or classify signals under a registered model with version, training/evaluation documentation, thresholds, calibration, drift/fairness monitoring, and human review. | Risk score is never proof of fraud or sole authorization. Deterministic exposure calculation, policy limits, permissions, and review triggers remain authoritative. |
| Decision and action | Explain a deterministic decision and prepare a human-readable recommendation. | A policy/permission/action service independently validates eligibility, calculation, unresolved exceptions, amount limits, human approval, and idempotency. AI cannot move funds, set policy, close its own case, or bypass review. |
| Department response | Summarize findings and suggest next steps. | Department users own findings/resolution; separate authorized reviewer verifies against connected authoritative records before closure. |

All model outputs use strict JSON schemas, citations, safety labels, confidence/uncertainty, model/version metadata, and prompt/data lineage. Prompt-injection tests, adversarial evaluations, model outage behavior, and shadow deployments are release gates. When AI is unavailable, deterministic workflows continue where safe; otherwise the case is queued for human review.

## Risk management controls

The production risk service must track distinct financial exposure, fraud signal, operational severity, compliance risk, and customer impact; preserve point-in-time risk history; show factor provenance; configure thresholds by tenant/product/rail; and alert on drift and threshold changes. Threshold configuration is versioned and approved. Risk labels are not presented as probability unless calibrated and validated as such.

The decision service must require explicit, verified reconciliation state; complete and authoritative evidence; active applicable policy version; known decision authority; explicit scoped permission; configured value/velocity limits; no unresolved conflict; and required human approval before any action. A mismatch record must never be auto-approved simply because its evidence is verified and its aggregate score is low.

## Availability, scale, and recovery targets

Initial production SLOs must be set with customers before launch. Design for stateless horizontal API scaling, partitionable event consumers, bounded queues, connection pooling, autoscaling, tenant quotas, and read replicas for reporting. Define RPO/RTO per tenant and service tier, test restore and regional failover, and prevent partial workflows through outbox/inbox and idempotent state transitions. Use load tests based on an agreed volume profile rather than claiming scale from the local demo.

## Release gates

No production data onboarding until: entity/legal applicability review; threat model and privacy impact review; production identity and tenant isolation tests; security review/penetration test; authoritative connector and reconciliation tests; policy source/approval workflow; model risk review if AI ranking is enabled; benchmark precision/recall and false-positive cost; audit/retention controls; disaster recovery exercise; operational runbooks; and customer acceptance sign-off are complete.

## Verified official references

- [NPCI UPI Circulars](https://www.npci.org.in/circulars/upi) — official circular index, including newer FY 2026–27 circulars.
- [NPCI UPI OC 185B, 28 August 2025](https://www.npci.org.in/uploads/UPI_OC_No185_B_FY_2025_26_Addendum_to_OC_185_A_Implementation_of_higher_per_transaction_limit_for_specific_categories_in_UPI_ba517a0902.pdf) — category-specific enhanced per-transaction and cumulative limits and eligibility/issuer conditions.
- [RBI Payment and Settlement Systems notifications](https://www.rbi.org.in/Scripts/FS_Notification.aspx?fn=9) — official payment-system notification index.
- [RBI Master Directions index](https://www.rbi.org.in/Scripts/BS_ViewMasterDirections.aspx) — official consolidated direction index; applicability must still be determined for each entity role.

Regulatory sources were checked on 25 September 2026 for this design. This source list is a starting point, not a legal applicability opinion or proof of a live monitoring service.
