from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cause_ai.database import append_audit, connect, hash_password, initialize, seed_cases
from cause_ai.domain import calculate_expected_settlement, decide, detect_exceptions, money, risk_assessment, validate_transition
from cause_ai.server import CauseAIHandler
from cause_ai.preflight import assess_production_environment


class RuntimeSafetyTests(unittest.TestCase):
    def test_production_preflight_fails_closed_and_redacts_secret_values(self):
        failed = assess_production_environment({"SESSION_SIGNING_KEY": "secret-value-that-must-not-appear-in-output"})
        self.assertFalse(failed["ready"])
        self.assertIn("postgresql_database_configured", failed["blockers"])
        self.assertNotIn("secret-value", str(failed))
        configured = assess_production_environment({
            "CAUSE_AI_ENV": "production", "DATABASE_URL": "postgresql://service@db/cause",
            "OIDC_ISSUER": "https://identity.example.com", "OIDC_AUDIENCE": "cause-ai",
            "SESSION_SIGNING_KEY": "x" * 32, "ALLOWED_ORIGINS": "https://cause.example.com",
            "OBSERVABILITY_ENDPOINT": "https://telemetry.example.com", "OBJECT_STORAGE_BUCKET": "cause-evidence",
            "WORKER_QUEUE_URL": "https://queue.example.com", "BACKUP_PLAN_ID": "backup-plan-123",
            "DATA_GOVERNANCE_APPROVED": "true", "SECURITY_RELEASE_APPROVED": "true",
        })
        self.assertTrue(configured["ready"])

    def test_server_refuses_production_profile_until_controls_exist(self):
        import cause_ai.server as server_module
        with patch.object(server_module, "RUNTIME_ENV", "production"):
            with self.assertRaisesRegex(RuntimeError, "production launch is blocked"):
                server_module.serve("127.0.0.1", 8000)

    def test_demo_server_refuses_non_loopback_binding(self):
        import cause_ai.server as server_module
        with patch.object(server_module, "RUNTIME_ENV", "demo"):
            with self.assertRaisesRegex(RuntimeError, "bind only to loopback"):
                server_module.serve("0.0.0.0", 8000)
from cause_ai import regulatory, razorpay
from cause_ai.service import (ServiceError, authenticate, evaluate_case, get_case,
                              list_cases, resolve_ticket, respond_to_ticket, run_reminders, verify_ticket,
                              create_detected_cases, propose_policy, review_policy_proposal,
                              activate_policy_proposal, list_policy_proposals, audit_integrity_status)
from cause_ai.tool_registry import controlled_tool_registry


class DomainTests(unittest.TestCase):
    def test_public_razorpay_schema_sample_detects_a_settlement_mismatch(self):
        sample_path = ROOT / "src" / "cause_ai" / "static" / "samples" / "razorpay_public_schema_sample.json"
        records = json.loads(sample_path.read_text(encoding="utf-8"))
        findings = detect_exceptions(records, schema_version="1.1")
        self.assertEqual([(finding["type"], finding["amount"]) for finding in findings], [("SETTLEMENT_MISMATCH", "2.00")])

    def test_detection_flags_settlement_shortfall_with_source_ids(self):
        records = [
            {"record_type":"payment","record_id":"PAY-1","payment_id":"P1","currency":"INR","amount":"10000","status":"CAPTURED"},
            {"record_type":"fee","record_id":"FEE-1","payment_id":"P1","currency":"INR","amount":"250"},
            {"record_type":"settlement","record_id":"SET-1","payment_id":"P1","currency":"INR","amount":"9500"},
        ]
        result = detect_exceptions(records)
        self.assertEqual([x["type"] for x in result], ["SETTLEMENT_MISMATCH"])
        self.assertEqual(result[0]["amount"], "250.00")
        self.assertEqual(result[0]["evidence_ids"], ["FEE-1", "PAY-1", "SET-1"])

    def test_settlement_discrepancy_zero_cent_and_high_boundaries(self):
        def detect(settled):
            return detect_exceptions([
                {"record_type":"payment", "record_id":"P", "payment_id":"BOUNDARY", "currency":"INR", "amount":"100.00", "status":"CAPTURED"},
                {"record_type":"fee", "record_id":"F", "payment_id":"BOUNDARY", "currency":"INR", "amount":"5.00"},
                {"record_type":"settlement", "record_id":"S", "payment_id":"BOUNDARY", "currency":"INR", "amount":settled},
            ])
        self.assertEqual(detect("95.00"), [])
        cent_difference = detect("94.99")
        self.assertEqual([(item["type"], item["amount"]) for item in cent_difference], [("SETTLEMENT_MISMATCH", "0.01")])
        high_difference = detect("1.00")
        self.assertEqual([(item["type"], item["amount"]) for item in high_difference], [("SETTLEMENT_MISMATCH", "94.00")])

    def test_detection_flags_missing_settlement(self):
        result = detect_exceptions([{"record_type":"payment","record_id":"P1","payment_id":"P1","amount":"100","status":"CAPTURED"}])
        self.assertEqual(result[0]["type"], "MISSING_SETTLEMENT")

    def test_detection_covers_duplicate_and_suspicious_activity(self):
        records = [
            {"record_type":"payment","record_id":"P1-A","payment_id":"P1","amount":"100","refund_attempt_count":4},
            {"record_type":"payment","record_id":"P1-B","payment_id":"P1","amount":"100","refund_attempt_count":4},
        ]
        kinds = {x["type"] for x in detect_exceptions(records)}
        self.assertIn("DUPLICATE_TRANSACTION", kinds)
        self.assertIn("SUSPICIOUS_ACTIVITY", kinds)

    def test_detection_covers_fee_refund_adjustment_bank_and_timing(self):
        fee = detect_exceptions([
            {"record_type":"payment","record_id":"P","payment_id":"FEE","amount":"100","expected_fee_amount":"5"},
            {"record_type":"fee","record_id":"F","payment_id":"FEE","amount":"7"},
        ])
        self.assertIn("FEE_DISCREPANCY", {x["type"] for x in fee})
        refund = detect_exceptions([
            {"record_type":"payment","record_id":"P","payment_id":"REF","amount":"100"},
            {"record_type":"refund_request","record_id":"RQ","payment_id":"REF","amount":"50","status":"REQUESTED"},
            {"record_type":"refund","record_id":"R","payment_id":"REF","amount":"40","status":"COMPLETED"},
            {"record_type":"settlement","record_id":"S","payment_id":"REF","amount":"60"},
        ])
        self.assertIn("REFUND_MISMATCH", {x["type"] for x in refund})
        adjustment = detect_exceptions([
            {"record_type":"payment","record_id":"P","payment_id":"ADJ","amount":"100"},
            {"record_type":"adjustment","record_id":"A","payment_id":"ADJ","amount":"10"},
            {"record_type":"settlement","record_id":"S","payment_id":"ADJ","amount":"100"},
        ])
        self.assertIn("ADJUSTMENT_DISCREPANCY", {x["type"] for x in adjustment})
        bank = detect_exceptions([
            {"record_type":"payment","record_id":"P","payment_id":"BANK","amount":"100"},
            {"record_type":"settlement","record_id":"S","payment_id":"BANK","amount":"100"},
            {"record_type":"bank","record_id":"B","payment_id":"BANK","amount":"99"},
        ])
        self.assertIn("BANK_MISMATCH", {x["type"] for x in bank})
        timing = detect_exceptions([
            {"record_type":"payment","record_id":"P","payment_id":"TIME","amount":"100","occurred_at":"2026-09-01"},
            {"record_type":"settlement","record_id":"S","payment_id":"TIME","amount":"100","occurred_at":"2026-09-20"},
        ])
        self.assertIn("TIMING_EXCEPTION", {x["type"] for x in timing})

    def test_detection_invalid_data_fails_safe_to_unknown_or_validation(self):
        invalid_amount = detect_exceptions([{"record_type":"payment","record_id":"P","payment_id":"P","amount":"NaN"}])
        self.assertEqual(invalid_amount[0]["type"], "UNKNOWN_EXCEPTION")
        missing = detect_exceptions([{"record_type":"event","record_id":"E","payment_id":"P"}])
        self.assertEqual(missing[0]["type"], "UNKNOWN_EXCEPTION")
        with self.assertRaises(ValueError):
            detect_exceptions([])
        with self.assertRaises(ValueError):
            detect_exceptions([{"record_type":"payment","record_id":"P","payment_id":"P"}], -1)
        with self.assertRaises(ValueError):
            detect_exceptions([{"record_type":"payment","record_id":"X","payment_id":"P"},{"record_type":"fee","record_id":"X","payment_id":"P"}])

    def test_suspicious_signal_requires_boolean_and_string_false_is_not_truthy(self):
        records = [
            {"record_type":"payment", "record_id":"P", "payment_id":"P", "amount":"100", "suspicious_signal":"false"},
            {"record_type":"settlement", "record_id":"S", "payment_id":"P", "amount":"100"},
        ]
        with self.assertRaisesRegex(ValueError, "must be a JSON boolean"):
            detect_exceptions(records)
        records[0]["suspicious_signal"] = False
        self.assertNotIn("SUSPICIOUS_ACTIVITY", {finding["type"] for finding in detect_exceptions(records)})

    def test_normalized_records_reject_unknown_fields_and_mistyped_units(self):
        base = {"record_type":"payment", "record_id":"P", "payment_id":"P", "currency":"INR", "amount":"10"}
        with self.assertRaisesRegex(ValueError, "unsupported payment field"):
            detect_exceptions([{**base, "currency_code":"INR"}])
        with self.assertRaisesRegex(ValueError, "currency must be a three-letter"):
            detect_exceptions([{**base, "currency":"RUPEES"}])
        with self.assertRaisesRegex(ValueError, "refund_attempt_count must be a non-negative integer"):
            detect_exceptions([{**base, "refund_attempt_count":"4"}])

    def test_decimal_settlement_calculation(self):
        self.assertEqual(calculate_expected_settlement("10000", "250", "0", "0"), money("9750.00"))

    def test_money_rejects_nan_and_unknown_currency(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                money(value)
        with self.assertRaises(ValueError):
            money("10", "XXX")

    def test_money_rounding_is_decimal_and_explicit(self):
        self.assertEqual(money("1.005"), money("1.01"))

    def test_missing_evidence_escalates(self):
        case = {"id":"C1", "type":"SETTLEMENT_MISMATCH", "amount":"100", "evidence_status":"INSUFFICIENT", "authority_known":True, "action_permitted":True}
        result = decide(case, {"status":"PASS"}, risk_assessment(case))
        self.assertEqual(result["outcome"], "DEPARTMENT_ESCALATE")
        self.assertIn("INSUFFICIENT_EVIDENCE", result["blockers"])

    def test_unverified_or_missing_evidence_never_auto_approves(self):
        for status in ("UNVERIFIED", "INVALID", "UNKNOWN", None):
            case = {"id":"C1", "type":"SETTLEMENT_MISMATCH", "amount":"100", "authority_known":True, "action_permitted":True}
            if status is not None:
                case["evidence_status"] = status
            with self.subTest(status=status):
                result = decide(case, {"status":"PASS"}, risk_assessment(case))
                self.assertEqual(result["outcome"], "DEPARTMENT_ESCALATE")

    def test_conflict_blocks_automatic_resolution(self):
        case = {"id":"C1", "type":"SETTLEMENT_MISMATCH", "amount":"100", "evidence_status":"CONFLICTING", "authority_known":True, "action_permitted":True}
        self.assertEqual(decide(case, {"status":"PASS"}, risk_assessment(case))["outcome"], "DEPARTMENT_ESCALATE")

    def test_possible_fraud_is_escalated_not_confirmed(self):
        case = {"id":"C1", "type":"SUSPICIOUS_ACTIVITY", "amount":"100", "evidence_status":"VERIFIED", "authority_known":True, "action_permitted":True}
        result = decide(case, {"status":"PASS"}, risk_assessment(case))
        self.assertEqual(result["outcome"], "FRAUD_ESCALATE")
        self.assertIn("Possible suspicious activity", result["reason"])

    def test_identity_fields_require_version_1_1_and_consistent_bundle_identity(self):
        records = [
            {"record_type":"payment", "record_id":"P", "payment_id":"P", "amount":"100", "status":"CAPTURED", "subject_type":"USER", "subject_id":"U-7", "email_id":"user@example.invalid"},
            {"record_type":"settlement", "record_id":"S", "payment_id":"P", "amount":"90", "subject_type":"USER", "subject_id":"U-7", "email_id":"user@example.invalid"},
        ]
        with self.assertRaisesRegex(ValueError, "unsupported"):
            detect_exceptions(records)
        finding = detect_exceptions(records, schema_version="1.1")[0]
        self.assertEqual(finding["subject_type"], "USER")
        conflicting = [*records, {"record_type":"report", "record_id":"R", "payment_id":"P", "subject_type":"USER", "subject_id":"U-8"}]
        with self.assertRaisesRegex(ValueError, "same user or company"):
            detect_exceptions(conflicting, schema_version="1.1")

    def test_clear_policy_failure_rejects(self):
        case = {"id":"C1", "type":"FEE_DISCREPANCY", "amount":"100", "evidence_status":"VERIFIED", "authority_known":True, "action_permitted":True}
        self.assertEqual(decide(case, {"status":"FAIL"}, risk_assessment(case))["outcome"], "REJECT")

    def test_auto_approve_only_with_all_demo_guards(self):
        case = {"id":"C1", "type":"SETTLEMENT_MISMATCH", "amount":"100", "evidence_status":"VERIFIED", "authority_known":True, "action_permitted":True, "action_idempotent":True, "reconciliation_status":"RECONCILED"}
        self.assertEqual(decide(case, {"status":"PASS"}, risk_assessment(case))["outcome"], "AUTO_APPROVE")
        case["action_permitted"] = False
        self.assertEqual(decide(case, {"status":"PASS"}, risk_assessment(case))["outcome"], "DEPARTMENT_ESCALATE")
        case["action_permitted"] = True
        case["action_idempotent"] = False
        self.assertIn("ACTION_NOT_IDEMPOTENT", decide(case, {"status":"PASS"}, risk_assessment(case))["blockers"])

    def test_unresolved_seeded_settlement_mismatch_cannot_auto_approve(self):
        case = {"id":"C1", "type":"SETTLEMENT_MISMATCH", "amount":"10000", "evidence_status":"VERIFIED", "authority_known":True, "action_permitted":True}
        result = decide(case, {"status":"PASS"}, risk_assessment(case))
        self.assertEqual(result["outcome"], "DEPARTMENT_ESCALATE")
        self.assertIn("RECONCILIATION_UNRESOLVED", result["blockers"])

    def test_high_financial_exposure_is_explained(self):
        risk = risk_assessment({"id":"C1", "amount":"125000", "type":"SETTLEMENT_MISMATCH", "report_count":1, "evidence_status":"VERIFIED"})
        self.assertEqual(risk["level"], "MEDIUM")
        self.assertTrue(any(f["dimension"] == "financial" for f in risk["factors"]))

    def test_non_inr_risk_requires_conversion_and_stays_manual(self):
        case = {"id":"C1", "amount":"1.00", "currency":"USD", "type":"SETTLEMENT_MISMATCH", "report_count":1, "evidence_status":"VERIFIED", "authority_known":True, "action_permitted":True}
        risk = risk_assessment(case)
        self.assertTrue(any("no USD conversion" in factor["explanation"] for factor in risk["factors"]))
        self.assertEqual(decide(case, {"status":"PASS"}, risk)["outcome"], "DEPARTMENT_ESCALATE")

    def test_extreme_decimal_precision_fails_as_validation_error(self):
        with self.assertRaises(ValueError):
            money("9" * 1000)

    def test_ticket_state_machine_rejects_skip_to_closed(self):
        with self.assertRaises(ValueError):
            validate_transition("CREATED", "CLOSED")
        validate_transition("RESOLVED", "VERIFIED")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.sqlite3"
        self.env = patch.dict(os.environ, {"CAUSE_AI_DB": str(self.db)})
        self.env.start()
        initialize(self.db, reseed=True)
        self.analyst = authenticate("analyst", "CauseDemo!2026")
        self.department = authenticate("department", "CauseDemo!2026")
        self.admin = authenticate("admin", "CauseDemo!2026")

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_roles_authenticate_and_bad_password_fails(self):
        self.assertEqual(self.analyst["role"], "analyst")
        self.assertEqual(self.analyst["tenant_id"], "DEMO-MERCHANT-01")
        self.assertEqual(self.department["role"], "department")
        self.assertIsNone(authenticate("analyst", "wrong"))

    def test_startup_automation_evaluates_all_pending_cases_once(self):
        from cause_ai.service import auto_evaluate_pending_cases
        first = auto_evaluate_pending_cases(self.analyst["tenant_id"])
        self.assertGreater(first["evaluated"], 0)
        self.assertTrue(all(item["outcome"] for item in first["outcomes"]))
        second = auto_evaluate_pending_cases(self.analyst["tenant_id"])
        self.assertEqual(second, {"evaluated": 0, "outcomes": []})

    def test_existing_v1_user_schema_migrates_to_demo_tenant(self):
        legacy_db = Path(self.temp.name) / "legacy-v1.sqlite3"
        salt, digest = hash_password("LegacyAccount!2026")
        conn = connect(legacy_db)
        try:
            conn.execute("CREATE TABLE schema_meta(version INTEGER NOT NULL)")
            conn.execute("INSERT INTO schema_meta(version) VALUES(1)")
            conn.execute("CREATE TABLE users(username TEXT PRIMARY KEY, role TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)")
            conn.execute("INSERT INTO users(username,role,salt,password_hash) VALUES('legacy-analyst','analyst',?,?)", (salt, digest))
            conn.commit()
        finally:
            conn.close()
        initialize(legacy_db)
        conn = connect(legacy_db)
        try:
            row = conn.execute("SELECT tenant_id FROM users WHERE username='legacy-analyst'").fetchone()
            version = conn.execute("SELECT version FROM schema_meta").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(row["tenant_id"], "DEMO-MERCHANT-01")
        self.assertEqual(version, 5)

    def test_fresh_database_records_current_schema_version(self):
        conn = connect(self.db)
        try:
            version = conn.execute("SELECT version FROM schema_meta").fetchone()[0]
            tenant_column = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        finally:
            conn.close()
        self.assertEqual(version, 5)
        self.assertIn("tenant_id", tenant_column)

    def test_policy_requires_independent_review_and_activation(self):
        reviewer = {"username": "policy-reviewer", "role": "admin", "tenant_id": self.admin["tenant_id"]}
        activator = {"username": "policy-activator", "role": "admin", "tenant_id": self.admin["tenant_id"]}
        proposal = propose_policy(self.admin, "DEMO-STANDARD-001", "2.0", "PASS", "Controlled internal policy source", "Evidence completeness policy with a reviewed change.", "2026-09-01", "Add an independently reviewed policy version for verification.")
        with self.assertRaises(ServiceError) as same_author:
            review_policy_proposal(self.admin, proposal["id"], "APPROVE", "The author cannot self approve this change.")
        self.assertEqual(same_author.exception.code, "SEGREGATION_OF_DUTIES")
        approved = review_policy_proposal(reviewer, proposal["id"], "APPROVE", "The policy source, effective date, and control impact were reviewed.")
        self.assertEqual(approved["state"], "APPROVED")
        with self.assertRaises(ServiceError) as same_reviewer:
            activate_policy_proposal(reviewer, proposal["id"])
        self.assertEqual(same_reviewer.exception.code, "SEGREGATION_OF_DUTIES")
        active = activate_policy_proposal(activator, proposal["id"])
        self.assertEqual(active["state"], "ACTIVE")
        self.assertEqual(list_policy_proposals(self.admin)[0]["state"], "ACTIVE")
        self.assertEqual(get_case("EXC-2026-000184", self.admin["tenant_id"])["policy"]["version"], "2.0")

    def test_controlled_tool_registry_excludes_financial_actions(self):
        registry = controlled_tool_registry()
        self.assertGreaterEqual(len(registry), 5)
        self.assertTrue(all(item["audit_required"] and item["roles"] for item in registry))
        self.assertFalse(any("refund" in item["operation"].casefold() or "settlement change" in item["operation"].casefold() for item in registry))

    def test_audit_hash_chain_is_immutable_and_verifiable(self):
        conn = connect(self.db)
        try:
            append_audit(conn, "admin", "admin", "CHAIN_TEST", "case", "CHAIN-1", "Verify audit hashing", tenant_id=self.admin["tenant_id"])
            conn.commit()
            integrity = audit_integrity_status(self.admin)
            self.assertTrue(integrity["valid"])
            self.assertGreaterEqual(integrity["verified_events"], 1)
            with self.assertRaisesRegex(__import__("sqlite3").IntegrityError, "append-only"):
                conn.execute("UPDATE audit_integrity SET event_sha256='bad' WHERE sequence=1")
        finally:
            conn.close()
    def test_detection_persists_immutable_tenant_scoped_financial_events(self):
        records = [
            {"record_type":"payment", "record_id":"EVENT-PAY-1", "payment_id":"EVENT-PAYMENT-1", "currency":"INR", "amount":"100.00", "status":"CAPTURED"},
            {"record_type":"settlement", "record_id":"EVENT-SET-1", "payment_id":"EVENT-PAYMENT-1", "currency":"INR", "amount":"90.00"},
        ]
        result = create_detected_cases(records, 7, self.analyst, "financial-events-v1")
        self.assertEqual(result["financial_events_ingested"], 2)
        case = get_case(result["created"][0], self.analyst["tenant_id"])
        self.assertTrue(all(item["financial_event_id"].startswith("FEV-") for item in case["evidence"]))
        conn = connect(self.db)
        try:
            rows = conn.execute("SELECT id,tenant_id,source_record_id,content_sha256,data_json FROM financial_events ORDER BY source_record_id").fetchall()
            self.assertEqual([(row["tenant_id"], row["source_record_id"]) for row in rows], [
                ("DEMO-MERCHANT-01", "EVENT-PAY-1"), ("DEMO-MERCHANT-01", "EVENT-SET-1"),
            ])
            self.assertEqual(len(rows[0]["content_sha256"]), 64)
            with self.assertRaisesRegex(__import__("sqlite3").IntegrityError, "immutable"):
                conn.execute("UPDATE financial_events SET data_json='{}' WHERE id=?", (rows[0]["id"],))
            before = conn.execute("SELECT content_sha256 FROM financial_events WHERE source_record_id='EVENT-SET-1'").fetchone()[0]
        finally:
            conn.close()
        changed = [dict(item) for item in records]
        changed[1]["amount"] = "80.00"
        with self.assertRaises(ServiceError) as conflict:
            create_detected_cases(changed, 7, self.analyst, "financial-events-rewrite")
        self.assertEqual(conflict.exception.code, "SOURCE_RECORD_CONFLICT")
        self.assertEqual(conflict.exception.status, 409)
        conn = connect(self.db)
        try:
            after = conn.execute("SELECT content_sha256 FROM financial_events WHERE source_record_id='EVENT-SET-1'").fetchone()[0]
            self.assertEqual(after, before)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM financial_events").fetchone()[0], 2)
        finally:
            conn.close()

    def test_razorpay_read_only_connector_normalizes_only_payment_fields(self):
        config = razorpay.RazorpayConfig("rzp_live_example", "secret-not-logged", "DEMO-MERCHANT-01")
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit):
                self.limit = limit
                return json.dumps({"items": [{"id": "pay_realshape1", "amount": 12345, "currency": "INR", "status": "captured", "created_at": 1_700_000_000, "email": "not-retained@example.com", "card": {"last4": "1234"}}]}).encode()
        class Opener:
            def __init__(self): self.request = None
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()
        opener = Opener()
        with patch("cause_ai.razorpay.build_opener", return_value=opener):
            records = razorpay.fetch_payments(config, from_epoch=1_700_000_000, to_epoch=1_700_000_100, count=1)
        self.assertEqual(records, [{"record_type": "payment", "record_id": "razorpay:payment:pay_realshape1", "payment_id": "pay_realshape1", "currency": "INR", "amount": "123.45", "status": "CAPTURED", "occurred_at": "2023-11-14T22:13:20+00:00"}])
        self.assertIn("/v1/payments?", opener.request.full_url)
        self.assertTrue(opener.request.get_header("Authorization").startswith("Basic "))
        self.assertNotIn("not-retained@example.com", json.dumps(records))

    def test_razorpay_live_import_requires_explicit_configuration(self):
        with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": "", "RAZORPAY_TENANT_ID": "", "RAZORPAY_MODE": "", "RAZORPAY_ALLOW_LIVE_READ_ONLY_IMPORT": ""}):
            with self.assertRaisesRegex(razorpay.RazorpayImportError, "not configured"):
                razorpay.RazorpayConfig.from_environment()

    def test_razorpay_test_import_requires_its_own_explicit_opt_in(self):
        test_environment = {
            "RAZORPAY_KEY_ID": "rzp_test_example", "RAZORPAY_KEY_SECRET": "test-secret",
            "RAZORPAY_TENANT_ID": "DEMO-MERCHANT-01", "RAZORPAY_MODE": "test",
            "RAZORPAY_ALLOW_TEST_READ_ONLY_IMPORT": "true", "RAZORPAY_ALLOW_LIVE_READ_ONLY_IMPORT": "",
        }
        with patch.dict(os.environ, test_environment):
            config = razorpay.RazorpayConfig.from_environment()
        self.assertEqual(config.mode, "test")
        self.assertEqual(config.tenant_id, "DEMO-MERCHANT-01")
        test_environment["RAZORPAY_ALLOW_TEST_READ_ONLY_IMPORT"] = ""
        with patch.dict(os.environ, test_environment):
            with self.assertRaisesRegex(razorpay.RazorpayImportError, "test import requires"):
                razorpay.RazorpayConfig.from_environment()

    def test_tenant_isolation_covers_dashboard_cases_tickets_audit_and_ticket_mutations(self):
        other_tenant = "MERCHANT-OTHER-02"
        other_case_id = "OTHER-TENANT-CASE"
        other_ticket_id = "OTHER-TENANT-TICKET"
        other_case = seed_cases()[0]
        other_case.update({"id": other_case_id, "payment_id": "PRIVATE-PAYMENT-OTHER", "subject_id": "PRIVATE-USER-OTHER"})
        salt, digest = hash_password("OtherTenant!2026")
        conn = connect(self.db)
        try:
            conn.execute("INSERT INTO tenants(id,status,created_at) VALUES(?,?,?)",
                         (other_tenant, "ACTIVE", "2026-09-25T00:00:00+00:00"))
            conn.execute("INSERT INTO users(username,role,salt,password_hash,tenant_id) VALUES(?,?,?,?,?)",
                         ("other-admin", "admin", salt, digest, other_tenant))
            conn.execute("INSERT INTO cases VALUES(?,?,?,?,?,?)",
                         (other_case_id, other_tenant, "ESCALATED", json.dumps(other_case), "2026-09-25T00:00:00+00:00", "2026-09-25T00:00:00+00:00"))
            other_ticket = {"id": other_ticket_id, "case_id": other_case_id, "status": "CREATED", "department": "Private Queue", "priority": "HIGH", "summary": "Private tenant investigation", "comments": []}
            conn.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?)",
                         (other_ticket_id, other_case_id, "CREATED", "Private Queue", "HIGH", json.dumps(other_ticket), "2026-09-25T00:00:00+00:00", "2026-09-25T00:00:00+00:00"))
            append_audit(conn, "other-admin", "admin", "PRIVATE_EVENT", "case", other_case_id,
                         "Private tenant audit event", {"secret": "must not leak"}, tenant_id=other_tenant)
            conn.commit()
        finally:
            conn.close()

        from cause_ai.service import audit_log, dashboard, get_case, list_cases, list_tickets
        other_actor = authenticate("other-admin", "OtherTenant!2026")
        self.assertEqual(other_actor["tenant_id"], other_tenant)
        from cause_ai.service import create_detected_cases
        same_identity_records = [
            {"record_type":"payment", "record_id":"OTHER-PAY-1", "payment_id":"PAY-10291", "currency":"INR", "amount":"10000", "status":"CAPTURED", "subject_type":"COMPANY", "subject_id":"SYN-COM-000184", "email_id":"synthetic.case000184@example.invalid"},
            {"record_type":"fee", "record_id":"OTHER-FEE-1", "payment_id":"PAY-10291", "currency":"INR", "amount":"250", "subject_type":"COMPANY", "subject_id":"SYN-COM-000184", "email_id":"synthetic.case000184@example.invalid"},
            {"record_type":"settlement", "record_id":"OTHER-SET-1", "payment_id":"PAY-10291", "currency":"INR", "amount":"9500", "subject_type":"COMPANY", "subject_id":"SYN-COM-000184", "email_id":"synthetic.case000184@example.invalid"},
        ]
        isolated_report = create_detected_cases(same_identity_records, 7, other_actor, "other-tenants-same-identity", "1.1")
        self.assertEqual(isolated_report["outcomes"][0]["prior_case_ids"], [])
        self.assertNotIn(other_case_id, {case["id"] for case in dashboard(self.analyst["tenant_id"])["cases"]})
        self.assertNotIn(other_ticket_id, {ticket["id"] for ticket in dashboard(self.analyst["tenant_id"])["tickets"]})
        self.assertNotIn(other_case_id, {case["id"] for case in list_cases({}, self.analyst["tenant_id"])})
        self.assertIsNone(get_case(other_case_id, self.analyst["tenant_id"]))
        self.assertNotIn(other_ticket_id, {ticket["id"] for ticket in list_tickets(self.analyst["tenant_id"])})
        self.assertNotIn("PRIVATE_EVENT", {event["action"] for event in audit_log(500, self.analyst["tenant_id"])})
        self.assertEqual(get_case(other_case_id, other_tenant)["id"], other_case_id)
        with self.assertRaises(ServiceError) as denied:
            respond_to_ticket(other_ticket_id, self.department, "Attempt to access another tenant case")
        self.assertEqual(denied.exception.status, 404)
        self.assertEqual(respond_to_ticket(other_ticket_id, other_actor, "Authorized private tenant investigation") ["status"], "UNDER_REVIEW")

    def test_regulatory_discovery_captures_immutable_hash_and_deduplicates(self):
        pages = {
            "https://www.npci.org.in/circulars/upi": (b'<a href="/uploads/UPI-circular-77.pdf">UPI Circular 77 implementation</a><a href="/uploads/OC-226A.pdf"></a><a href="https://evil.example/fake.pdf">UPI circular fake</a>', "text/html"),
            "https://www.rbi.org.in/Scripts/FS_Notification.aspx?fn=9": (b'<a href="/Scripts/FS_Notification.aspx?fn=9">Payment systems notifications</a><a href="/Scripts/FS_Notification.aspx?Id=13374&fn=9&Mode=0">UPI payment notification 2026</a><a href="/Scripts/NotificationUser.aspx">Notifications</a>', "text/html"),
            "https://www.rbi.org.in/Scripts/FS_Notification.aspx?Id=13374&fn=9&Mode=0": (b"RBI publication detail", "text/html"),
            "https://www.npci.org.in/uploads/UPI-circular-77.pdf": (b"immutable regulator PDF bytes", "application/pdf"),
            "https://www.npci.org.in/uploads/OC-226A.pdf": (b"second immutable regulator PDF", "application/pdf"),
        }
        def fake_fetch(url, limit):
            body, content_type = pages[url]
            self.assertLessEqual(len(body), limit)
            return body, content_type, url
        first = regulatory.scan_sources(fake_fetch)
        second = regulatory.scan_sources(fake_fetch)
        self.assertEqual(first["discovered"], 3)
        self.assertEqual(second["discovered"], 0)
        item = next(doc for doc in regulatory.inbox()["documents"] if doc["url"] == "https://www.npci.org.in/uploads/UPI-circular-77.pdf")
        self.assertEqual(item["content_sha256"], __import__("hashlib").sha256(pages["https://www.npci.org.in/uploads/UPI-circular-77.pdf"][0]).hexdigest())
        self.assertEqual(item["review_status"], "REVIEW_REQUIRED")
        self.assertNotIn("content_integrity", item)
        self.assertNotIn("stored_path", item)
        self.assertTrue((self.db.parent / "regulatory" / "objects" / f"{item['content_sha256']}.pdf").is_file())

    def test_regulatory_review_is_authorized_audited_and_never_activates_policy(self):
        raw = b"Verified official test publication body with source citation"
        digest = __import__("hashlib").sha256(raw).hexdigest()
        object_path = regulatory._data_dir() / f"{digest}.pdf"
        object_path.write_bytes(raw)
        conn = connect()
        try:
            conn.execute("INSERT INTO regulatory_sources(source_id,name,url) VALUES('TEST','Official test','https://www.npci.org.in')")
            conn.execute("INSERT INTO regulatory_documents(id,source_id,title,url,content_sha256,stored_path,content_type,discovered_at) VALUES('REG-TEST','TEST','Test circular','https://www.npci.org.in/test',?,?,?,?)", (digest, str(object_path), "application/pdf", "2026-09-25T00:00:00+00:00"))
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(ServiceError) as ctx:
            regulatory.review_document("REG-TEST", "RELEVANT", "This rationale is long enough", self.analyst)
        self.assertEqual(ctx.exception.status, 403)
        reviewed = regulatory.review_document("REG-TEST", "NEEDS_LEGAL_REVIEW", "Route to counsel to determine entity applicability", self.admin)
        self.assertFalse(reviewed["policy_activated"])
        reviewed = regulatory.review_document("REG-TEST", "NOT_APPLICABLE", "Counsel confirmed this notice does not apply to our role", self.admin)
        self.assertEqual(reviewed["review_status"], "NOT_APPLICABLE")
        with self.assertRaises(ServiceError) as ctx:
            regulatory.review_document("REG-TEST", "RELEVANT", "A review after final disposition is prohibited", self.admin)
        self.assertEqual(ctx.exception.status, 409)
        review_events = [x for x in __import__("cause_ai.service", fromlist=["audit_log"]).audit_log(50) if x["object_id"] == "REG-TEST"]
        self.assertEqual(len(review_events), 2)
        self.assertTrue(all(event["details"]["content_integrity"] == "VERIFIED" for event in review_events))

    def test_regulatory_review_fails_closed_on_changed_missing_or_out_of_store_content(self):
        regulatory.initialize_sources()
        root = regulatory._data_dir()
        raw = b"Original official document bytes for integrity check"
        digest = __import__("hashlib").sha256(raw).hexdigest()
        tampered_path = root / f"{digest}.bin"
        tampered_path.write_bytes(raw)
        tampered_path.write_bytes(b"modified bytes")
        external_path = self.db.parent / "external.bin"
        external_path.write_bytes(raw)
        conn = connect()
        try:
            rows = [
                ("REG-TAMPERED", "Changed content", digest, str(tampered_path)),
                ("REG-MISSING-CAPTURE", "No staged file", digest, None),
                ("REG-OUTSIDE", "Outside object store", digest, str(external_path)),
            ]
            for doc_id, title, content_hash, stored_path in rows:
                conn.execute("INSERT INTO regulatory_documents(id,source_id,title,url,content_sha256,stored_path,content_type,discovered_at) VALUES(?,?,?,?,?,?,?,?)",
                             (doc_id, "NPCI_UPI", title, f"https://www.npci.org.in/{doc_id}", content_hash, stored_path, "application/pdf", "2026-09-25T00:00:00+00:00"))
            conn.commit()
        finally:
            conn.close()
        docs = {doc["id"]: doc for doc in regulatory.inbox()["documents"]}
        self.assertTrue(all("content_integrity" not in doc and "stored_path" not in doc for doc in docs.values()))
        integrity_rows = {doc_id: {"stored_path": path, "content_sha256": digest} for doc_id, path in (
            ("REG-TAMPERED", str(tampered_path)), ("REG-MISSING-CAPTURE", None), ("REG-OUTSIDE", str(external_path)))}
        self.assertEqual(regulatory._content_integrity(integrity_rows["REG-TAMPERED"]), "HASH_MISMATCH")
        self.assertEqual(regulatory._content_integrity(integrity_rows["REG-MISSING-CAPTURE"]), "MISSING")
        self.assertEqual(regulatory._content_integrity(integrity_rows["REG-OUTSIDE"]), "OUTSIDE_OBJECT_STORE")
        with patch.object(Path, "is_symlink", return_value=True):
            self.assertEqual(regulatory._content_integrity(integrity_rows["REG-TAMPERED"]), "SYMLINK_REJECTED")
        self.assertNotIn("stored_path", docs["REG-TAMPERED"])
        for doc_id in ("REG-TAMPERED", "REG-MISSING-CAPTURE", "REG-OUTSIDE"):
            with self.subTest(document_id=doc_id), self.assertRaises(ServiceError) as ctx:
                regulatory.review_document(doc_id, "RELEVANT", "This review rationale is long enough", self.admin)
            self.assertEqual(ctx.exception.status, 409)

    def test_regulatory_url_allowlist_rejects_untrusted_and_plain_http(self):
        self.assertFalse(regulatory._allowed("https://evil.example/notices"))
        self.assertFalse(regulatory._allowed("http://www.npci.org.in/circulars"))
        self.assertFalse(regulatory._allowed("https://www.rbi.org.in.evil.example/"))
        with self.assertRaisesRegex(ValueError, "allowlist"):
            regulatory._fetch("https://evil.example/file.pdf", 100)

    def test_regulatory_redirect_is_rejected_before_following_untrusted_host(self):
        handler = regulatory._AllowlistedRedirectHandler()
        request = urllib.request.Request("https://www.rbi.org.in/Scripts/FS_Notification.aspx?fn=9")
        with self.assertRaisesRegex(ValueError, "redirected outside the allowlist"):
            handler.redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1/internal")
        same_host = handler.redirect_request(request, None, 302, "Found", {}, "/Scripts/FS_Notification.aspx?Id=1")
        self.assertEqual(same_host.full_url, "https://www.rbi.org.in/Scripts/FS_Notification.aspx?Id=1")

    def test_regulatory_html_fingerprint_ignores_script_and_markup_noise(self):
        pages = {
            "https://www.npci.org.in/circulars/upi": (b"<html>no linked circulars</html>", "text/html"),
            "https://www.rbi.org.in/Scripts/FS_Notification.aspx?fn=9": (b'<a href="/Scripts/FS_Notification.aspx?Id=90&fn=9">UPI limit circular 90</a>', "text/html"),
            "https://www.rbi.org.in/Scripts/FS_Notification.aspx?Id=90&fn=9": (b"<script>varying-1</script><p>UPI limit circular 90 text</p>", "text/html"),
        }
        def fake_fetch(url, limit):
            body, kind = pages[url]
            return body, kind, url
        self.assertEqual(regulatory.scan_sources(fake_fetch)["discovered"], 1)
        pages["https://www.rbi.org.in/Scripts/FS_Notification.aspx?Id=90&fn=9"] = (b"  <script>varying-2</script>  <p>UPI   limit circular 90 text </p>", "text/html")
        self.assertEqual(regulatory.scan_sources(fake_fetch)["discovered"], 0)
        self.assertEqual(len(regulatory.inbox()["documents"]), 1)

    def test_regulatory_source_failures_are_visible_not_reported_as_empty_success(self):
        def offline(url, limit):
            raise OSError("source unavailable")
        result = regulatory.scan_sources(offline)
        self.assertEqual([source["status"] for source in result["sources"]], ["ERROR", "ERROR"])
        self.assertTrue(all(source["error"] == "source unavailable" for source in result["sources"]))

    def test_dynamic_npci_index_without_static_links_is_not_marked_healthy(self):
        pages = {
            "https://www.npci.org.in/circulars/upi": (b"<html><div id='root'>Loading data in client</div></html>", "text/html"),
            "https://www.rbi.org.in/Scripts/FS_Notification.aspx?fn=9": (b"<html>No matching notices</html>", "text/html"),
        }
        result = regulatory.scan_sources(lambda url, limit: (*pages[url], url))
        npci = next(source for source in result["sources"] if source["id"] == "NPCI_UPI")
        self.assertEqual(npci["status"], "PARSER_LIMITED")
        self.assertIn("dynamically rendered", npci["error"])

    def test_evaluation_creates_audited_escalation_ticket_and_is_idempotent(self):
        first = evaluate_case("EXC-2026-000187", self.analyst, "test-key-1")
        second = evaluate_case("EXC-2026-000187", self.analyst, "test-key-1")
        third = evaluate_case("EXC-2026-000187", self.analyst, "test-key-2")
        self.assertEqual(first["decision"]["outcome"], "DEPARTMENT_ESCALATE")
        self.assertEqual(first["decision"], second["decision"])
        self.assertEqual(first["decision"], third["decision"])
        self.assertEqual(len(get_case("EXC-2026-000187")["tickets"]), 2)
        conn = connect()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_events WHERE object_id=?", ("EXC-2026-000187",)).fetchone()[0], 1)
        finally:
            conn.close()

    def test_seeded_unresolved_shortfall_is_never_auto_approved(self):
        result = evaluate_case("EXC-2026-000184", self.analyst)
        self.assertEqual(result["risk"]["level"], "LOW")
        self.assertEqual(result["decision"]["outcome"], "DEPARTMENT_ESCALATE")
        self.assertIn("RECONCILIATION_UNRESOLVED", result["decision"]["blockers"])
        self.assertEqual(result["case"]["tickets"][-1]["status"], "CREATED")

    def test_every_seeded_case_has_one_governed_outcome_and_escalations_have_tickets(self):
        expected = {
            "EXC-2026-000184": "DEPARTMENT_ESCALATE",
            "EXC-2026-000185": "DEPARTMENT_ESCALATE",
            "EXC-2026-000186": "DEPARTMENT_ESCALATE",
            "EXC-2026-000187": "DEPARTMENT_ESCALATE",
            "EXC-2026-000188": "FRAUD_ESCALATE",
            "EXC-2026-000189": "REJECT",
            "EXC-2026-000190": "DEPARTMENT_ESCALATE",
            "EXC-2026-000191": "DEPARTMENT_ESCALATE",
        }
        for case_id, outcome in expected.items():
            with self.subTest(case_id=case_id):
                result = evaluate_case(case_id, self.analyst)
                self.assertEqual(result["decision"]["outcome"], outcome)
                self.assertIn(outcome, {"AUTO_APPROVE", "REJECT", "FRAUD_ESCALATE", "DEPARTMENT_ESCALATE"})
                if outcome.endswith("ESCALATE"):
                    self.assertTrue(result["case"]["tickets"])
        fraud_case = get_case("EXC-2026-000188")
        self.assertNotIn("fraud_confirmed", fraud_case)
        self.assertEqual(fraud_case["decision"]["outcome"], "FRAUD_ESCALATE")

    def test_decision_keeps_the_policy_version_used_at_evaluation(self):
        conn = connect()
        try:
            policy_row = conn.execute("SELECT data_json FROM policies WHERE id='DEMO-FEE-003'").fetchone()
            policy = json.loads(policy_row[0])
            policy.update({"version":"2.1-test", "status":"FAIL"})
            conn.execute("UPDATE policies SET version=?,status=?,data_json=? WHERE id=?",
                         (policy["version"], policy["status"], json.dumps(policy), "DEMO-FEE-003"))
            conn.commit()
        finally:
            conn.close()
        evaluated = evaluate_case("EXC-2026-000189", self.analyst)
        self.assertEqual(evaluated["decision"]["outcome"], "REJECT")
        self.assertEqual(evaluated["decision"]["policy_version"], "2.1-test")
        conn = connect()
        try:
            policy = json.loads(conn.execute("SELECT data_json FROM policies WHERE id='DEMO-FEE-003'").fetchone()[0])
            policy["version"] = "2.2-test"
            conn.execute("UPDATE policies SET version=?,data_json=? WHERE id=?",
                         (policy["version"], json.dumps(policy), "DEMO-FEE-003"))
            conn.commit()
        finally:
            conn.close()
        replay = evaluate_case("EXC-2026-000189", self.analyst)
        self.assertEqual(replay["decision"]["policy_version"], "2.1-test")

    def test_idempotency_keys_are_scoped_to_case(self):
        first = evaluate_case("EXC-2026-000186", self.analyst, "shared-key")
        second = evaluate_case("EXC-2026-000188", self.analyst, "shared-key")
        self.assertNotEqual(first["case"]["id"], second["case"]["id"])
        self.assertEqual(second["decision"]["outcome"], "FRAUD_ESCALATE")

    def test_department_response_resolution_and_verification_workflow(self):
        evaluated = evaluate_case("EXC-2026-000186", self.analyst)
        ticket = evaluated["case"]["tickets"][-1]
        ticket_id = ticket["id"]
        with self.assertRaises(ServiceError):
            evaluate_case("EXC-2026-000184", self.department)
        response = respond_to_ticket(ticket_id, self.department, "We confirmed the settlement is missing from the source ledger.")
        self.assertEqual(response["status"], "UNDER_REVIEW")
        repeated_response = respond_to_ticket(ticket_id, self.department, "A follow-up request has been sent for authoritative settlement evidence.")
        self.assertEqual(len(repeated_response["comments"]), 2)
        case = get_case("EXC-2026-000186")
        evidence_id = next(e["id"] for e in case["evidence"] if e["status"] == "VERIFIED")
        resolved = resolve_ticket(ticket_id, self.department, "Settlement record request has been submitted to operations for correction.", [evidence_id])
        self.assertEqual(resolved["ticket"]["status"], "RESOLVED")
        checked = verify_ticket(ticket_id, self.analyst)
        self.assertEqual(checked["verification"]["status"], "PASSED")
        self.assertEqual(checked["ticket"]["status"], "CLOSED")
        self.assertEqual(checked["case"]["status"], "CLOSED")
        final_case = get_case("EXC-2026-000186")
        self.assertTrue(any(event["action"] == "DEPARTMENT_RESPONSE" for event in final_case["audit"]))
        self.assertTrue(any(event["action"] == "TICKET_CLOSED" for event in final_case["audit"]))

    def test_sla_reminders_are_idempotent_per_day(self):
        now = datetime.now(timezone.utc) + timedelta(days=2)
        first = run_reminders(self.analyst, now)
        second = run_reminders(self.analyst, now + timedelta(hours=1))
        later = run_reminders(self.analyst, now + timedelta(days=1, hours=1))
        self.assertEqual(first["count"], 2)
        self.assertEqual(second["count"], 0)
        self.assertEqual(later["count"], 2)

    def test_department_role_cannot_trigger_reminders(self):
        with self.assertRaises(ServiceError) as ctx:
            run_reminders(self.department)
        self.assertEqual(ctx.exception.status, 403)

    def test_resolution_requires_verified_case_evidence(self):
        evaluated = evaluate_case("EXC-2026-000187", self.analyst)
        ticket = evaluated["case"]["tickets"][-1]
        respond_to_ticket(ticket["id"], self.department, "We have started investigation and requested bank proof.")
        with self.assertRaises(ServiceError):
            resolve_ticket(ticket["id"], self.department, "The resolution cites evidence that does not belong to the case.", ["EV-FAKE"])

    def test_audit_log_cannot_be_updated_or_deleted(self):
        evaluate_case("EXC-2026-000184", self.analyst)
        conn = connect()
        try:
            with self.assertRaises(Exception):
                conn.execute("UPDATE audit_events SET reason='edited' WHERE seq=1")
            conn.rollback()
            with self.assertRaises(Exception):
                conn.execute("DELETE FROM audit_events WHERE seq=1")
        finally:
            conn.close()

    def test_case_search_filters(self):
        cases = list_cases({"q":"PAY-10331", "risk":"HIGH"})
        self.assertEqual([c["id"] for c in cases], ["EXC-2026-000188"])

    def test_case_identity_fields_are_present_and_synthetic_for_seed_data(self):
        company_case = get_case("EXC-2026-000184")
        user_case = get_case("EXC-2026-000185")
        self.assertEqual(company_case["subject_type"], "COMPANY")
        self.assertEqual(company_case["subject_id"], "SYN-COM-000184")
        self.assertEqual(user_case["subject_type"], "USER")
        self.assertEqual(user_case["subject_id"], "SYN-USE-000185")
        self.assertTrue(company_case["email_id"].endswith("@example.invalid"))
        self.assertEqual(list_cases({"q":"synthetic.case000184"})[0]["id"], company_case["id"])

    def test_detected_drafts_keep_evidence_unverified_and_import_is_idempotent(self):
        records = [
            {"record_type":"payment","record_id":"NEW-PAY-1","payment_id":"NEW-PAY-1","amount":"10000","status":"CAPTURED"},
            {"record_type":"settlement","record_id":"NEW-SET-1","payment_id":"NEW-PAY-1","amount":"9000"},
        ]
        result = create_detected_cases(records, 7, self.analyst)
        repeated = create_detected_cases(records, 7, self.analyst)
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["duplicate_run"])
        self.assertTrue(repeated["duplicate_run"])
        self.assertEqual(result["created"], repeated["created"])
        case = get_case(result["created"][0])
        self.assertEqual(case["evidence_status"], "UNVERIFIED")
        self.assertIsNone(case["subject_type"])
        self.assertIsNone(case["subject_id"])
        self.assertIsNone(case["email_id"])
        self.assertTrue(all(item["status"] == "UNVERIFIED" for item in case["evidence"]))
        decision = evaluate_case(case["id"], self.analyst)["decision"]
        self.assertEqual(decision["outcome"], "DEPARTMENT_ESCALATE")
        self.assertIn("INSUFFICIENT_EVIDENCE", decision["blockers"])

    def test_detection_automatically_escalates_and_links_repeat_request_history(self):
        records = [
            {"record_type":"payment", "record_id":"REPEAT-PAY", "payment_id":"REPEAT-1", "currency":"INR", "amount":"10000", "status":"CAPTURED", "subject_type":"COMPANY", "subject_id":"SYN-COMPANY-77", "email_id":"finance77@example.invalid"},
            {"record_type":"settlement", "record_id":"REPEAT-SET", "payment_id":"REPEAT-1", "currency":"INR", "amount":"9000", "subject_type":"COMPANY", "subject_id":"SYN-COMPANY-77", "email_id":"finance77@example.invalid"},
        ]
        first = create_detected_cases(records, 7, self.analyst, "submit-1", "1.1")
        retry = create_detected_cases(records, 7, self.analyst, "submit-1", "1.1")
        changed_replay = [dict(item) for item in records]
        changed_replay[1]["amount"] = "8000"
        with self.assertRaises(ServiceError) as conflict:
            create_detected_cases(changed_replay, 7, self.analyst, "submit-1", "1.1")
        self.assertEqual(conflict.exception.status, 409)
        second = create_detected_cases(records, 7, self.analyst, "submit-2", "1.1")
        self.assertEqual(first["outcomes"][0]["outcome"], "DEPARTMENT_ESCALATE")
        self.assertTrue(first["outcomes"][0]["ticket_id"])
        self.assertTrue(retry["duplicate_run"])
        self.assertFalse(second["duplicate_run"])
        repeated_case = get_case(second["created"][0])
        previous_id = first["created"][0]
        self.assertIn("REPEAT_REQUEST_REVIEW", repeated_case["decision"]["blockers"])
        self.assertEqual(repeated_case["repeat_request"]["prior_case_id"], previous_id)
        self.assertEqual(repeated_case["subject_history"][0]["status"], "ESCALATED")
        self.assertEqual(repeated_case["tickets"][0]["investigation_data"]["prior_cases"][0]["id"], previous_id)
        previous = get_case(previous_id)
        self.assertEqual(previous["report_count"], 2)
        self.assertIn(repeated_case["id"], previous["related_cases"])

    def test_suspicious_detection_auto_routes_to_fraud_review_without_confirming_fraud(self):
        records = [
            {"record_type":"payment", "record_id":"SUSP-P", "payment_id":"SUSP-1", "amount":"100", "status":"CAPTURED", "suspicious_signal":True, "subject_type":"USER", "subject_id":"SYN-USER-90"},
            {"record_type":"settlement", "record_id":"SUSP-S", "payment_id":"SUSP-1", "amount":"100", "subject_type":"USER", "subject_id":"SYN-USER-90"},
        ]
        result = create_detected_cases(records, 7, self.analyst, "fraud-submission", "1.1")
        case = get_case(result["created"][0])
        self.assertEqual(case["decision"]["outcome"], "FRAUD_ESCALATE")
        self.assertEqual(case["tickets"][0]["department"], "Risk/Fraud")
        self.assertNotIn("confirmed_fraud", case)

    def test_department_cannot_verify_resolution(self):
        with self.assertRaises(ServiceError) as ctx:
            verify_ticket("TKT-2026-0041", self.department)
        self.assertEqual(ctx.exception.status, 403)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.temp.name) / "http.sqlite3"
        cls.env = patch.dict(os.environ, {"CAUSE_AI_DB": str(cls.db)})
        cls.env.start()
        initialize(cls.db, reseed=True)
        salt, digest = hash_password("IsolatedHttp!2026")
        conn = connect(cls.db)
        try:
            conn.execute("INSERT INTO users(username,role,salt,password_hash,tenant_id) VALUES(?,?,?,?,?)",
                         ("isolated-http", "analyst", salt, digest, "HTTP-OTHER-TENANT"))
            conn.commit()
        finally:
            conn.close()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), CauseAIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.env.stop()
        cls.temp.cleanup()

    def request(self, path, method="GET", data=None, opener=None, headers=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers=headers or {})
        client = opener or urllib.request.build_opener()
        return client.open(req)

    def test_health_and_static_app(self):
        health_response = self.request("/api/health")
        health = json.loads(health_response.read())
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["schema_version"], 5)
        self.assertEqual(health["database"], "sqlite")
        self.assertRegex(health_response.headers["X-Request-ID"], r"^[0-9a-f]{24}$")
        ready = json.loads(self.request("/api/ready").read())
        self.assertEqual(ready, {"status":"ready", "mode":"synthetic-demo", "schema_version":5})
        page = self.request("/").read().decode()
        self.assertIn("Cause AI", page)
        self.assertEqual(self.request("/app.js").status, 200)
        sample = json.loads(self.request("/samples/razorpay_public_schema_sample.json").read())
        self.assertEqual([record["record_type"] for record in sample], ["payment", "fee", "settlement"])
        self.assertTrue(all(record["email_id"].endswith("@example.invalid") for record in sample))
        legal = self.request("/legal.html").read().decode()
        self.assertIn("Legal Terms and Privacy Notice", legal)
        self.assertIn("Pre launch legal template", legal)
        css = self.request("/styles.css").read().decode()
        self.assertIn("[hidden]{display:none!important}", css)
        client_script = self.request("/app.js").read().decode()
        self.assertNotIn("style=", client_script)
        self.assertIn("Detection lab", page + client_script)

    def test_encoded_traversal_does_not_escape_static_root(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/%2e%2e/README.md")
        self.assertEqual(ctx.exception.code, 404)

    def test_api_requires_auth_and_invalid_login_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/dashboard")
        self.assertEqual(ctx.exception.code, 401)

    def test_invalid_content_length_is_rejected_without_reading_the_stream(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/login", "POST", {"username": "analyst"}, headers={"Content-Length": "-1"})
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(json.loads(ctx.exception.read())["error"]["code"], "INVALID_CONTENT_LENGTH")

    def test_http_tenant_is_taken_from_authenticated_user_and_scopes_all_case_routes(self):
        from http.cookiejar import CookieJar
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        login = json.loads(self.request("/api/login", "POST", {"username":"isolated-http", "password":"IsolatedHttp!2026"}, client).read())
        self.assertEqual(login["user"]["tenant_id"], "HTTP-OTHER-TENANT")
        dashboard = json.loads(self.request("/api/dashboard", opener=client).read())
        self.assertEqual(dashboard["total_cases"], 0)
        self.assertEqual(json.loads(self.request("/api/cases", opener=client).read())["items"], [])
        self.assertEqual(json.loads(self.request("/api/tickets", opener=client).read())["items"], [])
        self.assertEqual(json.loads(self.request("/api/audit", opener=client).read())["items"], [])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/cases/EXC-2026-000184", opener=client)
        self.assertEqual(ctx.exception.code, 404)

    def test_regulatory_inbox_and_scan_are_admin_only(self):
        from http.cookiejar import CookieJar
        analyst = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"analyst","password":"CauseDemo!2026"}, analyst)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/regulatory/inbox", opener=analyst)
        self.assertEqual(ctx.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/regulatory/scan", "POST", {}, analyst)
        self.assertEqual(ctx.exception.code, 403)
        admin = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"admin","password":"CauseDemo!2026"}, admin)
        inbox = json.loads(self.request("/api/regulatory/inbox", opener=admin).read())
        self.assertEqual(inbox["policy_activation"], "NOT_SUPPORTED: discovered documents never activate policy")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/regulatory/documents/REG-MISSING/review", "POST", {"verdict":"ACTIVATE","reason":"activate now please"}, admin)
        self.assertEqual(ctx.exception.code, 400)

    def test_policy_and_tool_governance_endpoints_are_admin_controlled(self):
        from http.cookiejar import CookieJar
        analyst = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"analyst","password":"CauseDemo!2026"}, analyst)
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.request("/api/tools", opener=analyst)
        self.assertEqual(denied.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as denied_integrity:
            self.request("/api/audit/integrity", opener=analyst)
        self.assertEqual(denied_integrity.exception.code, 403)
        admin = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"admin","password":"CauseDemo!2026"}, admin)
        tools = json.loads(self.request("/api/tools", opener=admin).read())["items"]
        self.assertTrue(all(item["audit_required"] for item in tools))
        integrity = json.loads(self.request("/api/audit/integrity", opener=admin).read())
        self.assertTrue(integrity["valid"])
        proposed = json.loads(self.request("/api/policies/proposals", "POST", {
            "policy_id":"DEMO-STANDARD-001", "version":"3.0", "status":"PASS",
            "source":"Controlled internal policy source", "description":"A reviewed policy endpoint test description.",
            "effective_from":"2026-09-01", "rationale":"Exercise the protected policy proposal endpoint through HTTP."
        }, admin).read())["proposal"]
        with self.assertRaises(urllib.error.HTTPError) as self_review:
            self.request(f"/api/policies/proposals/{proposed['id']}/review", "POST", {
                "verdict":"APPROVE", "reason":"The proposal author cannot complete its own review."
            }, admin)
        self.assertEqual(self_review.exception.code, 409)

    def test_razorpay_import_is_admin_only_and_fails_closed_without_live_configuration(self):
        from http.cookiejar import CookieJar
        analyst = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"analyst","password":"CauseDemo!2026"}, analyst)
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.request("/api/integrations/razorpay/payments/import", "POST", {}, analyst)
        self.assertEqual(denied.exception.code, 403)

        admin = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"admin","password":"CauseDemo!2026"}, admin)
        blank_config = {"RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": "", "RAZORPAY_TENANT_ID": "", "RAZORPAY_MODE": "", "RAZORPAY_ALLOW_LIVE_READ_ONLY_IMPORT": ""}
        with patch.dict(os.environ, blank_config):
            with self.assertRaises(urllib.error.HTTPError) as unavailable:
                self.request("/api/integrations/razorpay/payments/import", "POST", {}, admin)
        self.assertEqual(unavailable.exception.code, 503)
        self.assertEqual(json.loads(unavailable.exception.read())["error"]["code"], "RAZORPAY_IMPORT_UNAVAILABLE")

    def test_login_dashboard_and_role_permissions_over_http(self):
        from http.cookiejar import CookieJar
        
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"analyst","password":"CauseDemo!2026"}, client)
        dashboard = json.loads(self.request("/api/dashboard", opener=client).read())
        self.assertEqual(dashboard["total_cases"], 9)
        self.request("/api/cases/EXC-2026-000184/evaluate", "POST", {}, client, {"Idempotency-Key":"http-test-1"})
        dept = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"department","password":"CauseDemo!2026"}, dept)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/cases/EXC-2026-000185/evaluate", "POST", {}, dept)
        self.assertEqual(ctx.exception.code, 403)

    def test_detection_preview_api_requires_analyst_and_does_not_persist(self):
        from http.cookiejar import CookieJar
        analyst = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"analyst","password":"CauseDemo!2026"}, analyst)
        records = [
            {"record_type":"payment","record_id":"PAY-X","payment_id":"PX","amount":"1000","status":"CAPTURED"},
            {"record_type":"settlement","record_id":"SET-X","payment_id":"PX","amount":"900"},
        ]
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/detection/preview", "POST", {"records":records}, analyst)
        self.assertEqual(ctx.exception.code, 400)
        result = json.loads(self.request("/api/detection/preview", "POST", {"schema_version":"1.0","records":records}, analyst).read())
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["persisted"])
        self.assertEqual(result["findings"][0]["type"], "SETTLEMENT_MISMATCH")
        committed = json.loads(self.request("/api/detection/commit", "POST", {"schema_version":"1.0","records":records}, analyst).read())
        self.assertEqual(committed["count"], 1)
        self.assertTrue(committed["persisted"])
        self.assertEqual(committed["evidence_status"], "UNVERIFIED")
        department = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.request("/api/login", "POST", {"username":"department","password":"CauseDemo!2026"}, department)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/detection/preview", "POST", {"schema_version":"1.0","records":records}, department)
        self.assertEqual(ctx.exception.code, 403)

    def test_cross_origin_post_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/login", "POST", {"username":"analyst","password":"CauseDemo!2026"}, headers={"Origin":"https://attacker.invalid"})
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)


