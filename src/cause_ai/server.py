"""Small standard-library HTTP server for the local synthetic-data demo."""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .database import DEFAULT_DB, connect, initialize
from .domain import detect_exceptions
from .service import (ServiceError, audit_log, authenticate, dashboard, evaluate_case,
                      get_case, list_cases, list_tickets, respond_to_ticket,
                      resolve_ticket, run_reminders, verify_ticket, create_detected_cases,
                      list_policy_proposals, propose_policy, review_policy_proposal, activate_policy_proposal,
                      audit_integrity_status, auto_evaluate_pending_cases, investigate_case)
from .tool_registry import controlled_tool_registry
from . import regulatory, razorpay

STATIC = Path(__file__).with_name("static")
SESSIONS: dict[str, dict[str, str]] = {}
LOGIN_FAILURES: dict[str, list[float]] = {}
SESSION_LOCK = threading.Lock()
LOGIN_FAILURE_LOCK = threading.Lock()
RUNTIME_ENV = os.environ.get("CAUSE_AI_ENV", "demo").strip().casefold()
DEMO_MODE = RUNTIME_ENV == "demo" and os.environ.get("CAUSE_AI_DEMO", "true").casefold() == "true"
MAX_BODY_BYTES = 1_048_576
MAX_ACTIVE_SESSIONS = 10_000


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


SESSION_TTL_SECONDS = _bounded_int("CAUSE_AI_SESSION_TTL_SECONDS", 28_800, 300, 86_400)
COOKIE_SECURE = os.environ.get("CAUSE_AI_COOKIE_SECURE", "false").casefold() == "true"
logger = logging.getLogger("cause_ai.http")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")


class CauseAIHandler(BaseHTTPRequestHandler):
    server_version = "CauseAI"
    sys_version = ""

    def log_message(self, fmt: str, *args: object) -> None:
        logger.info("request_id=%s client=%s %s", getattr(self, "request_id", "unassigned"), self.client_address[0], fmt % args)

    def _headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", getattr(self, "request_id", "unassigned"))

    def _json(self, payload: object, status: int = 200, extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: str, message: str, status: int) -> None:
        self._json({"error": {"code": code, "message": message, "request_id": getattr(self, "request_id", "unassigned")}}, status)

    def _body(self) -> dict:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise ServiceError("INVALID_CONTENT_LENGTH", "Content-Length must be a non-negative integer") from None
        if length < 0:
            raise ServiceError("INVALID_CONTENT_LENGTH", "Content-Length must be a non-negative integer")
        if length > MAX_BODY_BYTES:
            raise ServiceError("PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB", 413)
        if length == 0:
            return {}
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ServiceError("INVALID_JSON", "Request body must be valid JSON") from None
        if not isinstance(value, dict):
            raise ServiceError("INVALID_BODY", "Request body must be a JSON object")
        return value

    def _actor(self) -> dict[str, str] | None:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie.get("cause_session")
        except Exception:
            token = None
        if token is None:
            return None
        with SESSION_LOCK:
            session = SESSIONS.get(token.value)
            if session is None:
                return None
            if session.get("expires_at", 0) <= time.time():
                SESSIONS.pop(token.value, None)
                return None
        return {"username": session["username"], "role": session["role"], "tenant_id": session["tenant_id"]}

    @staticmethod
    def _prune_expired_sessions(now: float) -> None:
        for token, session in list(SESSIONS.items()):
            if session.get("expires_at", 0) <= now:
                SESSIONS.pop(token, None)

    def _health(self) -> tuple[dict[str, object], int]:
        try:
            conn = connect()
            try:
                schema_version = conn.execute("SELECT version FROM schema_meta").fetchone()[0]
                conn.execute("SELECT 1").fetchone()
            finally:
                conn.close()
        except Exception:
            logger.exception("Health database check failed")
            return {"status": "degraded", "mode": "synthetic-demo", "database": "unavailable"}, 503
        return {"status": "ok", "mode": "synthetic-demo", "database": "sqlite", "schema_version": schema_version}, 200

    def _readiness(self) -> tuple[dict[str, object], int]:
        body, status = self._health()
        if status != 200:
            return {"status": "not_ready", "reason": "database_unavailable"}, 503
        if body.get("schema_version") != 5:
            return {"status": "not_ready", "reason": "schema_outdated", "schema_version": body.get("schema_version")}, 503
        return {"status": "ready", "mode": "synthetic-demo", "schema_version": 5}, 200

    def _require_actor(self) -> dict[str, str]:
        actor = self._actor()
        if actor is None:
            raise ServiceError("UNAUTHENTICATED", "Sign in with a demo account to continue", 401)
        return actor

    def _check_origin(self) -> None:
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            expected_host = self.headers.get("Host", "")
            if parsed.netloc != expected_host or parsed.scheme not in {"http", "https"}:
                raise ServiceError("INVALID_ORIGIN", "Cross-origin requests are not accepted", 403)

    def do_GET(self) -> None:  # noqa: N802
        self.request_id = secrets.token_hex(12)
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/"):
                if path == "/api/health":
                    body, status = self._health()
                    return self._json(body, status)
                if path == "/api/ready":
                    body, status = self._readiness()
                    return self._json(body, status)
                actor = self._require_actor()
                if path == "/api/session":
                    return self._json({"user": {"username": actor["username"], "role": actor["role"], "tenant_id": actor["tenant_id"]}, "demo_mode": DEMO_MODE})
                if path == "/api/dashboard":
                    return self._json(dashboard(actor["tenant_id"]))
                if path == "/api/cases":
                    q = {k: v[-1] for k, v in parse_qs(urlparse(self.path).query).items() if v}
                    return self._json({"items": list_cases(q, actor["tenant_id"])})
                if path.startswith("/api/cases/"):
                    case_id = unquote(path.removeprefix("/api/cases/"))
                    case = get_case(case_id, actor["tenant_id"])
                    if case is None:
                        raise ServiceError("NOT_FOUND", "Case was not found", 404)
                    return self._json(case)
                if path == "/api/tickets":
                    return self._json({"items": list_tickets(actor["tenant_id"])})
                if path == "/api/audit":
                    query = parse_qs(urlparse(self.path).query)
                    return self._json({"items": audit_log(int((query.get("limit") or ["100"])[0]), actor["tenant_id"])})
                if path == "/api/audit/integrity":
                    return self._json(audit_integrity_status(actor))
                if path == "/api/policies":
                    return self._json({"items": list_policy_proposals(actor)})
                if path == "/api/tools":
                    if actor["role"] != "admin":
                        raise ServiceError("FORBIDDEN", "Admin role is required to view controlled tools", 403)
                    return self._json({"items": controlled_tool_registry()})
                if path == "/api/regulatory/inbox":
                    if actor["role"] != "admin":
                        raise ServiceError("FORBIDDEN", "Admin role is required to review regulatory publications", 403)
                    return self._json(regulatory.inbox())
                raise ServiceError("NOT_FOUND", "API route was not found", 404)
            return self._static(path)
        except ServiceError as exc:
            self._error(exc.code, str(exc), exc.status)
        except (ValueError, TypeError):
            self._error("VALIDATION_ERROR", "Request parameters are invalid", 400)
        except Exception:
            logger.exception("Unhandled GET failure path=%s", path)
            self._error("INTERNAL_ERROR", "The request could not be completed", 500)

    def do_POST(self) -> None:  # noqa: N802
        self.request_id = secrets.token_hex(12)
        path = urlparse(self.path).path
        try:
            self._check_origin()
            if path == "/api/login":
                if not DEMO_MODE:
                    raise ServiceError("DEMO_DISABLED", "Demo authentication is disabled", 403)
                now = time.time()
                with LOGIN_FAILURE_LOCK:
                    for address, attempts in list(LOGIN_FAILURES.items()):
                        active = [attempt for attempt in attempts if now - attempt < 60]
                        if active:
                            LOGIN_FAILURES[address] = active
                        else:
                            LOGIN_FAILURES.pop(address, None)
                    failures = LOGIN_FAILURES.get(self.client_address[0], [])
                    if len(failures) >= 10:
                        raise ServiceError("RATE_LIMITED", "Too many sign-in attempts; retry shortly", 429)
                data = self._body()
                actor = authenticate(str(data.get("username", ""))[:100], str(data.get("password", ""))[:200])
                if actor is None:
                    with LOGIN_FAILURE_LOCK:
                        LOGIN_FAILURES.setdefault(self.client_address[0], failures).append(now)
                    raise ServiceError("INVALID_CREDENTIALS", "Username or password is incorrect", 401)
                with LOGIN_FAILURE_LOCK:
                    LOGIN_FAILURES.pop(self.client_address[0], None)
                with SESSION_LOCK:
                    self._prune_expired_sessions(now)
                    if len(SESSIONS) >= MAX_ACTIVE_SESSIONS:
                        raise ServiceError("SESSION_CAPACITY_REACHED", "Sign-in is temporarily unavailable", 503)
                    SESSIONS[actor["session"]] = {"username": actor["username"], "role": actor["role"], "tenant_id": actor["tenant_id"], "expires_at": now + SESSION_TTL_SECONDS}
                secure = "; Secure" if COOKIE_SECURE else ""
                cookie = f"cause_session={actor['session']}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL_SECONDS}{secure}"
                return self._json({"user": {"username": actor["username"], "role": actor["role"], "tenant_id": actor["tenant_id"]}, "demo_mode": True}, extra_headers={"Set-Cookie": cookie})
            if path == "/api/logout":
                actor = self._require_actor()
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                token = cookie.get("cause_session")
                if token:
                    with SESSION_LOCK:
                        SESSIONS.pop(token.value, None)
                body = b'{"ok":true}'
                self.send_response(200)
                self._headers()
                self.send_header("Set-Cookie", "cause_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            actor = self._require_actor()
            if path == "/api/policies/proposals":
                data = self._body()
                return self._json({"proposal": propose_policy(actor, str(data.get("policy_id", "")), str(data.get("version", "")), str(data.get("status", "")), str(data.get("source", "")), str(data.get("description", "")), str(data.get("effective_from", "")), str(data.get("rationale", "")))}, 201)
            if path.startswith("/api/policies/proposals/") and path.endswith("/review"):
                data = self._body()
                proposal_id = unquote(path.removeprefix("/api/policies/proposals/").removesuffix("/review").strip("/"))
                return self._json({"proposal": review_policy_proposal(actor, proposal_id, str(data.get("verdict", "")), str(data.get("reason", "")))})
            if path.startswith("/api/policies/proposals/") and path.endswith("/activate"):
                proposal_id = unquote(path.removeprefix("/api/policies/proposals/").removesuffix("/activate").strip("/"))
                return self._json({"proposal": activate_policy_proposal(actor, proposal_id)})
            if path == "/api/regulatory/scan":
                if actor["role"] != "admin":
                    raise ServiceError("FORBIDDEN", "Admin role is required to initiate a source scan", 403)
                return self._json(regulatory.scan_sources())
            if path == "/api/integrations/razorpay/payments/import":
                if actor["role"] != "admin":
                    raise ServiceError("FORBIDDEN", "Admin role is required for Razorpay imports", 403)
                data = self._body()
                try:
                    config = razorpay.RazorpayConfig.from_environment()
                    if config.tenant_id != actor["tenant_id"]:
                        raise ServiceError("FORBIDDEN", "Razorpay credential tenant does not match the authenticated tenant", 403)
                    records = razorpay.fetch_payments(
                        config,
                        from_epoch=data.get("from_epoch"),
                        to_epoch=data.get("to_epoch"),
                        count=data.get("count", 100),
                    )
                except razorpay.RazorpayImportError as exc:
                    raise ServiceError("RAZORPAY_IMPORT_UNAVAILABLE", str(exc), 503) from exc
                source_system = "RAZORPAY_PAYMENTS_API" if config.mode == "live" else "RAZORPAY_TEST_PAYMENTS_API"
                if not records:
                    return self._json({"source_system": source_system, "razorpay_mode": config.mode, "fetched": 0, "persisted": False, "outcomes": []})
                result = create_detected_cases(records, 7, actor, self.headers.get("Idempotency-Key", ""), "1.0", source_system)
                return self._json({"source_system": source_system, "razorpay_mode": config.mode, "fetched": len(records), "persisted": True, **result})
            if path.startswith("/api/regulatory/documents/") and path.endswith("/review"):
                data = self._body()
                doc_id = unquote(path.removeprefix("/api/regulatory/documents/").removesuffix("/review").strip("/"))
                return self._json({"document": regulatory.review_document(doc_id, str(data.get("verdict", "")), str(data.get("reason", "")), actor)})
            if path == "/api/detection/preview":
                if actor["role"] not in {"analyst", "admin"}:
                    raise ServiceError("FORBIDDEN", "Analyst or admin role is required to scan source records", 403)
                data = self._body()
                schema_version = data.get("schema_version")
                if schema_version not in {"1.0", "1.1"}:
                    raise ServiceError("VALIDATION_ERROR", "schema_version must be 1.0 or 1.1")
                records = data.get("records")
                if not isinstance(records, list):
                    raise ServiceError("VALIDATION_ERROR", "records must be a list of normalized financial records")
                try:
                    findings = detect_exceptions(records, data.get("timing_window_days", 7), schema_version)
                except ValueError as exc:
                    raise ServiceError("VALIDATION_ERROR", str(exc)) from exc
                return self._json({"mode": "preview", "persisted": False, "count": len(findings), "findings": findings})
            if path == "/api/detection/commit":
                if actor["role"] not in {"analyst", "admin"}:
                    raise ServiceError("FORBIDDEN", "Analyst or admin role is required to create detected cases", 403)
                data = self._body()
                schema_version = data.get("schema_version")
                if schema_version not in {"1.0", "1.1"}:
                    raise ServiceError("VALIDATION_ERROR", "schema_version must be 1.0 or 1.1")
                records = data.get("records")
                if not isinstance(records, list):
                    raise ServiceError("VALIDATION_ERROR", "records must be a list of normalized financial records")
                timing_window = data.get("timing_window_days", 7)
                idem = self.headers.get("Idempotency-Key", "")
                if idem and any(ord(ch) < 33 or ord(ch) > 126 for ch in idem):
                    raise ServiceError("VALIDATION_ERROR", "Idempotency-Key contains invalid characters")
                try:
                    result = create_detected_cases(records, timing_window, actor, idem, schema_version)
                except ValueError as exc:
                    raise ServiceError("VALIDATION_ERROR", str(exc)) from exc
                return self._json({"mode": "commit", "persisted": True, **result})
            if path.startswith("/api/cases/") and path.endswith("/evaluate"):
                case_id = unquote(path.removeprefix("/api/cases/").removesuffix("/evaluate").strip("/"))
                idem = self.headers.get("Idempotency-Key", "")[:120]
                if idem and any(ord(ch) < 33 or ord(ch) > 126 for ch in idem):
                    raise ServiceError("VALIDATION_ERROR", "Idempotency-Key contains invalid characters")
                return self._json(evaluate_case(case_id, actor, idem))
            if path.startswith("/api/cases/") and path.endswith("/ai-investigation"):
                case_id = unquote(path.removeprefix("/api/cases/").removesuffix("/ai-investigation").strip("/"))
                return self._json({"investigation": investigate_case(case_id, actor)})
            if path == "/api/reminders/run":
                return self._json(run_reminders(actor))
            if path.startswith("/api/tickets/"):
                rest = path.removeprefix("/api/tickets/").split("/")
                if len(rest) == 2:
                    ticket_id, action = unquote(rest[0]), rest[1]
                    data = self._body()
                    if action == "respond":
                        return self._json({"ticket": respond_to_ticket(ticket_id, actor, str(data.get("comment", "")))})
                    if action == "resolve":
                        evidence_ids = data.get("evidence_ids", [])
                        if not isinstance(evidence_ids, list):
                            raise ServiceError("VALIDATION_ERROR", "evidence_ids must be a list")
                        return self._json(resolve_ticket(ticket_id, actor, str(data.get("resolution", "")), evidence_ids))
                    if action == "verify":
                        return self._json(verify_ticket(ticket_id, actor))
            raise ServiceError("NOT_FOUND", "API route was not found", 404)
        except ServiceError as exc:
            self._error(exc.code, str(exc), exc.status)
        except (ValueError, TypeError):
            self._error("VALIDATION_ERROR", "Request parameters are invalid", 400)
        except Exception:
            logger.exception("Unhandled POST failure path=%s", path)
            self._error("INTERNAL_ERROR", "The request could not be completed", 500)

    def _static(self, path: str) -> None:
        requested = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (STATIC / requested).resolve()
        if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
            self._error("NOT_FOUND", "Page was not found", 404)
            return
        content_type = {".html":"text/html; charset=utf-8", ".css":"text/css; charset=utf-8", ".js":"text/javascript; charset=utf-8", ".svg":"image/svg+xml"}.get(target.suffix, "application/octet-stream")
        body = target.read_bytes()
        self.send_response(200)
        self._headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802
        self.request_id = secrets.token_hex(12)
        if urlparse(self.path).path == "/api/health":
            return self._json({"status":"ok"})
        self.send_response(200)
        self._headers()
        self.send_header("Content-Length", "0")
        self.end_headers()


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    # This server uses in-memory sessions, SQLite, demo accounts, and no TLS.
    # Refuse production mode and unsafe network exposure so
    # a deployment script cannot accidentally turn the prototype into a live
    # customer-data service by changing HOST alone.
    if RUNTIME_ENV != "demo":
        raise RuntimeError("Unsupported CAUSE_AI_ENV. This build only supports CAUSE_AI_ENV=demo; production launch is blocked until production controls are implemented.")
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("The demo server may bind only to loopback. Use a production architecture with authenticated TLS ingress before network exposure.")
    initialize()
    automatic_evaluation = auto_evaluate_pending_cases()
    regulatory.initialize_sources()
    server = ThreadingHTTPServer((host, port), CauseAIHandler)
    server.daemon_threads = True
    if os.environ.get("CAUSE_AI_REGULATORY_MONITOR", "true").casefold() == "true":
        def monitor() -> None:
            interval = max(900, int(os.environ.get("REGULATORY_SCAN_INTERVAL_SECONDS", "21600")))
            while True:
                try:
                    regulatory.scan_sources()
                except Exception:
                    logger.exception("Regulatory source scan failed")
                time.sleep(interval)
        threading.Thread(target=monitor, name="cause-ai-regulatory-monitor", daemon=True).start()
    logger.info("Cause AI demo ready at http://%s:%s using database %s automatic_evaluations=%s", host, port, os.environ.get("CAUSE_AI_DB", DEFAULT_DB), automatic_evaluation["evaluated"])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Cause AI")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve(os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000")))
