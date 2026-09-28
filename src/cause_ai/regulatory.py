"""Official-source discovery and immutable regulatory-document staging.

This service discovers publications only. It does not interpret law or activate
financial policy; an authorized human must review applicability separately.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import secrets
import urllib.request
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, build_opener

from .database import DEFAULT_DB, append_audit, connect, now_iso
from .service import ServiceError

MAX_INDEX_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_LINKS_PER_SOURCE = 100
KEYWORDS = re.compile(r"upi|circular|notification|master direction|payment system|payment aggregator|digital payment", re.I)
INDEX_TITLE = re.compile(r"^(index to|index to rbi|old notifications|circulars withdrawn|standalone circulars|draft notifications|draft notifications/guidelines)", re.I)
GENERIC_TITLE = re.compile(r"^(notifications?|master directions?|master circulars?|payment systems notifications?)(?:\s*[▼▶]?\s*)$", re.I)
INDEX_PATH = re.compile(r"circularindex|oldnotifications|withdrawncircular|viewlistofstandalone|draftnotificationsguildelines|bs_viewmasterdirections|bs_viewmastercirculardetails|notificationuser\.aspx", re.I)
SOURCES = (
    ("NPCI_UPI", "NPCI UPI circulars", "https://www.npci.org.in/circulars/upi"),
    ("RBI_PSS", "RBI payment systems notifications", "https://www.rbi.org.in/Scripts/FS_Notification.aspx?fn=9"),
)


@contextmanager
def _db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href = None


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _canonical_digest(body: bytes, content_type: str) -> str:
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _VisibleText()
        parser.feed(body.decode("utf-8", errors="replace"))
        canonical = " ".join(" ".join(parser.parts).split()).casefold().encode("utf-8")
    elif content_type.startswith("text/"):
        canonical = " ".join(body.decode("utf-8", errors="replace").split()).casefold().encode("utf-8")
    else:
        canonical = body
    return hashlib.sha256(canonical).hexdigest()


def _allowed(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in {"www.npci.org.in", "www.rbi.org.in"} and not parsed.username and not parsed.password


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    """Reject untrusted redirects before urllib sends the next request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urljoin(req.full_url, newurl)
        if not _allowed(destination):
            raise ValueError("Official source redirected outside the allowlist")
        return super().redirect_request(req, fp, code, msg, headers, destination)


def _fetch(url: str, limit: int) -> tuple[bytes, str, str]:
    if not _allowed(url):
        raise ValueError("URL is outside the official-source allowlist")
    request = urllib.request.Request(url, headers={"User-Agent": "CauseAI-RegulatoryMonitor/1.0", "Accept": "text/html,application/pdf,*/*"})
    opener = build_opener(_AllowlistedRedirectHandler())
    with opener.open(request, timeout=20) as response:
        final_url = response.geturl()
        if not _allowed(final_url):
            raise ValueError("Official source redirected outside the allowlist")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Official source response exceeded the configured size limit")
        return data, response.headers.get_content_type(), final_url


def _data_dir() -> Path:
    db = Path(os.environ.get("CAUSE_AI_DB", DEFAULT_DB))
    root = db.parent / "regulatory" / "objects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _content_integrity(row) -> str:
    """Verify the staged bytes before presenting them as reviewable evidence."""
    stored_path = row["stored_path"]
    if not stored_path:
        return "MISSING"
    object_root = _data_dir().resolve()
    content_hash = str(row["content_sha256"])
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        return "INVALID_HASH"
    candidate = Path(stored_path)
    if candidate.suffix.lower() not in {".bin", ".pdf"}:
        return "INVALID_REFERENCE"
    expected_path = object_root / candidate.name
    if os.path.normcase(os.path.abspath(candidate)) != os.path.normcase(os.path.abspath(expected_path)):
        return "OUTSIDE_OBJECT_STORE"
    if candidate.name != content_hash + candidate.suffix.lower():
        return "INVALID_REFERENCE"
    if expected_path.is_symlink():
        return "SYMLINK_REJECTED"
    try:
        path = expected_path.resolve(strict=True)
    except FileNotFoundError:
        return "MISSING"
    except OSError:
        return "UNREADABLE"
    if not path.is_relative_to(object_root):
        return "OUTSIDE_OBJECT_STORE"
    if not path.is_file():
        return "MISSING"
    try:
        hasher = hashlib.sha256()
        with path.open("rb") as content:
            for chunk in iter(lambda: content.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    except OSError:
        return "UNREADABLE"
    return "VERIFIED" if secrets.compare_digest(digest, content_hash) else "HASH_MISMATCH"


def initialize_sources() -> None:
    with _db() as conn:
        for source_id, name, url in SOURCES:
            conn.execute("INSERT OR IGNORE INTO regulatory_sources(source_id,name,url) VALUES(?,?,?)", (source_id, name, url))


def scan_sources(fetcher=_fetch) -> dict:
    initialize_sources()
    result = {"sources": [], "discovered": 0}
    for source_id, name, index_url in SOURCES:
        checked = now_iso()
        new_count, error = 0, None
        try:
            page, _, final_url = fetcher(index_url, MAX_INDEX_BYTES)
            parser = _Links()
            parser.feed(page.decode("utf-8", errors="replace"))
            candidates = []
            for href, title in parser.links:
                url = urljoin(final_url, html.unescape(href))
                parsed = urlparse(url)
                title = title or unquote(Path(parsed.path).name)
                npci_circular_file = source_id == "NPCI_UPI" and parsed.path.lower().endswith(".pdf")
                is_rbi_index = "fs_notification.aspx" in parsed.path.casefold() and "id=" not in parsed.query.casefold()
                if (title and (KEYWORDS.search(title) or npci_circular_file) and not INDEX_TITLE.search(title) and not GENERIC_TITLE.search(title)
                        and not is_rbi_index and not INDEX_PATH.search(parsed.path + ("?" + parsed.query if parsed.query else ""))
                        and _allowed(url)):
                    candidates.append((url, title[:500]))
            parser_limited = source_id == "NPCI_UPI" and not candidates
            if parser_limited:
                error = "Index responded but exposed no circular links in static HTML; NPCI list is dynamically rendered and the current monitor cannot verify its circular coverage."
            for url, title in list(dict.fromkeys(candidates))[:MAX_LINKS_PER_SOURCE]:
                try:
                    body, content_type, canonical_url = fetcher(url, MAX_DOCUMENT_BYTES)
                    digest = hashlib.sha256(body).hexdigest()
                    canonical_digest = _canonical_digest(body, content_type)
                    suffix = ".pdf" if content_type == "application/pdf" or url.lower().endswith(".pdf") else ".bin"
                    object_path = _data_dir() / f"{digest}{suffix}"
                    with _db() as conn:
                        existing = conn.execute("SELECT id,content_sha256,canonical_sha256,stored_path FROM regulatory_documents WHERE url=?", (canonical_url,)).fetchall()
                        exists = False
                        for old in existing:
                            old_canonical = old["canonical_sha256"]
                            if not old_canonical and old["stored_path"] and Path(old["stored_path"]).is_file():
                                try:
                                    old_body = Path(old["stored_path"]).read_bytes()
                                    old_canonical = _canonical_digest(old_body, content_type)
                                    conn.execute("UPDATE regulatory_documents SET canonical_sha256=? WHERE id=?", (old_canonical, old["id"]))
                                except OSError:
                                    old_canonical = old["content_sha256"]
                            if old_canonical in {canonical_digest, digest}:
                                exists = True
                                break
                        if not exists:
                            if not object_path.exists():
                                object_path.write_bytes(body)
                            doc_id = "REG-" + secrets.token_hex(8).upper()
                            conn.execute("INSERT INTO regulatory_documents(id,source_id,title,url,content_sha256,canonical_sha256,stored_path,content_type,discovered_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                         (doc_id, source_id, title, canonical_url, digest, canonical_digest, str(object_path), content_type, now_iso()))
                            append_audit(conn, "regulatory-monitor", "system", "DOCUMENT_STAGED", "regulatory_document", doc_id,
                                         "Official-source publication captured for human review", {"source_id": source_id, "sha256": digest, "url": canonical_url}, tenant_id="SYSTEM")
                            new_count += 1
                except Exception as exc:
                    # One bad publication must not discard the rest of the source scan.
                    error = (str(exc)[:300])
            status = "PARSER_LIMITED" if parser_limited else "PARTIAL_ERROR" if error and new_count else "ERROR" if error else "OK"
        except Exception as exc:
            error, status = str(exc)[:500], "ERROR"
        with _db() as conn:
            conn.execute("UPDATE regulatory_sources SET checked_at=?,status=?,last_error=? WHERE source_id=?", (checked, status, error, source_id))
            conn.execute("INSERT INTO regulatory_checks(source_id,checked_at,status,item_count,error) VALUES(?,?,?,?,?)", (source_id, checked, status, new_count, error))
        result["discovered"] += new_count
        result["sources"].append({"id": source_id, "name": name, "status": status, "checked_at": checked, "new_documents": new_count, "error": error})
    return result


def inbox() -> dict:
    initialize_sources()
    with _db() as conn:
        sources = [dict(row) for row in conn.execute("SELECT source_id AS id,name,url,checked_at,status,last_error FROM regulatory_sources ORDER BY source_id")]
        documents = [dict(row) for row in conn.execute("SELECT id,source_id,title,url,published_label,content_sha256,content_type,discovered_at,review_status,review_actor,review_reason,reviewed_at FROM regulatory_documents WHERE review_status!='FILTERED_INDEX' ORDER BY discovered_at DESC LIMIT 500")]
        pending = conn.execute("SELECT COUNT(*) FROM regulatory_documents WHERE review_status='REVIEW_REQUIRED'").fetchone()[0]
    return {"sources": sources, "documents": documents, "pending_count": pending,
            "policy_activation": "NOT_SUPPORTED: discovered documents never activate policy"}


def review_document(document_id: str, verdict: str, reason: str, actor: dict) -> dict:
    if actor.get("role") != "admin":
        raise ServiceError("FORBIDDEN", "Admin role is required to review regulatory publications", 403)
    if verdict not in {"RELEVANT", "NOT_APPLICABLE", "NEEDS_LEGAL_REVIEW"}:
        raise ServiceError("VALIDATION_ERROR", "verdict must be RELEVANT, NOT_APPLICABLE, or NEEDS_LEGAL_REVIEW")
    reason = reason.strip()
    if not 15 <= len(reason) <= 2000:
        raise ServiceError("VALIDATION_ERROR", "Review rationale must contain 15–2,000 characters")
    with _db() as conn:
        row = conn.execute("SELECT * FROM regulatory_documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise ServiceError("NOT_FOUND", "Regulatory publication was not found", 404)
        if row["review_status"] not in {"REVIEW_REQUIRED", "NEEDS_LEGAL_REVIEW"}:
            raise ServiceError("CONFLICT", "This publication has already been reviewed", 409)
        integrity = _content_integrity(row)
        if integrity != "VERIFIED":
            raise ServiceError("CONFLICT", f"This publication cannot be reviewed because its stored content integrity is {integrity}", 409)
        timestamp = now_iso()
        conn.execute("UPDATE regulatory_documents SET review_status=?,review_actor=?,review_reason=?,reviewed_at=? WHERE id=?",
                     (verdict, actor["username"], reason, timestamp, document_id))
        append_audit(conn, actor["username"], actor["role"], "REGULATORY_DOCUMENT_REVIEWED", "regulatory_document", document_id,
                     reason, {"verdict": verdict, "sha256": row["content_sha256"], "content_integrity": integrity, "policy_activated": False}, tenant_id=actor["tenant_id"])
        return {"id": document_id, "review_status": verdict, "review_actor": actor["username"], "review_reason": reason, "reviewed_at": timestamp, "policy_activated": False}
