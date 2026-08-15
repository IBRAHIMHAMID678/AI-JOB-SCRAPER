"""
Email OAuth integration for JOBPILOT.

Supports Gmail via OAuth 2.0.
NEVER stores raw passwords. Only OAuth tokens (stored in system_settings table).

Setup:
1. Google Cloud Console → create project → enable Gmail API
2. Create OAuth 2.0 credentials (Web application)
3. Add authorized redirect URI: http://localhost:8000/api/email/callback
4. Set in .env: EMAIL_OAUTH_CLIENT_ID, EMAIL_OAUTH_CLIENT_SECRET

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
from datetime import datetime, timezone
from typing import List, Optional

import requests as _requests

from ...core.config import settings
from ...core.logging import get_logger

logger = get_logger(__name__)

_GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
_GMAIL_MESSAGE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}"
_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@dataclass
class EmailMessage:
    external_id: str
    sender: str
    subject: str
    body_preview: str
    received_at: datetime


_CLASSIFICATION_PATTERNS = {
    "confirmation": [
        r"application\s+received",
        r"thank\s+you\s+for\s+(applying|your\s+application)",
        r"we\s+have\s+received\s+your",
        r"application\s+confirmed",
    ],
    "rejection": [
        r"we\s+regret",
        r"not\s+(moving\s+forward|selected|a\s+match)",
        r"(pursued|decided\s+to\s+pursue)\s+other\s+candidates",
        r"position\s+has\s+been\s+filled",
        r"will\s+not\s+be\s+moving\s+forward",
        r"unfortunately.*not.*proceed",
    ],
    "interview": [
        r"interview\s+(invitation|request|schedule|opportunity)",
        r"(phone|video|technical|virtual)\s+(screen|interview|call)",
        r"schedule\s+a\s+(call|interview|meeting)",
        r"would\s+like\s+to\s+(speak|chat|meet|talk)",
        r"next\s+steps.*interview",
    ],
    "assessment": [
        r"(coding|technical)\s+(assessment|test|challenge|exercise)",
        r"hackerrank",
        r"codility",
        r"leetcode",
        r"take-home\s+(test|assignment|project)",
    ],
    "offer": [
        r"offer\s+letter",
        r"job\s+offer",
        r"pleased\s+to\s+offer",
        r"extend\s+an\s+offer",
        r"compensation\s+package",
        r"start\s+date",
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


class GmailOAuthClient:
    """
    Complete Gmail OAuth 2.0 client.
    Tokens are stored/retrieved from the system_settings DB table.
    """

    provider = "gmail"

    def __init__(self) -> None:
        self._client_id = settings.EMAIL_OAUTH_CLIENT_ID
        self._client_secret = settings.EMAIL_OAUTH_CLIENT_SECRET
        self._redirect_uri = settings.EMAIL_OAUTH_REDIRECT_URI
        self._configured = bool(self._client_id and self._client_secret)
        if not self._configured:
            logger.info(
                "Gmail OAuth not configured — set EMAIL_OAUTH_CLIENT_ID and "
                "EMAIL_OAUTH_CLIENT_SECRET in .env"
            )

    @property
    def is_configured(self) -> bool:
        return self._configured

    def get_auth_url(self) -> Optional[str]:
        """Return the Google OAuth URL the user must visit to authorize."""
        if not self._configured:
            return None
        params = (
            f"client_id={self._client_id}"
            f"&redirect_uri={self._redirect_uri}"
            f"&response_type=code"
            f"&scope={_GMAIL_SCOPE}"
            f"&access_type=offline"
            f"&prompt=consent"
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"

    def exchange_code(self, code: str) -> dict:
        """Exchange the one-time authorization code for access + refresh tokens."""
        resp = _requests.post(_GMAIL_TOKEN_URL, data={
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Use refresh token to get a fresh access token."""
        try:
            resp = _requests.post(_GMAIL_TOKEN_URL, data={
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            }, timeout=15)
            resp.raise_for_status()
            return resp.json().get("access_token")
        except Exception as exc:
            logger.error("Gmail token refresh failed: %s", exc)
            return None

    def _get_valid_token(self, stored: dict) -> Optional[str]:
        """Return a valid access token, refreshing if needed."""
        access_token = stored.get("access_token")
        refresh_token = stored.get("refresh_token")
        expires_at = stored.get("expires_at", 0)

        import time
        if access_token and time.time() < expires_at - 60:
            return access_token

        if refresh_token:
            new_token = self.refresh_access_token(refresh_token)
            if new_token:
                stored["access_token"] = new_token
                stored["expires_at"] = time.time() + 3600
                self._save_tokens(stored)
                return new_token

        return None

    def _save_tokens(self, token_data: dict) -> None:
        """Persist token data to system_settings table."""
        try:
            from ...core.database import db_session
            from ...core.models import SystemSetting
            with db_session() as db:
                s = db.query(SystemSetting).filter_by(key="EMAIL_OAUTH_TOKENS").first()
                if s:
                    s.value = token_data
                else:
                    db.add(SystemSetting(
                        key="EMAIL_OAUTH_TOKENS",
                        value=token_data,
                        description="Gmail OAuth access + refresh tokens",
                    ))
        except Exception as exc:
            logger.error("Failed to save Gmail tokens: %s", exc)

    def _load_tokens(self) -> Optional[dict]:
        """Load stored tokens from system_settings table."""
        try:
            from ...core.database import db_session
            from ...core.models import SystemSetting
            with db_session() as db:
                s = db.query(SystemSetting).filter_by(key="EMAIL_OAUTH_TOKENS").first()
                return dict(s.value) if s and s.value else None
        except Exception:
            return None

    def save_tokens_from_exchange(self, token_response: dict) -> None:
        """Called after exchange_code() — store tokens with expiry timestamp."""
        import time
        data = {
            "access_token": token_response.get("access_token"),
            "refresh_token": token_response.get("refresh_token"),
            "expires_at": time.time() + token_response.get("expires_in", 3600),
            "scope": token_response.get("scope", ""),
        }
        self._save_tokens(data)

    @property
    def is_authorized(self) -> bool:
        """True if we have stored tokens."""
        tokens = self._load_tokens()
        return bool(tokens and (tokens.get("access_token") or tokens.get("refresh_token")))

    def _fetch_messages(self, since: Optional[datetime] = None) -> List[EmailMessage]:
        """Fetch recent Gmail messages using the stored access token."""
        tokens = self._load_tokens()
        if not tokens:
            logger.info("Gmail not authorized — complete OAuth flow at /api/email/auth")
            return []

        access_token = self._get_valid_token(tokens)
        if not access_token:
            logger.warning("Gmail: could not get valid access token")
            return []

        headers = {"Authorization": f"Bearer {access_token}"}

        # Build query: last 7 days, inbox only, job-related senders
        query = "in:inbox newer_than:7d"
        if since:
            ts = int(since.timestamp())
            query = f"in:inbox after:{ts}"

        try:
            # List message IDs
            resp = _requests.get(
                _GMAIL_MESSAGES_URL,
                headers=headers,
                params={"q": query, "maxResults": 50},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            message_refs = data.get("messages", [])
        except Exception as exc:
            logger.error("Gmail list messages failed: %s", exc)
            return []

        messages: List[EmailMessage] = []
        for ref in message_refs[:30]:
            try:
                msg_resp = _requests.get(
                    _GMAIL_MESSAGE_URL.format(msg_id=ref["id"]),
                    headers=headers,
                    params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                    timeout=10,
                )
                msg_resp.raise_for_status()
                msg = msg_resp.json()

                headers_list = msg.get("payload", {}).get("headers", [])
                header_map = {h["name"]: h["value"] for h in headers_list}

                subject = header_map.get("Subject", "(no subject)")
                sender = header_map.get("From", "")
                date_str = header_map.get("Date", "")
                snippet = msg.get("snippet", "")

                try:
                    from email.utils import parsedate_to_datetime
                    received_at = parsedate_to_datetime(date_str) if date_str else datetime.now(timezone.utc)
                    if received_at.tzinfo is None:
                        received_at = received_at.replace(tzinfo=timezone.utc)
                except Exception:
                    received_at = datetime.now(timezone.utc)

                messages.append(EmailMessage(
                    external_id=ref["id"],
                    sender=sender,
                    subject=subject,
                    body_preview=snippet,
                    received_at=received_at,
                ))
            except Exception as exc:
                logger.debug("Failed to fetch message %s: %s", ref["id"], exc)
                continue

        return messages

    def scan_inbox(self, since: Optional[datetime] = None) -> List[dict]:
        """
        Fetch recent emails and classify each one.
        Returns list of classified email dicts ready for the API.
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
                    "confidence": round(confidence, 2),
                    "requires_review": confidence < 0.7,
                })
            logger.info("Gmail scan: classified %d emails", len(results))
            return results
        except Exception as exc:
            logger.error("Email scan failed: %s", exc)
            return []


# ── Singleton ──────────────────────────────────────────────────────────────────

_client: Optional[GmailOAuthClient] = None


def get_email_client() -> GmailOAuthClient:
    global _client
    if _client is None:
        _client = GmailOAuthClient()
    return _client
