"""
Submission Verification & Evidence Engine for JOBPILOT.
Guarantees that no application can ever be marked SUBMITTED without affirmative browser-level proof.

Evidence sources:
- Navigation to explicit confirmation URL (/confirmation, /thanks, /submitted, etc.)
- Affirmative confirmation headings / containers in the DOM
- Formal application reference or confirmation ID
- Disappearance of form followed by verified success state

If evidence is missing or uncertain, records SUBMISSION_UNCONFIRMED or VALIDATION_BLOCKED.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel

from .logging import get_logger

logger = get_logger("core.submission_verifier")


class SubmissionEvidence(BaseModel):
    is_confirmed: bool = False
    status: str = "SUBMISSION_UNCONFIRMED"  # SUBMITTED, SUBMISSION_UNCONFIRMED, VALIDATION_BLOCKED, FAILED
    platform: str = "unknown"
    submission_attempted_at: Optional[str] = None
    confirmation_detected_at: Optional[str] = None
    confirmation_type: Optional[str] = None   # "url_transition", "dom_confirmation_heading", "ats_reference_badge"
    confirmation_text: Optional[str] = None
    final_url: Optional[str] = None
    screenshot_path: Optional[str] = None
    validation_errors_before_submit: List[Dict[str, str]] = []
    validation_errors_after_submit: List[Dict[str, str]] = []
    notes: Optional[str] = None


CONFIRMATION_URL_PATTERNS = [
    r"/confirmation",
    r"/confirmed",
    r"/thanks",
    r"/thank-you",
    r"/application-submitted",
    r"/success",
    r"status=submitted",
    r"submitted=true",
]

CONFIRMATION_TEXT_PATTERNS = [
    "thank you for applying",
    "thank you for your application",
    "application submitted",
    "application has been submitted",
    "application received",
    "your application was sent",
    "we've received your application",
    "we have received your application",
    "submission successful",
    "your application has been received",
]

CONFIRMATION_SELECTORS = [
    "#application_confirmation",
    ".application-confirmation",
    ".confirmation-message",
    "[data-qa='confirmation']",
    ".postings-confirmation",
    ".submitted-message",
    "div:has-text('Thank you for applying')",
    "h1:has-text('Application Submitted')",
    "h2:has-text('Application Submitted')",
]


def collect_validation_errors(page) -> List[Dict[str, str]]:
    """
    Scans the current page for visible validation errors before or after submit attempt.
    """
    errors: List[Dict[str, str]] = []
    try:
        # Check standard input aria-invalid attributes
        invalids = page.locator("[aria-invalid='true']").all()
        for el in invalids:
            if el.is_visible():
                name = el.get_attribute("name") or el.get_attribute("id") or "field"
                errors.append({"field": name, "type": "aria-invalid", "message": "Field marked invalid by form"})

        # Check greenhouse and general error class elements
        error_locators = page.locator(
            ".field-error, .error, .error-message, .invalid-feedback, [class*='errorMessage'], [id*='error']"
        ).all()
        for err in error_locators:
            try:
                if err.is_visible():
                    txt = (err.text_content() or "").strip()
                    if txt and len(txt) < 200:
                        errors.append({"field": "unknown", "type": "visible_error", "message": txt})
            except Exception:
                pass

        # Check for HTML5 required fields that are empty
        empty_required = page.locator("input[required]:empty, select[required]:empty, textarea[required]:empty").all()
        for req in empty_required:
            try:
                if req.is_visible() and not req.input_value():
                    name = req.get_attribute("name") or req.get_attribute("id") or "required_field"
                    errors.append({"field": name, "type": "required_empty", "message": "Required field is empty"})
            except Exception:
                pass

    except Exception as exc:
        logger.debug("Error collecting validation errors: %s", exc)

    return errors


def verify_submission(
    page,
    platform: str,
    application_id: str,
    screenshot_dir: str = r"d:\Job Scraper\jobpilot\screenshots",
) -> SubmissionEvidence:
    """
    Conducts strict DOM & URL inspection to verify whether an application was truly submitted.
    Takes a timestamped screenshot as persistent proof.
    """
    attempted_time = datetime.utcnow().isoformat()
    evidence = SubmissionEvidence(
        platform=platform,
        submission_attempted_at=attempted_time,
    )

    os.makedirs(screenshot_dir, exist_ok=True)
    shot_filename = f"{application_id}_{platform}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
    shot_path = os.path.join(screenshot_dir, shot_filename)

    try:
        page.screenshot(path=shot_path, full_page=False)
        evidence.screenshot_path = shot_path
    except Exception as e:
        logger.warning("Could not capture verification screenshot: %s", e)

    try:
        final_url = page.url or ""
        evidence.final_url = final_url

        # Check remaining validation errors after submit
        errors_after = collect_validation_errors(page)
        evidence.validation_errors_after_submit = errors_after

        if errors_after:
            evidence.is_confirmed = False
            evidence.status = "VALIDATION_BLOCKED"
            evidence.notes = f"Validation errors remained after submit: {errors_after}"
            logger.warning("[SUBMISSION VERIFY] Blocked by validation on %s: %s", final_url, errors_after)
            return evidence

        # Evidence 1: Confirmation URL
        for url_pattern in CONFIRMATION_URL_PATTERNS:
            if re.search(url_pattern, final_url, re.IGNORECASE):
                evidence.is_confirmed = True
                evidence.status = "SUBMITTED"
                evidence.confirmation_type = "url_transition"
                evidence.confirmation_detected_at = datetime.utcnow().isoformat()
                evidence.confirmation_text = f"URL matched confirmation pattern: {url_pattern}"
                logger.info("[SUBMISSION VERIFY] CONFIRMED via URL transition: %s", final_url)
                return evidence

        # Evidence 2: Confirmation DOM selectors
        for sel in CONFIRMATION_SELECTORS:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0 and elem.is_visible():
                    txt = (elem.text_content() or "").strip()
                    evidence.is_confirmed = True
                    evidence.status = "SUBMITTED"
                    evidence.confirmation_type = "dom_confirmation_heading"
                    evidence.confirmation_detected_at = datetime.utcnow().isoformat()
                    evidence.confirmation_text = txt[:200]
                    logger.info("[SUBMISSION VERIFY] CONFIRMED via DOM selector '%s': %s", sel, txt[:100])
                    return evidence
            except Exception:
                pass

        # Evidence 3: Affirmative Confirmation text in body (ONLY IF form inputs have disappeared)
        try:
            body_text = (page.inner_text("body") or "").lower()
            remaining_inputs = page.locator("input[type='email'], input[name*='email']").count()
            if remaining_inputs == 0:
                for pattern in CONFIRMATION_TEXT_PATTERNS:
                    if pattern in body_text:
                        evidence.is_confirmed = True
                        evidence.status = "SUBMITTED"
                        evidence.confirmation_type = "confirmation_text_body"
                        evidence.confirmation_detected_at = datetime.utcnow().isoformat()
                        evidence.confirmation_text = pattern
                        logger.info("[SUBMISSION VERIFY] CONFIRMED via body text: '%s'", pattern)
                        return evidence
        except Exception:
            pass

        # If no affirmative confirmation evidence found
        evidence.is_confirmed = False
        evidence.status = "SUBMISSION_UNCONFIRMED"
        evidence.notes = "Form was submitted but no affirmative confirmation screen or URL transition was detected"
        logger.warning("[SUBMISSION VERIFY] UNCONFIRMED submission on %s — marking SUBMISSION_UNCONFIRMED", final_url)

    except Exception as exc:
        evidence.is_confirmed = False
        evidence.status = "FAILED"
        evidence.notes = f"Exception during submission verification: {exc}"
        logger.error("[SUBMISSION VERIFY] Verification error: %s", exc)

    return evidence
