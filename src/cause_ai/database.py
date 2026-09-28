"""SQLite storage, safe synthetic fixtures, and append-only audit events."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = Path(os.environ.get("CAUSE_AI_DB", str(ROOT / "data" / "cause_ai.sqlite3")))
DEMO_PASSWORD = "CauseDemo!2026"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = Path(path or os.environ.get("CAUSE_AI_DB", DEFAULT_DB))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10, isolation_level="DEFERRED")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    return salt.hex(), _password_hash(password, salt).hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    try:
        actual = _password_hash(password, bytes.fromhex(salt_hex)).hex()
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(actual, digest_hex)


def _evidence(case_id: str, records: list[tuple[str, str, str, str, str, str]]) -> list[dict[str, Any]]:
    return [
        {"id": f"EV-{case_id}-{name}", "fact": fact, "source_type": kind, "source_id": source,
         "authority": authority, "status": status, "timestamp": "2026-09-25T09:00:00+05:30"}
        for name, fact, kind, source, authority, status in records
    ]


def seed_cases() -> list[dict[str, Any]]:
    data = [
        ("EXC-2026-000184", "SETTLEMENT_MISMATCH", "High-value settlement shortfall", "PAY-10291", "INR", "10000.00", "MEDIUM", "VERIFIED", "OPEN", 1, "Settlement Ops", "Settlement", True, "CAPTURED payment 10,000; fee 250; expected settlement 9,750; settled 9,500.", [
            ("payment", "Payment PAY-10291 captured for INR 10,000.00", "payment", "PAY-10291", "PAYMENT_LEDGER", "VERIFIED"),
            ("fee", "Fee FEE-772 is INR 250.00", "fee", "FEE-772", "FEE_LEDGER", "VERIFIED"),
            ("settlement", "Settlement SET-441 is INR 9,500.00", "settlement", "SET-441", "SETTLEMENT_LEDGER", "VERIFIED")]),
        ("EXC-2026-000185", "REFUND_MISMATCH", "Refund amount differs from request", "PAY-10308", "INR", "3200.00", "LOW", "VERIFIED", "DECISION_READY", 1, "Refund Ops", "Refund", True, "Requested refund INR 3,200.00; recorded refund INR 2,700.00.", [
            ("payment", "Payment PAY-10308 captured for INR 3,200.00", "payment", "PAY-10308", "PAYMENT_LEDGER", "VERIFIED"),
            ("refund", "Refund REF-220 is INR 2,700.00", "refund", "REF-220", "REFUND_LEDGER", "VERIFIED")]),
        ("EXC-2026-000186", "MISSING_SETTLEMENT", "Settlement record not found", "PAY-10311", "INR", "18000.00", "MEDIUM", "INSUFFICIENT", "INVESTIGATING", 1, "Settlement Ops", "Settlement", False, "Payment is captured, but no linked settlement record is available.", [
            ("payment", "Payment PAY-10311 captured for INR 18,000.00", "payment", "PAY-10311", "PAYMENT_LEDGER", "VERIFIED")]),
        ("EXC-2026-000187", "BANK_MISMATCH", "Conflicting bank and settlement amounts", "PAY-10320", "INR", "54500.00", "HIGH", "CONFLICTING", "ESCALATED", 2, "Settlement Ops", "Bank reconciliation", False, "Settlement ledger and bank statement show conflicting values.", [
            ("settlement", "Settlement SET-490 is INR 54,500.00", "settlement", "SET-490", "SETTLEMENT_LEDGER", "VERIFIED"),
            ("bank", "Bank entry BANK-776 is INR 52,000.00", "bank", "BANK-776", "BANK_STATEMENT", "CONFLICTING")]),
        ("EXC-2026-000188", "SUSPICIOUS_ACTIVITY", "Repeated unusual refund attempts", "PAY-10331", "INR", "128000.00", "HIGH", "VERIFIED", "ESCALATED", 4, "Risk/Fraud", "Fraud review", False, "Multiple refund attempts across linked transactions require specialist review.", [
            ("signal", "Four refund attempts were reported in a short interval", "risk_signal", "SIG-10331", "DEMO_SIGNAL", "UNVERIFIED"),
            ("payment", "Payment PAY-10331 captured for INR 128,000.00", "payment", "PAY-10331", "PAYMENT_LEDGER", "VERIFIED")]),
        ("EXC-2026-000189", "FEE_DISCREPANCY", "Fee exceeds configured schedule", "PAY-10337", "INR", "7200.00", "LOW", "VERIFIED", "DETECTED", 1, "Settlement Ops", "Fee review", True, "Recorded fee exceeds the synthetic demo schedule for this case.", [
            ("payment", "Payment PAY-10337 captured for INR 7,200.00", "payment", "PAY-10337", "PAYMENT_LEDGER", "VERIFIED"),
            ("fee", "Recorded fee FEE-781 is INR 600.00", "fee", "FEE-781", "FEE_LEDGER", "VERIFIED")]),
        ("EXC-2026-000190", "DUPLICATE_TRANSACTION", "Possible duplicate payment capture", "PAY-10342", "INR", "2500.00", "MEDIUM", "CONFLICTING", "INVESTIGATING", 2, "Payment Ops", "Duplicate review", False, "Two capture records share the payment reference but have different event identifiers.", [
            ("capture1", "Capture CAP-901 recorded for INR 2,500.00", "payment", "CAP-901", "PAYMENT_LEDGER", "VERIFIED"),
            ("capture2", "Capture CAP-902 recorded for INR 2,500.00", "payment", "CAP-902", "PAYMENT_LEDGER", "CONFLICTING")]),
        ("EXC-2026-000191", "ADJUSTMENT_DISCREPANCY", "Repeated adjustment discrepancy", "PAY-10350", "INR", "42000.00", "MEDIUM", "VERIFIED", "DETECTED", 3, "Settlement Ops", "Adjustment review", True, "Adjustment AJ-118 is not reflected in the expected settlement calculation.", [
            ("payment", "Payment PAY-10350 captured for INR 42,000.00", "payment", "PAY-10350", "PAYMENT_LEDGER", "VERIFIED"),
            ("adjustment", "Adjustment AJ-118 is INR 1,200.00", "adjustment", "AJ-118", "ADJUSTMENT_LEDGER", "VERIFIED")]),
    ]
    output = []
    for index, row in enumerate(data):
        case_id, kind, title, payment_id, currency, amount, priority, evidence_status, status, reports, queue, category, permitted, summary, records = row
        suffix = case_id.rsplit("-", 1)[-1]
        subject_type = "COMPANY" if index % 2 == 0 else "USER"
        output.append({
            "id": case_id, "type": kind, "title": title, "payment_id": payment_id,
            "subject_type": subject_type, "subject_id": f"SYN-{subject_type[:3]}-{suffix}",
            "email_id": f"synthetic.case{suffix}@example.invalid",
            "currency": currency, "amount": amount, "priority": priority,
            "evidence_status": evidence_status, "status": status, "report_count": reports,
            "department": queue, "category": category, "action_permitted": permitted,
            "authority_known": True, "summary": summary,
            # This is the source-visible registration timestamp for the synthetic
            # fixture. Imported cases receive their registration time at ingestion.
            "registered_at": "2026-09-25T08:45:00+05:30",
            "evidence": _evidence(case_id, records),
            "timeline": [
                {"time": "2026-09-25T08:45:00+05:30", "event": "Exception detected", "source": "Cause AI detection demo"},
                {"time": "2026-09-25T09:00:00+05:30", "event": "Source records gathered", "source": "Synthetic finance records"},
            ],
        })
    return output


def initialize(path: str | Path | None = None, reseed: bool = False) -> None:
    conn = connect(path)
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('ACTIVE','SUSPENDED')),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, role TEXT NOT NULL CHECK(role IN ('analyst','department','admin')),
            salt TEXT NOT NULL, password_hash TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            tenant_id TEXT NOT NULL DEFAULT 'DEMO-MERCHANT-01'
        );
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, status TEXT NOT NULL,
            data_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
        CREATE INDEX IF NOT EXISTS idx_cases_tenant ON cases(tenant_id);
        CREATE TABLE IF NOT EXISTS policies (
            id TEXT PRIMARY KEY, version TEXT NOT NULL, status TEXT NOT NULL,
            source TEXT NOT NULL, effective_from TEXT NOT NULL, data_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS policy_proposals (
            id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            policy_id TEXT NOT NULL, version TEXT NOT NULL, policy_status TEXT NOT NULL CHECK(policy_status IN ('PASS','FAIL','UNKNOWN')),
            source TEXT NOT NULL, effective_from TEXT NOT NULL, data_json TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('DRAFT','APPROVED','REJECTED','ACTIVE','SUPERSEDED')),
            created_by TEXT NOT NULL, created_at TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT,
            review_reason TEXT, activated_by TEXT, activated_at TEXT,
            UNIQUE(tenant_id, policy_id, version)
        );
        CREATE INDEX IF NOT EXISTS idx_policy_proposals_tenant_state ON policy_proposals(tenant_id, state, created_at DESC);
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), status TEXT NOT NULL,
            department TEXT NOT NULL, priority TEXT NOT NULL, data_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
        CREATE TABLE IF NOT EXISTS audit_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
            tenant_id TEXT NOT NULL, actor TEXT NOT NULL, actor_role TEXT NOT NULL,
            action TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL,
            reason TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_events(object_type, object_id, seq);
        CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id, seq);
        CREATE TABLE IF NOT EXISTS audit_integrity (
            audit_event_id TEXT PRIMARY KEY REFERENCES audit_events(id), tenant_id TEXT NOT NULL,
            sequence INTEGER NOT NULL, previous_sha256 TEXT, event_sha256 TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, UNIQUE(tenant_id, sequence)
        );
        CREATE INDEX IF NOT EXISTS idx_audit_integrity_tenant ON audit_integrity(tenant_id, sequence);
        CREATE TABLE IF NOT EXISTS idempotency (
            key TEXT PRIMARY KEY, actor TEXT NOT NULL, response_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS detection_runs (
            run_hash TEXT PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'DEMO-MERCHANT-01',
            actor TEXT NOT NULL, response_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS financial_events (
            id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
            source_system TEXT NOT NULL, source_record_id TEXT NOT NULL,
            record_type TEXT NOT NULL, payment_id TEXT NOT NULL, occurred_at TEXT,
            currency TEXT, amount TEXT, content_sha256 TEXT NOT NULL,
            data_json TEXT NOT NULL, ingested_at TEXT NOT NULL,
            UNIQUE(tenant_id, source_system, source_record_id)
        );
        CREATE INDEX IF NOT EXISTS idx_financial_events_tenant_payment ON financial_events(tenant_id, payment_id, ingested_at);
        CREATE INDEX IF NOT EXISTS idx_financial_events_hash ON financial_events(tenant_id, content_sha256);
        CREATE TABLE IF NOT EXISTS regulatory_sources (
            source_id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, checked_at TEXT,
            status TEXT NOT NULL DEFAULT 'NEVER_CHECKED', last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS regulatory_documents (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES regulatory_sources(source_id),
            title TEXT NOT NULL, url TEXT NOT NULL, published_label TEXT, content_sha256 TEXT NOT NULL,
            canonical_sha256 TEXT,
            stored_path TEXT, content_type TEXT NOT NULL, discovered_at TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED', review_actor TEXT,
            review_reason TEXT, reviewed_at TEXT, UNIQUE(url, content_sha256)
        );
        CREATE INDEX IF NOT EXISTS idx_regulatory_review ON regulatory_documents(review_status, discovered_at);
        CREATE TABLE IF NOT EXISTS regulatory_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL REFERENCES regulatory_sources(source_id),
            checked_at TEXT NOT NULL, status TEXT NOT NULL, item_count INTEGER NOT NULL DEFAULT 0,
            error TEXT
        );
        CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
        BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
        BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_integrity_no_update BEFORE UPDATE ON audit_integrity
        BEGIN SELECT RAISE(ABORT, 'audit integrity records are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_integrity_no_delete BEFORE DELETE ON audit_integrity
        BEGIN SELECT RAISE(ABORT, 'audit integrity records are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS financial_events_no_update BEFORE UPDATE ON financial_events
        BEGIN SELECT RAISE(ABORT, 'financial events are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS financial_events_no_delete BEFORE DELETE ON financial_events
        BEGIN SELECT RAISE(ABORT, 'financial events are immutable'); END;
        """)
        conn.execute("INSERT OR IGNORE INTO tenants(id,status,created_at) VALUES(?,?,?)", ("DEMO-MERCHANT-01", "ACTIVE", now_iso()))
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "tenant_id" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'DEMO-MERCHANT-01'")
        detection_run_columns = {row[1] for row in conn.execute("PRAGMA table_info(detection_runs)")}
        if "tenant_id" not in detection_run_columns:
            conn.execute("ALTER TABLE detection_runs ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'DEMO-MERCHANT-01'")
        if conn.execute("SELECT COUNT(*) FROM schema_meta").fetchone()[0] == 0:
            conn.execute("INSERT INTO schema_meta(version) VALUES (1)")
        conn.execute("UPDATE schema_meta SET version=5 WHERE version<5")
        regulatory_columns = {row[1] for row in conn.execute("PRAGMA table_info(regulatory_documents)")}
        if "canonical_sha256" not in regulatory_columns:
            conn.execute("ALTER TABLE regulatory_documents ADD COLUMN canonical_sha256 TEXT")
        for username, role in (("analyst", "analyst"), ("department", "department"), ("admin", "admin")):
            if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone() is None:
                salt, digest = hash_password(DEMO_PASSWORD)
                conn.execute("INSERT INTO users(username,role,salt,password_hash) VALUES(?,?,?,?)", (username, role, salt, digest))
        if reseed:
            conn.execute("DELETE FROM tickets")
            conn.execute("DELETE FROM cases")
            conn.execute("DELETE FROM idempotency")
            conn.execute("DELETE FROM financial_events")
        if conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 0:
            timestamp = now_iso()
            sample_sla_due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
            for case in seed_cases():
                conn.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)", (case["id"], "DEMO-MERCHANT-01", case["status"], json.dumps(case), timestamp, timestamp))
            for policy_id, status, description in (
                ("DEMO-REFUND-001", "PASS", "Synthetic demo refund evidence and amount checks"),
                ("DEMO-FEE-003", "FAIL", "Synthetic demo fee schedule check failed"),
                ("DEMO-STANDARD-001", "PASS", "Synthetic demo evidence completeness check"),
            ):
                policy = {"id": policy_id, "version": "1.0-demo", "status": status, "description": description, "source": "Cause AI synthetic demo policy", "effective_from": "2026-01-01"}
                conn.execute("INSERT OR IGNORE INTO policies VALUES(?,?,?,?,?,?)", (policy_id, policy["version"], status, policy["source"], policy["effective_from"], json.dumps(policy)))
            # Seed tickets make the department queue and reminders workflow immediately explorable.
            for ticket in (
                {"id":"TKT-2026-0041","case_id":"EXC-2026-000187","status":"OPEN","department":"Settlement Ops","priority":"HIGH","summary":"Investigate conflicting bank and settlement records.","sla_due":sample_sla_due,"reminders_sent":0},
                {"id":"TKT-2026-0042","case_id":"EXC-2026-000188","status":"ASSIGNED","department":"Risk/Fraud","priority":"HIGH","summary":"Review suspicious refund pattern; no fraud determination has been made.","sla_due":sample_sla_due,"reminders_sent":0},
            ):
                conn.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?)", (ticket["id"], ticket["case_id"], ticket["status"], ticket["department"], ticket["priority"], json.dumps(ticket), timestamp, timestamp))
        # Enrich existing seeded cases on upgrade; never infer identities for imported cases.
        seeded_identities = {case["id"]: {key: case[key] for key in ("subject_type", "subject_id", "email_id")} for case in seed_cases()}
        for case_id, data_json, created_at in conn.execute("SELECT id,data_json,created_at FROM cases").fetchall():
            identity = seeded_identities.get(case_id)
            case_data = json.loads(data_json)
            changed = False
            if identity and not any(case_data.get(key) for key in identity):
                    case_data.update(identity)
                    changed = True
            if not case_data.get("registered_at"):
                case_data["registered_at"] = created_at
                changed = True
            if changed:
                conn.execute("UPDATE cases SET data_json=? WHERE id=?", (json.dumps(case_data), case_id))
        conn.commit()
    finally:
        conn.close()


def append_audit(conn: sqlite3.Connection, actor: str, role: str, action: str, object_type: str,
                 object_id: str, reason: str, details: dict[str, Any] | None = None,
                 tenant_id: str | None = None) -> dict[str, Any]:
    if not tenant_id:
        raise ValueError("An authenticated tenant_id is required for audit events")
    event = {"id": "AUD-" + secrets.token_hex(8), "tenant_id": tenant_id, "actor": actor,
             "actor_role": role, "action": action, "object_type": object_type,
             "object_id": object_id, "reason": reason, "details": details or {}, "created_at": now_iso()}
    conn.execute("INSERT INTO audit_events(id,tenant_id,actor,actor_role,action,object_type,object_id,reason,details_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (event["id"], tenant_id, actor, role, action, object_type, object_id, reason,
                  json.dumps(event["details"]), event["created_at"]))
    previous = conn.execute("SELECT sequence,event_sha256 FROM audit_integrity WHERE tenant_id=? ORDER BY sequence DESC LIMIT 1", (tenant_id,)).fetchone()
    sequence = int(previous["sequence"]) + 1 if previous else 1
    previous_sha256 = previous["event_sha256"] if previous else None
    canonical = json.dumps({**event, "previous_sha256": previous_sha256}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    event_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    conn.execute("INSERT INTO audit_integrity(audit_event_id,tenant_id,sequence,previous_sha256,event_sha256,created_at) VALUES(?,?,?,?,?,?)",
                 (event["id"], tenant_id, sequence, previous_sha256, event_sha256, event["created_at"]))
    event["integrity"] = {"sequence": sequence, "sha256": event_sha256, "previous_sha256": previous_sha256}
    return event


def row_case(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return json.loads(row["data_json"]) if row else None


def row_ticket(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return json.loads(row["data_json"]) if row else None
