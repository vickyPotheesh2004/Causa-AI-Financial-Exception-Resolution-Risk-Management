"""Read-only Razorpay payment import with explicit test and live safeguards."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_BASE = "https://api.razorpay.com/v1"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class RazorpayImportError(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RazorpayImportError("Razorpay API redirects are not accepted for credentialed imports")


@dataclass(frozen=True)
class RazorpayConfig:
    key_id: str
    key_secret: str
    tenant_id: str
    mode: str = "live"

    @classmethod
    def from_environment(cls) -> "RazorpayConfig":
        missing = [name for name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_TENANT_ID") if not os.environ.get(name)]
        if missing:
            raise RazorpayImportError("Razorpay read-only import is not configured")
        mode = os.environ.get("RAZORPAY_MODE", "").casefold()
        if mode not in {"test", "live"}:
            raise RazorpayImportError("Razorpay import requires RAZORPAY_MODE=test or RAZORPAY_MODE=live")
        consent_variable = f"RAZORPAY_ALLOW_{mode.upper()}_READ_ONLY_IMPORT"
        if os.environ.get(consent_variable, "").casefold() != "true":
            raise RazorpayImportError(f"Razorpay {mode} import requires explicit read-only opt-in")
        return cls(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"], os.environ["RAZORPAY_TENANT_ID"], mode)


def _minor_to_amount(value: Any) -> str:
    if isinstance(value, bool):
        raise RazorpayImportError("Razorpay payment amount is invalid")
    try:
        minor = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RazorpayImportError("Razorpay payment amount is invalid") from exc
    if minor != minor.to_integral_value() or minor < 0:
        raise RazorpayImportError("Razorpay payment amount is invalid")
    return f"{minor / Decimal(100):.2f}"


def _normalize_payment(item: dict[str, Any]) -> dict[str, Any]:
    payment_id = item.get("id")
    currency = item.get("currency")
    created_at = item.get("created_at")
    if not isinstance(payment_id, str) or not payment_id or not isinstance(currency, str) or not currency:
        raise RazorpayImportError("Razorpay payment response is missing a required identifier")
    if isinstance(created_at, bool):
        raise RazorpayImportError("Razorpay payment timestamp is invalid")
    try:
        occurred_at = datetime.fromtimestamp(int(created_at), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise RazorpayImportError("Razorpay payment timestamp is invalid") from exc
    return {
        "record_type": "payment",
        "record_id": f"razorpay:payment:{payment_id}",
        "payment_id": payment_id,
        "currency": currency.upper(),
        "amount": _minor_to_amount(item.get("amount")),
        "status": str(item.get("status", "UNKNOWN")).upper(),
        "occurred_at": occurred_at,
    }


def fetch_payments(config: RazorpayConfig, *, from_epoch: int | None = None,
                   to_epoch: int | None = None, count: int = 100) -> list[dict[str, Any]]:
    """Fetch and normalize one bounded page of payment records.

    The caller persists only normalized fields. Raw Razorpay responses and
    credentials never enter audit events or application responses.
    """
    if not 1 <= count <= 100:
        raise RazorpayImportError("Razorpay import count must be between 1 and 100")
    query: dict[str, str | int] = {"count": count}
    for key, value in (("from", from_epoch), ("to", to_epoch)):
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RazorpayImportError(f"Razorpay import {key} must be a Unix timestamp")
            query[key] = value
    if from_epoch is not None and to_epoch is not None and from_epoch > to_epoch:
        raise RazorpayImportError("Razorpay import from timestamp must not exceed to timestamp")
    token = base64.b64encode(f"{config.key_id}:{config.key_secret}".encode("utf-8")).decode("ascii")
    request = Request(
        f"{API_BASE}/payments?{urlencode(query)}",
        headers={"Accept": "application/json", "Authorization": f"Basic {token}", "User-Agent": "CauseAI-RazorpayReadOnly/1.0"},
        method="GET",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise RazorpayImportError("Razorpay response exceeded the configured size limit")
    except RazorpayImportError:
        raise
    except HTTPError as exc:
        raise RazorpayImportError(f"Razorpay API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RazorpayImportError("Razorpay API request failed") from exc
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RazorpayImportError("Razorpay API returned invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise RazorpayImportError("Razorpay API response does not contain a payment collection")
    return [_normalize_payment(item) for item in payload["items"] if isinstance(item, dict)]
