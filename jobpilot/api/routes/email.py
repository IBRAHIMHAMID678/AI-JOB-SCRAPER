"""
Email OAuth routes for JOBPILOT.

GET  /api/email/status        — is Gmail authorized?
GET  /api/email/auth          — get the Google login URL
GET  /api/email/callback      — Google redirects here after authorization
POST /api/email/scan          — manually trigger inbox scan
GET  /api/email/results       — last scan results
DELETE /api/email/disconnect  — remove stored tokens
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from ...integrations.email.oauth import get_email_client, classify_email
from ...core.logging import get_logger

router = APIRouter(tags=["email"])
logger = get_logger(__name__)

_last_scan_results: list = []


@router.get("/email/status")
def email_status() -> Dict[str, Any]:
    """Check whether Gmail is connected."""
    client = get_email_client()
    return {
        "configured": client.is_configured,
        "authorized": client.is_authorized if client.is_configured else False,
        "provider": "gmail",
        "message": (
            "Gmail connected and ready"
            if client.is_configured and client.is_authorized
            else "Visit /api/email/auth to connect Gmail"
            if client.is_configured
            else "Set EMAIL_OAUTH_CLIENT_ID and EMAIL_OAUTH_CLIENT_SECRET in .env"
        ),
    }


@router.get("/email/auth")
def email_auth():
    """
    Returns the Google OAuth URL.
    Open this URL in a browser to authorize Gmail access.
    """
    client = get_email_client()
    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Gmail OAuth not configured. Set EMAIL_OAUTH_CLIENT_ID and "
                   "EMAIL_OAUTH_CLIENT_SECRET in your .env file.",
        )
    url = client.get_auth_url()
    return {"auth_url": url, "instructions": "Open this URL in your browser to connect Gmail."}


@router.get("/email/callback")
def email_callback(code: str = Query(...), error: str = Query(None)):
    """
    Google redirects here after the user authorizes.
    Exchanges the code for tokens and stores them.
    """
    if error:
        return HTMLResponse(
            content=f"<h2>Authorization failed: {error}</h2>"
                    "<p>Close this tab and try again from the dashboard.</p>",
            status_code=400,
        )

    client = get_email_client()
    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Gmail OAuth not configured")

    try:
        token_response = client.exchange_code(code)
        client.save_tokens_from_exchange(token_response)
        logger.info("Gmail OAuth tokens saved successfully")
        return HTMLResponse(
            content="""
            <html><body style="font-family:sans-serif;padding:40px;background:#0E1013;color:#E4E7EC">
            <h2 style="color:#3FA98A">✓ Gmail Connected Successfully</h2>
            <p>JOBPILOT can now scan your inbox for application updates.</p>
            <p style="color:#9BA3AF">You can close this tab and return to the dashboard.</p>
            <script>setTimeout(()=>window.close(),3000)</script>
            </body></html>
            """
        )
    except Exception as exc:
        logger.error("Gmail token exchange failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}")


@router.post("/email/scan")
def email_scan() -> Dict[str, Any]:
    """
    Manually trigger a Gmail inbox scan.
    Classifies emails and returns results.
    Also updates application statuses in the DB where possible.
    """
    global _last_scan_results
    client = get_email_client()

    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Gmail not configured. Set EMAIL_OAUTH_CLIENT_ID and EMAIL_OAUTH_CLIENT_SECRET.",
        )
    if not client.is_authorized:
        raise HTTPException(
            status_code=401,
            detail="Gmail not authorized. Visit /api/email/auth to connect.",
        )

    results = client.scan_inbox()
    _last_scan_results = results

    # Auto-update application statuses based on email classification
    updated = _apply_email_classifications(results)

    return {
        "scanned": len(results),
        "applications_updated": updated,
        "results": results,
    }


@router.get("/email/results")
def email_results() -> Dict[str, Any]:
    """Return the results from the last inbox scan."""
    return {
        "count": len(_last_scan_results),
        "results": _last_scan_results,
    }


@router.delete("/email/disconnect")
def email_disconnect() -> Dict[str, str]:
    """Remove stored Gmail tokens (disconnect)."""
    try:
        from ...core.database import db_session
        from ...core.models import SystemSetting
        with db_session() as db:
            db.query(SystemSetting).filter_by(key="EMAIL_OAUTH_TOKENS").delete()
        global _last_scan_results
        _last_scan_results = []
        logger.info("Gmail tokens removed")
        return {"status": "disconnected"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _apply_email_classifications(results: list) -> int:
    """
    Match classified emails to applications and update their status.
    Returns count of applications updated.
    """
    if not results:
        return 0

    updated = 0
    try:
        from ...core.database import db_session
        from ...core.models import Application, ApplicationStatus

        classification_to_status = {
            "interview": ApplicationStatus.INTERVIEW,
            "offer": ApplicationStatus.OFFER,
            "confirmation": ApplicationStatus.CONFIRMED,
        }

        with db_session() as db:
            for email in results:
                classification = email.get("classification")
                new_status = classification_to_status.get(classification)
                if not new_status:
                    continue

                sender = email.get("sender", "").lower()
                subject = email.get("subject", "").lower()

                # Try to match by company name in sender domain or subject
                apps = db.query(Application).filter(
                    Application.status.notin_([
                        ApplicationStatus.OFFER,
                        ApplicationStatus.OFFER_REJECTED,
                        ApplicationStatus.WITHDRAWN,
                    ])
                ).all()

                for app in apps:
                    company = (app.job.company if app.job else "").lower()
                    if not company:
                        continue
                    company_words = [w for w in company.split() if len(w) > 3]
                    if any(w in sender or w in subject for w in company_words):
                        if app.status != new_status:
                            app.status = new_status
                            logger.info(
                                "Auto-updated application %s → %s (from email: %s)",
                                app.id, new_status.value, subject[:60],
                            )
                            updated += 1
                        break
    except Exception as exc:
        logger.error("Email → application status update failed: %s", exc)

    return updated
