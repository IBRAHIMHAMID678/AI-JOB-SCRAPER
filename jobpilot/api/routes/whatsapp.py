"""
WhatsApp routes for JOBPILOT.

GET  /api/whatsapp/status      — is WhatsApp configured?
POST /api/whatsapp/test        — send a test message to yourself
POST /api/whatsapp/notify/job  — send a job match notification
GET  /api/whatsapp/webhook     — Meta webhook verification
POST /api/whatsapp/webhook     — receive incoming WhatsApp messages (APPROVE/REJECT)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ...integrations.whatsapp.client import get_whatsapp_client
from ...core.config import settings
from ...core.logging import get_logger

router = APIRouter(tags=["whatsapp"])
logger = get_logger(__name__)


class JobNotifyRequest(BaseModel):
    job_title: str
    company: str
    score: int
    match_label: str = "Strong Match"
    job_url: str = ""


class TextMessageRequest(BaseModel):
    message: str


@router.get("/whatsapp/status")
def whatsapp_status() -> Dict[str, Any]:
    """Check whether WhatsApp Business API is configured."""
    client = get_whatsapp_client()
    return {
        "configured": client.is_configured,
        "message": (
            "WhatsApp Business API is ready"
            if client.is_configured
            else "Set WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, and WHATSAPP_TO_NUMBER in .env"
        ),
        "setup_guide": (
            "https://developers.facebook.com/docs/whatsapp/cloud-api/get-started"
            if not client.is_configured
            else None
        ),
    }


@router.post("/whatsapp/test")
def whatsapp_test() -> Dict[str, Any]:
    """Send a test message to verify the WhatsApp integration is working."""
    client = get_whatsapp_client()
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "WhatsApp not configured. Set WHATSAPP_API_TOKEN, "
                "WHATSAPP_PHONE_NUMBER_ID, and WHATSAPP_TO_NUMBER in .env"
            ),
        )
    success = client.send_text(
        "✅ *JOBPILOT WhatsApp Connected*\n\n"
        "Your job intelligence assistant is now active.\n"
        "You will receive notifications for high-match jobs, interview requests, and daily summaries."
    )
    if success:
        return {"status": "sent", "message": "Test message delivered successfully"}
    raise HTTPException(status_code=502, detail="WhatsApp API returned an error. Check your token and phone number ID.")


@router.post("/whatsapp/notify/job")
def whatsapp_notify_job(req: JobNotifyRequest) -> Dict[str, Any]:
    """Send a job match notification via WhatsApp."""
    client = get_whatsapp_client()
    if not client.is_configured:
        raise HTTPException(status_code=503, detail="WhatsApp not configured")
    success = client.send_job_notification(
        job_title=req.job_title,
        company=req.company,
        score=req.score,
        match_label=req.match_label,
        job_url=req.job_url,
    )
    return {"status": "sent" if success else "failed"}


@router.post("/whatsapp/send")
def whatsapp_send(req: TextMessageRequest) -> Dict[str, Any]:
    """Send a custom text message via WhatsApp."""
    client = get_whatsapp_client()
    if not client.is_configured:
        raise HTTPException(status_code=503, detail="WhatsApp not configured")
    success = client.send_text(req.message)
    return {"status": "sent" if success else "failed"}


# ── Webhook (Meta requires this to verify your endpoint) ──────────────────────

@router.get("/whatsapp/webhook")
def whatsapp_webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Meta webhook verification challenge.
    Set Callback URL in Meta App Dashboard → Webhooks → WhatsApp.
    """
    expected_token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "jobpilot-webhook-token"
    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info("WhatsApp webhook verified")
        return int(hub_challenge) if hub_challenge else "OK"
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook_receive(request: Request) -> Dict[str, str]:
    """
    Receive incoming WhatsApp messages.
    Handles APPROVE / REJECT replies to auto-approve or reject applications.
    """
    try:
        body = await request.json()
        entries = body.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    if msg.get("type") == "text":
                        text = msg["text"]["body"].strip().upper()
                        sender = msg.get("from", "")
                        logger.info("WhatsApp incoming from %s: %s", sender, text)
                        _handle_incoming_reply(text, sender)
    except Exception as exc:
        logger.error("WhatsApp webhook error: %s", exc)

    return {"status": "ok"}


def _handle_incoming_reply(text: str, sender: str) -> None:
    """
    Handle APPROVE / REJECT replies from the user.
    Finds the most recent application awaiting approval and acts on it.
    """
    try:
        from ...core.database import db_session
        from ...core.models import Application, ApplicationStatus

        if text not in ("APPROVE", "REJECT"):
            return

        with db_session() as db:
            pending = (
                db.query(Application)
                .filter(Application.status == ApplicationStatus.READY_FOR_REVIEW)
                .order_by(Application.updated_at.desc())
                .first()
            )
            if not pending:
                logger.info("WhatsApp %s reply: no application pending approval", text)
                return

            if text == "APPROVE":
                pending.status = ApplicationStatus.APPROVED
                logger.info("Application %s APPROVED via WhatsApp", pending.id)
            else:
                pending.status = ApplicationStatus.REJECTED
                logger.info("Application %s REJECTED via WhatsApp", pending.id)

            client = get_whatsapp_client()
            job_title = pending.job.title if pending.job else "the job"
            company = pending.job.company if pending.job else ""
            if text == "APPROVE":
                client.send_text(f"✅ Got it — application for *{job_title}* at {company} is approved and queued.")
            else:
                client.send_text(f"❌ Application for *{job_title}* at {company} has been rejected.")
    except Exception as exc:
        logger.error("WhatsApp reply handler failed: %s", exc)
