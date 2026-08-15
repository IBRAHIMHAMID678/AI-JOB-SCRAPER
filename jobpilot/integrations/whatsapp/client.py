"""
WhatsApp Business API integration.

IMPORTANT: Uses ONLY the official Meta WhatsApp Business Cloud API.
Does NOT use unofficial scraping, web automation, or account abuse.

STATUS: PENDING CONFIGURATION
Required: Meta Business Account + WhatsApp Business API approval
Set in .env: WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TO_NUMBER
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from ...core.config import settings
from ...core.logging import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://graph.facebook.com/v18.0"


class WhatsAppClient:
    """
    Official Meta WhatsApp Business Cloud API client.
    All messages use approved message templates for business-initiated conversations.
    """

    def __init__(self) -> None:
        self._token = settings.WHATSAPP_API_TOKEN
        self._phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self._to = settings.WHATSAPP_TO_NUMBER
        self._configured = all([self._token, self._phone_id, self._to])
        if not self._configured:
            logger.info("WhatsApp not configured (set WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TO_NUMBER)")

    @property
    def is_configured(self) -> bool:
        return self._configured

    def send_text(self, message: str) -> bool:
        """Send a plain text message (requires active conversation window or template)."""
        if not self._configured:
            logger.debug("WhatsApp: message skipped (not configured): %s", message[:50])
            return False
        return self._send({
            "messaging_product": "whatsapp",
            "to": self._to,
            "type": "text",
            "text": {"body": message[:4096]},
        })

    def send_job_notification(self, job_title: str, company: str, score: int, match_label: str, job_url: str) -> bool:
        """Notify about a high-scoring job match."""
        message = (
            f"🎯 *JOBPILOT Match Found*\n\n"
            f"*{job_title}*\n"
            f"Company: {company}\n"
            f"Score: {score}% ({match_label})\n\n"
            f"Apply: {job_url[:100]}\n\n"
            f"_Reply APPROVE or REJECT_"
        )
        return self.send_text(message)

    def send_approval_request(self, job_title: str, company: str, score: int, application_id: str) -> bool:
        """Request approval before submitting application."""
        message = (
            f"⏳ *Application Approval Required*\n\n"
            f"Job: *{job_title}* at {company}\n"
            f"Match Score: {score}%\n"
            f"Application ID: {application_id}\n\n"
            f"Visit dashboard to review and approve."
        )
        return self.send_text(message)

    def send_interview_alert(self, company: str, details: str) -> bool:
        return self.send_text(f"🎉 *Interview Request*\n\nFrom: {company}\n\n{details[:300]}")

    def send_daily_summary(self, discovered: int, matched: int, submitted: int) -> bool:
        message = (
            f"📊 *JOBPILOT Daily Summary*\n\n"
            f"• Jobs discovered: {discovered}\n"
            f"• Jobs matched: {matched}\n"
            f"• Applications submitted: {submitted}\n"
        )
        return self.send_text(message)

    def _send(self, payload: Dict[str, Any]) -> bool:
        try:
            resp = requests.post(
                f"{_BASE_URL}/{self._phone_id}/messages",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                return True
            logger.warning("WhatsApp API error %d: %s", resp.status_code, resp.text[:200])
            return False
        except Exception as exc:
            logger.error("WhatsApp send failed: %s", exc)
            return False


# Singleton
_client: Optional[WhatsAppClient] = None


def get_whatsapp_client() -> WhatsAppClient:
    global _client
    if _client is None:
        _client = WhatsAppClient()
    return _client
