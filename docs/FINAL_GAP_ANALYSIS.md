# Causa Final Gap Analysis

Verified on: 2026-09-28

## Implemented

- Deterministic decimal financial calculations, exception detection, policy checks, explainable risk, automatic routing, ticket workflow, evidence and tenant controls.
- Immutable financial-event records, append-only audit events, hash-chain verification for current audit schema events, idempotency and role checks.
- Read-only Razorpay connector guardrails and a regulatory-source monitor that fails closed when source parsing is incomplete.
- Synthetic local demo, Vercel synthetic demo adapter, responsive browser interface and automated test suite.

## Partially Implemented

- The public Vercel demo functions with synthetic data but uses ephemeral SQLite and process-memory sessions.
- Architecture documents describe production services, but durable PostgreSQL and persistent session-store adapters are not implemented.
- The interface shows deterministic evidence and investigation descriptions but has no bounded AI investigation panel.
- Existing documentation and generated reports retain older branding, test counts and schema references.

## Missing

- AI provider abstraction for optional Ollama and Gemini use, structured investigation findings and evidence-grounded validation.
- 100-record benchmark dataset, independent ground truth, evaluation CLI and benchmark UI.
- Storage and session provider interfaces, optional external PostgreSQL implementation, durable-session implementation and production migrations.
- Current final audit, test matrix, final submission report and clean-install verification.

## Broken or Inconsistent

- Visible branding still says `Cause AI` while the requested product name is `Causa`.
- `pyproject.toml` requests Python 3.12 while Docker and README support Python 3.11.
- Generated local build directories and cached presentation dependencies are present in the workspace and should remain excluded from source control.

## Outdated Documentation

- Historical reports state 56, 72 or 74 tests and must be regenerated only after the final suite completes.
- The legal page contains unfinished company placeholders and needs an explicit synthetic-demo notice.
- README needs zero-cost AI configuration, benchmark instructions and deployment-mode boundaries.

## Deployment Risks

- Vercel functions can be recycled, so `/tmp` SQLite and in-memory sessions are not durable.
- Vercel demo mode must not receive real financial data or be called a production deployment.
- A durable production deployment requires an external database, persistent sessions, managed secrets, identity, monitoring and approved operational controls.

## Security Risks

- External AI providers must be optional, outbound only, secret-safe and constrained to a minimized investigation context.
- AI output must be schema-validated, evidence-cited and never permitted to alter financial, policy, audit or authorization state.
- Historical generated artifacts need a final secret and stale-content review before submission.

## AI Gaps

- Current system is deterministic only. It does not claim to use an LLM.
- Required additions are provider selection, a safe fallback label, prompt-injection resistance, structured findings, evidence-ID validation and a UI panel that distinguishes assistance from authority.

## Testing Gaps

- Add AI safety and schema tests, prompt-injection tests, benchmark tests, responsive smoke tests and clean-install checks.
- Docker cannot be verified on this host until Docker is available.
- External Ollama and Gemini calls must remain opt-in and must not run in normal CI.

## Repository Cleanup

- Keep source, documentation, dataset and meaningful submission artifacts.
- Exclude generated `public/`, virtual environments, caches, render outputs, local databases, backups and presentation dependency trees from commits.
