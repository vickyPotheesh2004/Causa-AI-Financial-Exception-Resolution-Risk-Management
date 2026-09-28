"""Vercel adapter for the synthetic Cause AI submission demo.

The data file is intentionally kept in /tmp on Vercel. This makes the demo
usable without a paid database, but its contents are not durable between
serverless instances. Do not use this adapter for customer or financial data.
"""

import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("CAUSE_AI_ENV", "demo")
os.environ.setdefault("CAUSE_AI_DEMO", "true")
os.environ.setdefault("CAUSE_AI_DB", "/tmp/cause_ai.sqlite3")
os.environ.setdefault("CAUSE_AI_COOKIE_SECURE", "true")

from cause_ai.database import initialize  # noqa: E402
from cause_ai.service import auto_evaluate_pending_cases  # noqa: E402
from cause_ai.server import CauseAIHandler  # noqa: E402

initialize()
auto_evaluate_pending_cases()


class handler(CauseAIHandler):
    """Vercel's Python runtime invokes this BaseHTTPRequestHandler class."""

    def _restore_api_path(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        routed_path = query.pop("cause_path", [""])[-1]
        if routed_path:
            suffix = urlencode(query, doseq=True)
            self.path = f"/api/{routed_path}" + (f"?{suffix}" if suffix else "")

    def do_GET(self) -> None:  # noqa: N802
        self._restore_api_path()
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._restore_api_path()
        super().do_POST()
