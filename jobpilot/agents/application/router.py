"""
Application Router & Field Classifier Module

Detects application mechanisms (Greenhouse, Lever, Google Forms, Workday, Email, Company Form)
and classifies DOM fields by label, placeholder, name, and accessibility semantics.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from ...core.logging import get_logger

logger = get_logger("application.router")


class ApplicationRoute(BaseModel):
    url: str
    route_type: str  # GREENHOUSE, LEVER, ASHBY, WORKDAY, GOOGLE_FORM, EMAIL, COMPANY_FORM, MANUAL
    target_email: Optional[str] = None
    ats_name: Optional[str] = None
    requires_login: bool = False
    requires_otp: bool = False
    is_apply_compatible: bool = True
    incompatibility_reason: Optional[str] = None


def is_form_apply_compatible(url: str, page_content: str = "", page_obj=None) -> tuple[bool, str]:
    """
    Checks if a given job application URL/page can be autonomously applied to.
    Returns (compatible, reason).
    Detects login walls, password fields, OTP/2FA verification, and complex ATS barriers.
    """
    url_lower = url.lower()
    
    # 1. Known login-walled enterprise ATS platforms
    walled_domains = [
        ("myworkdayjobs.com", "Workday login wall required"),
        ("workday.com", "Workday login wall required"),
        ("taleo.net", "Taleo portal login wall required"),
        ("icims.com", "iCIMS account creation required"),
        ("successfactors.com", "SAP SuccessFactors portal login wall required"),
        ("brassring.com", "BrassRing login wall required"),
        ("oraclecloud.com", "Oracle Cloud recruiter login required"),
    ]
    for domain, reason in walled_domains:
        if domain in url_lower:
            return False, reason

    # 2. Known high-compatibility open ATS platforms
    if "greenhouse.io" in url_lower or "job-boards.greenhouse.io" in url_lower:
        return True, "Greenhouse direct open form"
    if "lever.co" in url_lower or "jobs.lever.co" in url_lower:
        return True, "Lever direct open form"
    if "ashbyhq.com" in url_lower:
        return True, "Ashby direct open form"

    # 3. Check page object (if rendered by Playwright)
    if page_obj is not None:
        try:
            for frame in page_obj.frames:
                # Password field indicates account creation wall
                if frame.locator("input[type='password']").count() > 0:
                    return False, "Password / account creation wall detected in form DOM"
                
                # Check for OTP inputs or texts
                body_text = (frame.inner_text("body") or "").lower()
                otp_triggers = [
                    "enter the 6-digit code", "enter verification code", "one-time password",
                    "otp sent to", "enter the code sent", "check your email for code",
                    "two-step verification", "2-step verification"
                ]
                if any(k in body_text for k in otp_triggers):
                    return False, "OTP / 2FA SMS/Email verification required"

                if any(k in body_text for k in ["sign in to apply", "create an account to apply", "log in with your account"]):
                    return False, "Login wall detected on application landing page"
        except Exception:
            pass

    # 4. Check raw page content
    if page_content:
        content_lower = page_content.lower()
        if 'type="password"' in content_lower or "type='password'" in content_lower:
            return False, "Password / account creation wall detected"
        if any(k in content_lower for k in ["enter verification code", "one-time password", "otp verification", "enter the 6-digit code"]):
            return False, "OTP verification required"
        if any(k in content_lower for k in ["sign in to apply", "create an account to continue", "log in to apply"]):
            return False, "Login wall required"

    return True, "Form appears open and compatible"


def classify_application_url(url: str, page_content: str = "") -> ApplicationRoute:
    """
    Classifies an application URL into its specialized agent handler route.
    """
    url_lower = url.lower()

    if "mailto:" in url_lower or (re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', url) and "http" not in url):
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', url)
        return ApplicationRoute(
            url=url,
            route_type="EMAIL",
            target_email=email_match.group(0) if email_match else None,
            is_apply_compatible=True,
        )

    if "greenhouse.io" in url_lower or "boards.greenhouse.io" in url_lower or "job-boards.greenhouse.io" in url_lower:
        return ApplicationRoute(url=url, route_type="GREENHOUSE", ats_name="Greenhouse", is_apply_compatible=True)

    if "lever.co" in url_lower or "jobs.lever.co" in url_lower:
        return ApplicationRoute(url=url, route_type="LEVER", ats_name="Lever", is_apply_compatible=True)

    if "ashbyhq.com" in url_lower:
        return ApplicationRoute(url=url, route_type="ASHBY", ats_name="Ashby", is_apply_compatible=True)

    if "myworkdayjobs.com" in url_lower or "workday" in url_lower:
        return ApplicationRoute(
            url=url,
            route_type="WORKDAY",
            ats_name="Workday",
            requires_login=True,
            is_apply_compatible=False,
            incompatibility_reason="Workday login wall required",
        )

    if "forms.gle" in url_lower or "docs.google.com/forms" in url_lower:
        return ApplicationRoute(url=url, route_type="GOOGLE_FORM", ats_name="Google Form", is_apply_compatible=True)

    compatible, reason = is_form_apply_compatible(url, page_content)
    return ApplicationRoute(
        url=url,
        route_type="COMPANY_FORM",
        ats_name="Generic Browser",
        requires_login=not compatible and "login" in reason.lower(),
        requires_otp=not compatible and "otp" in reason.lower(),
        is_apply_compatible=compatible,
        incompatibility_reason=None if compatible else reason,
    )


def classify_form_field(label: str, field_type: str = "text", placeholder: str = "") -> str:
    """
    Classifies a form input field into standardized candidate profile keys.
    """
    combined = (label + " " + placeholder).lower()

    if any(k in combined for k in ["first name", "given name"]):
        return "FIRST_NAME"
    if any(k in combined for k in ["last name", "surname", "family name"]):
        return "LAST_NAME"
    if any(k in combined for k in ["full name", "your name"]):
        return "FULL_NAME"
    if any(k in combined for k in ["email", "e-mail"]):
        return "EMAIL"
    if any(k in combined for k in ["phone", "mobile", "contact number"]):
        return "PHONE"
    if any(k in combined for k in ["linkedin", "profile link"]):
        return "LINKEDIN_URL"
    if any(k in combined for k in ["github", "portfolio"]):
        return "GITHUB_URL"
    if any(k in combined for k in ["resume", "cv", "attach file"]):
        return "RESUME_FILE"
    if any(k in combined for k in ["cover letter"]):
        return "COVER_LETTER"
    if any(k in combined for k in ["salary", "desired pay"]):
        return "EXPECTED_SALARY"
    if any(k in combined for k in ["sponsorship", "visa"]):
        return "WORK_AUTHORIZATION"

    return "CUSTOM_QUESTION"
