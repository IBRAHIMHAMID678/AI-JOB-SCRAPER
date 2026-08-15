"""
Email OAuth integration for JOBPILOT.

Supports Gmail and Outlook via OAuth 2.0.
NEVER stores raw passwords. Only OAuth tokens (encrypted at rest in DB).

STATUS: PENDING CONFIGURATION
Required: Google Cloud Console OAuth credentials OR Azure App Registration
Set in .env: EMAIL_OAUTH_CLIENT_ID, EMAIL_OAUTH_CLIENT_SECRET, EMAIL_PROVIDER

The EmailMonitor scans for:
- Application confirmations
- Rejection emails
- Interview invitations
- Recruiter messages
- Assessment requests
- Offer letters
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from ...core.config import settings
from ...core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EmailMessage:
    external_id: str
    sender: str
    subject: str
    body_preview: str
    received_at: datetime


_CLASSIFICATION_PATTERNS = {
    "confirmation": [
        r"application\s+received", r"thank\s+you\s+for\s+(applying|your\s+application)",
        r"we\s+have\s+received\s+your", r"application\s+confirmed",
    ],
    "rejection": [
        r"we\s+regret", r"not\s+(moving\s+forward|selected|a\s+match)",
        r"(pursued|decided\s+to\s+pursue)\s+other\s+candidates",
        r"position\s+has\s+been\s+filled", r"will\s+not\s+be\s+moving\s+forward",
    ],
    "interview": [
        r"interview\s+(invitation|request|schedule|opportunity)",
        r"(phone|video|technical)\s+(screen|interview|call)",
        r"schedule\s+a\s+(call|interview|meeting)",
        r"would\s+like\s+to\s+(speak|chat|meet|talk)",
    ],
    "assessment": [
        r"(coding|technical)\s+(assessment|test|challenge|exercise)",
        r"hackerrank", r"codility", r"leetcode", r"take-home",
    ],
    "offer": [
        r"offer\s+letter", r"job\s+offer", r"pleased\s+to\s+offer",
        r"extend\s+an\s+offer", r"compensation\s+package",
    ],
}

_COMPILED = {
    cat: [re.compile(p, re.IGNORECASE) for p in patterns]
    for cat, patterns in _CLASSIFICATION_PATTERNS.items()
}


def classify_email(subject: str, body: str) -> tuple[str, float]:
    """
    Returns (classification, confidence).
    classification: confirmation | rejection | interview | assessment | offer | unknown
    """
    text = (subject + " " + body).lower()
    scores: dict[str, int] = {}
    for cat, patterns in _COMPILED.items():
        matches = sum(1 for p in patterns if p.search(text))
        if matches:
            scores[cat] = matches

    if not scores:
        return "unknown", 0.3
    best_cat = max(scores, key=lambda k: scores[k])
    confidence = min(0.6 + scores[best_cat] * 0.15, 0.95)
    return best_cat, confidence


class EmailOAuthClient:
    """
    OAuth-based email client.
    Subclasses implement _fetch_messages() for Gmail / Outlook.
    """

    provider: str = "base"

    def __init__(self) -> None:
        self._client_id = settings.EMAIL_OAUTH_CLIENT_ID
        self._client_secret = settings.EMAIL_OAUTH_CLIENT_SECRET
        self._configured = bool(self._client_id and self._client_secret)
        if not self._configured:
            logger.info("Email OAuth not configured (set EMAIL_OAUTH_CLIENT_ID, EMAIL_OAUTH_CLIENT_SECRET)")

    @property
    def is_configured(self) -> bool:
        return self._configured

    def get_auth_url(self) -> Optional[str]:
        """Return the OAuth authorization URL for the user to visit."""
        raise NotImplementedError

    def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        raise NotImplementedError

    def scan_inbox(self, since: Optional[datetime] = None) -> List[dict]:
        """
        Fetch recent emails and classify each one.
        Returns list of classified email dicts.
        """
        if not self._configured:
            return []
        try:
            messages = self._fetch_messages(since)
            results = []
            for msg in messages:
                classification, confidence = classify_email(msg.subject, msg.body_preview)
                results.append({
                    "external_id": msg.external_id,
                    "sender": msg.sender,
                    "subject": msg.subject,
                    "body_preview": msg.body_preview[:500],
                    "received_at": msg.received_at.isoformat(),
                    "classification": classification,
                    "confidence": confidence,
                    "requires_review": confidence < 0.7,
                })
            return results
        except Exception as exc:
            logger.error("Email scan failed: %s", exc)
            return []

    def _fetch_messages(self, since: Optional[datetime]) -> List[EmailMessage]:
        """Implement in provider-specific subclass."""
        raise NotImplementedError


class GmailOAuthClient(EmailOAuthClient):
    """
    Gmail OAuth client using Google APIs.
    PENDING: requires Google Cloud Console project + OAuth credentials.
    """
    provider = "gmail"

    def get_auth_url(self) -> Optional[str]:
        if not self._configured:
            return None
        scope = "https://www.googleapis.com/auth/gmail.readonly"
        return (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={self._client_id}"
            f"&redirect_uri={settings.EMAIL_OAUTH_REDIRECT_URI}"
            f"&response_type=code&scope={scope}&access_type=offline&prompt=consent"
        )

    def exchange_code(self, code: str) -> dict:
        import requests
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": settings.EMAIL_OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        }, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _fetch_messages(self, since: Optional[datetime]) -> List[EmailMessage]:
        # Placeholder — real implementation requires stored OAuth token
        # When token is available, use Google Gmail API:
        # GET https://gmail.googleapis.com/gmail/v1/users/me/messages
        logger.info("Gmail fetch not yet authorized — complete OAuth flow first")
        return []


def get_email_client() -> EmailOAuthClient:
    provider = settings.EMAIL_PROVIDER.lower()
    if provider == "gmail":
        return GmailOAuthClient()
    logger.warning("Email provider '%s' not implemented, defaulting to Gmail", provider)
    return GmailOAuthClient()
