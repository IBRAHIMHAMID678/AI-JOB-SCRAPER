"""
Auto-apply engine.

Strategy per source:
  - Email apply  : detect apply email in description → send email with CV attached
  - LinkedIn      : Playwright Easy Apply flow (requires LINKEDIN_EMAIL/PASSWORD)
  - Indeed        : Playwright Easy Apply flow (requires INDEED_EMAIL/PASSWORD)
  - Rozee.pk      : Playwright apply flow (requires ROZEE_EMAIL/PASSWORD)
  - Other sites   : Playwright generic form detection → fill + submit

Daily limits enforced:
  Tier 1 (90%+) : DAILY_APPLY_LIMIT_TIER1 per day
  Tier 2 (80-89%): DAILY_APPLY_LIMIT_TIER2 per day
"""
from __future__ import annotations

import re
import smtplib
import pathlib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from typing import Optional

from ..core.config import settings
from ..core.database import db_session
from ..core.models import DailyApplyLog, Application, ApplicationStatus
from ..core.logging import get_logger
from .telegram_service import notify_applied, notify_error

logger = get_logger(__name__)

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)
APPLY_EMAIL_KEYWORDS = ["apply", "career", "hr", "recruit", "job", "talent", "hiring"]


# ── Daily limit helpers ────────────────────────────────────────────────────────

def _get_today() -> str:
    return date.today().isoformat()


def get_daily_count(tier: int) -> int:
    with db_session() as db:
        log = db.query(DailyApplyLog).filter_by(date=_get_today(), tier=tier).first()
        return log.count if log else 0


def _increment_daily(tier: int) -> None:
    today = _get_today()
    with db_session() as db:
        log = db.query(DailyApplyLog).filter_by(date=today, tier=tier).first()
        if log:
            log.count += 1
        else:
            db.add(DailyApplyLog(date=today, tier=tier, count=1))


def can_apply(score: int) -> bool:
    if score >= settings.TIER1_SCORE_MIN:
        return get_daily_count(1) < settings.DAILY_APPLY_LIMIT_TIER1
    if score >= settings.TIER2_SCORE_MIN:
        return get_daily_count(2) < settings.DAILY_APPLY_LIMIT_TIER2
    return False


def _tier(score: int) -> int:
    return 1 if score >= settings.TIER1_SCORE_MIN else 2


# ── Email apply ────────────────────────────────────────────────────────────────

def _find_apply_email(description: str) -> Optional[str]:
    emails = EMAIL_PATTERN.findall(description)
    for email in emails:
        local = email.split("@")[0].lower()
        if any(kw in local for kw in APPLY_EMAIL_KEYWORDS):
            return email
    return emails[0] if emails else None


def _send_email_application(
    to_email: str,
    job_title: str,
    company: str,
    cv_path: str,
    cover_letter: str,
    candidate_name: str,
    candidate_email: str,
) -> bool:
    smtp_host = getattr(settings, "SMTP_HOST", None)
    smtp_user = getattr(settings, "SMTP_USER", None)
    smtp_pass = getattr(settings, "SMTP_PASS", None)

    if not all([smtp_host, smtp_user, smtp_pass]):
        logger.warning("SMTP not configured — cannot send email application")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{candidate_name} <{candidate_email}>"
        msg["To"] = to_email
        msg["Subject"] = f"Application for {job_title} — {candidate_name}"

        body = cover_letter or (
            f"Dear Hiring Team,\n\nI am applying for the {job_title} position at {company}. "
            f"Please find my CV attached.\n\nBest regards,\n{candidate_name}"
        )
        msg.attach(MIMEText(body, "plain"))

        if cv_path and pathlib.Path(cv_path).exists():
            with open(cv_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            fname = pathlib.Path(cv_path).name
            part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
            msg.attach(part)

        port = getattr(settings, "SMTP_PORT", 587)
        with smtplib.SMTP(smtp_host, port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False


# ── Playwright apply ───────────────────────────────────────────────────────────

def _playwright_apply(url: str, source: str, cv_path: str, cover_letter: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed — skipping browser apply")
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            if "linkedin.com" in url:
                return _linkedin_easy_apply(page, url, cv_path, cover_letter)
            if "indeed.com" in url:
                return _indeed_apply(page, url, cv_path)
            if "rozee.pk" in url:
                return _rozee_apply(page, url, cv_path)
            return _generic_apply(page, url, cv_path)
    except Exception as exc:
        logger.error("Playwright apply failed for %s: %s", url, exc)
        return False


def _linkedin_easy_apply(page, url: str, cv_path: str, cover_letter: str) -> bool:
    if not settings.LINKEDIN_EMAIL:
        return False
    try:
        page.goto("https://www.linkedin.com/login", timeout=15000)
        page.fill("#username", settings.LINKEDIN_EMAIL)
        page.fill("#password", settings.LINKEDIN_PASSWORD or "")
        page.click("[type=submit]")
        page.wait_for_timeout(3000)
        page.goto(url, timeout=15000)
        page.wait_for_timeout(2000)

        easy_btn = page.query_selector(".jobs-apply-button, button:has-text('Easy Apply')")
        if not easy_btn:
            return False
        easy_btn.click()
        page.wait_for_timeout(2000)

        # Upload CV if file input exists
        file_input = page.query_selector("input[type=file]")
        if file_input and cv_path and pathlib.Path(cv_path).exists():
            file_input.set_input_files(cv_path)
            page.wait_for_timeout(1000)

        # Click through multi-step form
        for _ in range(6):
            next_btn = page.query_selector("button:has-text('Next'), button:has-text('Review')")
            if not next_btn:
                break
            next_btn.click()
            page.wait_for_timeout(1500)

        submit_btn = page.query_selector("button:has-text('Submit application')")
        if submit_btn:
            submit_btn.click()
            page.wait_for_timeout(2000)
            return True
        return False
    except Exception as exc:
        logger.warning("LinkedIn apply error: %s", exc)
        return False


def _indeed_apply(page, url: str, cv_path: str) -> bool:
    if not settings.INDEED_EMAIL:
        return False
    try:
        page.goto(url, timeout=15000)
        page.wait_for_timeout(2000)
        apply_btn = page.query_selector("button:has-text('Apply now'), .indeed-apply-button")
        if not apply_btn:
            return False
        apply_btn.click()
        page.wait_for_timeout(2000)

        email_input = page.query_selector("input[type=email], input[name=email]")
        if email_input:
            email_input.fill(settings.INDEED_EMAIL)

        file_input = page.query_selector("input[type=file]")
        if file_input and cv_path and pathlib.Path(cv_path).exists():
            file_input.set_input_files(cv_path)

        submit = page.query_selector("button:has-text('Submit'), button[type=submit]")
        if submit:
            submit.click()
            page.wait_for_timeout(2000)
            return True
        return False
    except Exception as exc:
        logger.warning("Indeed apply error: %s", exc)
        return False


def _rozee_apply(page, url: str, cv_path: str) -> bool:
    if not settings.ROZEE_EMAIL:
        return False
    try:
        page.goto("https://www.rozee.pk/login", timeout=15000)
        page.fill("input[name=email], #email", settings.ROZEE_EMAIL)
        page.fill("input[name=password], #password", settings.ROZEE_PASSWORD or "")
        page.click("button[type=submit], .login-btn")
        page.wait_for_timeout(3000)
        page.goto(url, timeout=15000)
        page.wait_for_timeout(2000)

        apply_btn = page.query_selector(".apply-btn, button:has-text('Apply')")
        if apply_btn:
            apply_btn.click()
            page.wait_for_timeout(2000)
            return True
        return False
    except Exception as exc:
        logger.warning("Rozee apply error: %s", exc)
        return False


def _generic_apply(page, url: str, cv_path: str) -> bool:
    try:
        page.goto(url, timeout=20000)
        page.wait_for_timeout(2000)

        apply_btn = page.query_selector(
            "a:has-text('Apply'), button:has-text('Apply'), "
            "a:has-text('Apply Now'), button:has-text('Apply Now')"
        )
        if apply_btn:
            apply_btn.click()
            page.wait_for_timeout(2000)

        file_input = page.query_selector("input[type=file]")
        if file_input and cv_path and pathlib.Path(cv_path).exists():
            file_input.set_input_files(cv_path)
            page.wait_for_timeout(1000)

        email_input = page.query_selector("input[type=email]")
        if email_input:
            email_input.fill(settings.CANDIDATE_EMAIL)

        submit = page.query_selector("button[type=submit], input[type=submit]")
        if submit:
            submit.click()
            page.wait_for_timeout(2000)
            return True
        return False
    except Exception as exc:
        logger.warning("Generic apply error: %s", exc)
        return False


# ── Main entry point ───────────────────────────────────────────────────────────

def apply_to_job(
    job_id: str,
    job_title: str,
    company: str,
    source: str,
    apply_url: str,
    score: int,
    description: str,
    cv_path: str,
    cover_letter: str = "",
) -> bool:
    """
    Attempt to apply to a job. Enforces daily limits.
    Returns True if application was submitted successfully.
    """
    if not can_apply(score):
        logger.info("Daily limit reached for tier %d — skipping %s", _tier(score), job_title)
        return False

    success = False

    # Strategy 1: email apply
    apply_email = _find_apply_email(description)
    if apply_email:
        logger.info("Applying via email to %s at %s", job_title, apply_email)
        success = _send_email_application(
            to_email=apply_email,
            job_title=job_title,
            company=company,
            cv_path=cv_path,
            cover_letter=cover_letter,
            candidate_name=settings.CANDIDATE_NAME,
            candidate_email=settings.CANDIDATE_EMAIL,
        )

    # Strategy 2: browser apply
    if not success:
        logger.info("Applying via browser to %s @ %s", job_title, apply_url)
        success = _playwright_apply(apply_url, source, cv_path, cover_letter)

    if success:
        _increment_daily(_tier(score))
        _mark_submitted(job_id)
        notify_applied(job_title, company, source, score, apply_url)
        logger.info("Successfully applied: %s @ %s (score=%d)", job_title, company, score)
    else:
        logger.warning("Could not auto-apply to %s @ %s — marked for manual review", job_title, company)

    return success


def _mark_submitted(job_id: str) -> None:
    try:
        with db_session() as db:
            app = db.query(Application).filter_by(job_id=job_id).first()
            if app:
                app.status = ApplicationStatus.SUBMITTED.value
                from datetime import datetime
                app.submitted_at = datetime.utcnow()
    except Exception as exc:
        logger.error("Failed to mark submitted: %s", exc)
