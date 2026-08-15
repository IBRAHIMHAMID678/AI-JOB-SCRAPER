"""
Security utilities for JOBPILOT.
Covers URL validation (SSRF prevention), secret management,
input sanitization, and prompt injection defence.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import urllib.parse
from typing import Optional

from .logging import get_logger

logger = get_logger(__name__)

# ── SSRF / URL validation ─────────────────────────────────────────────────────

_ALLOWED_SCHEMES = {"http", "https"}

_PRIVATE_IP_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".sh", ".ps1", ".cmd", ".vbs", ".js",
    ".php", ".asp", ".aspx", ".jsp",
}


def validate_external_url(url: str) -> tuple[bool, str]:
    """
    Returns (is_safe, reason).
    Blocks: non-http(s), localhost, private IPs, dangerous extensions.
    """
    if not url or len(url) > 2000:
        return False, "URL missing or too long"

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "URL parse error"

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, f"Scheme not allowed: {parsed.scheme}"

    hostname = parsed.hostname or ""
    if not hostname:
        return False, "No hostname"

    if hostname in ("localhost", "127.0.0.1", "::1"):
        return False, "localhost not allowed"

    # Resolve to IP and check private ranges
    try:
        addr = ipaddress.ip_address(hostname)
        for net in _PRIVATE_IP_NETWORKS:
            if addr in net:
                return False, f"Private IP blocked: {hostname}"
    except ValueError:
        pass  # hostname not a raw IP — fine

    # Block dangerous file extensions in path
    path = parsed.path.lower()
    for ext in _DANGEROUS_EXTENSIONS:
        if path.endswith(ext):
            return False, f"Dangerous extension: {ext}"

    return True, "ok"


def sanitize_url(url: str) -> Optional[str]:
    """Return cleaned URL or None if invalid."""
    ok, reason = validate_external_url(url)
    if not ok:
        logger.warning("Blocked URL: %s — %s", url, reason)
        return None
    return url


# ── Prompt injection defence ──────────────────────────────────────────────────

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?instructions",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(if\s+you\s+are\s+)?",
    r"forget\s+(everything|all)\s+(you\s+know|above)",
    r"send\s+(the\s+)?(database|data|keys?|secrets?)\s+to",
    r"exfiltrate",
    r"print\s+your\s+(system\s+)?prompt",
    r"reveal\s+your\s+(system\s+)?(prompt|instructions)",
    r"http[s]?://[^\s]+\s*\[INJECT\]",
]

_COMPILED_INJECTION = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION_PATTERNS]


def detect_prompt_injection(text: str) -> tuple[bool, Optional[str]]:
    """
    Check untrusted text (job descriptions, emails) for injection attempts.
    Returns (is_suspicious, matched_pattern).
    """
    for pat in _COMPILED_INJECTION:
        m = pat.search(text)
        if m:
            return True, m.group(0)[:80]
    return False, None


def sanitize_for_prompt(text: str, max_length: int = 4000) -> str:
    """
    Truncate and wrap untrusted content so it cannot escape its context block.
    The wrapper makes the LLM treat the content as data, not instructions.
    """
    if not text:
        return ""
    # Truncate
    text = text[:max_length]
    # Wrap in a clear data block
    return f"[BEGIN UNTRUSTED JOB CONTENT]\n{text}\n[END UNTRUSTED JOB CONTENT]"


# ── Hashing ───────────────────────────────────────────────────────────────────

def hash_url(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()[:64]


def hash_content(title: str, company: str, description: str = "") -> str:
    raw = f"{title.strip().lower()}::{company.strip().lower()}::{description[:200].strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


# ── Secret validation ─────────────────────────────────────────────────────────

def mask_secret(value: str, visible: int = 4) -> str:
    """Return '***...XXXX' for display in logs."""
    if not value or len(value) <= visible:
        return "****"
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"
