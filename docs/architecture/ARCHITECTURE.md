# Architecture

## System boundary

Cause AI is a controlled workflow around financial records. AI interprets evidence through limited tools; deterministic services own calculations, policy checks, permissions, state transitions, and action validation; authorized humans own consequential decisions when required; audit storage records the lifecycle.

## Conceptual flow

```text
Source systems and reports
        ↓
Ingestion, normalization, and data-quality checks
        ↓
Exception detection and report correlation
        ↓
Financial event graph and investigation
        ↓
Evidence assembly and conflict detection
        ↓
Versioned policy evaluation + explainable risk
        ↓
Deterministic decision and independent action validation
   ┌────┼───────────┬────────────┐
   ↓    ↓           ↓            ↓
Approve Reject Fraud escalation Department escalation
   └────┴───────────┴────────────┘
        ↓
Ticket/SLA/reminder workflow when routed
        ↓
Resolution, independent verification, closure or reopening
        ↓
Append-only searchable audit history
```

## Responsibility boundaries

| Component | Owns | Must not own |
|---|---|---|
| Ingestion and data quality | Normalize, validate, deduplicate, identify missing or inconsistent fields. | Invent absent values or silently overwrite conflicting source records. |
| Exception detector | Deterministic mismatch checks, classification, correlation. | Make an unsupported policy or fraud judgment. |
| Financial event graph | Link source records and preserve provenance. | Treat inferred links as authoritative without marking uncertainty. |
| Investigator / AI agent | Retrieve records through scoped tools, summarize findings, identify unknowns, recommend next steps. | Direct database access, unrestricted tool execution, ungrounded facts, or independent financial authorization. |
| Evidence service | Claim-to-source relationships, status, authority, conflict and provenance. | Convert model confidence into evidence. |
| Policy engine | Versioned rule retrieval and deterministic PASS/FAIL/UNKNOWN/CONFLICT result. | Hide source, version, effective date, or rule uncertainty. |
| Risk engine | Explainable factor-based dimensions and history. | Use a bare unexplained AI score as a final decision. |
| Decision and action guard | Enforce outcome criteria, roles, permissions, limits, and human approval. | Execute action that failed validation. |
| Ticket and reminder service | Configurable routing, assignment, SLA and valid transitions. | Assume a specific company's department structure. |
| Verification service | Independently confirm resolution against expected outcomes and source records. | Trust a submitted resolution without checking it. |
| Audit service | Append-only actor-attributed events and searchable history. | Rewrite prior findings or erase correction history. |

## Core records

The conceptual model includes tenants/merchants, source records, financial events and links, exceptions, reports, evidence, claims/findings, policy versions and rules, risk assessments, decisions, permissions, action requests/results, department tickets, assignments, SLA/reminders, resolution submissions, verification results, users/roles, and audit events. Exact schemas and retention behavior remain implementation decisions.

## Safety and failure behavior

Missing evidence yields UNKNOWN or DATA_INSUFFICIENT. Conflicting authoritative sources yield CONFLICTING and block automatic resolution. Unavailable policy yields POLICY_UNAVAILABLE. Unclear authority yields AUTHORITY_UNKNOWN. Invalid structured model output, failed tools, and timeouts must fail closed to a safe retry or escalation path. No AI confidence score bypasses these controls.

## Source authority

The supplied payment terms are reference material, not a complete or automatically current legal rulebook. Policy ingestion must retain source, version, jurisdiction, effective dates, and review owner. Applicable legal or regulatory interpretation requires a designated policy owner before operational use.

## Deployment and technology

The source specifications offer implementation options but do not establish a final stack, hosting target, or production integration. Select these after scope, data, security, and operational constraints are agreed. The architecture here describes responsibilities rather than claiming an existing implementation.

