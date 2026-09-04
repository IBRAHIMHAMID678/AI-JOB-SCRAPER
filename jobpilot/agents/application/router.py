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
    route_type: str  # GREENHOUSE, LEVER, WORKDAY, GOOGLE_FORM, EMAIL, COMPANY_FORM, MANUAL
    target_email: Optional[str] = None
    ats_name: Optional[str] = None
    requires_login: bool = False


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
        )

    if "greenhouse.io" in url_lower or "boards.greenhouse.io" in url_lower:
        return ApplicationRoute(url=url, route_type="GREENHOUSE", ats_name="Greenhouse")

    if "lever.co" in url_lower or "jobs.lever.co" in url_lower:
        return ApplicationRoute(url=url, route_type="LEVER", ats_name="Lever")

    if "myworkdayjobs.com" in url_lower or "workday" in url_lower:
        return ApplicationRoute(url=url, route_type="WORKDAY", ats_name="Workday", requires_login=True)

    if "forms.gle" in url_lower or "docs.google.com/forms" in url_lower:
        return ApplicationRoute(url=url, route_type="GOOGLE_FORM", ats_name="Google Form")

    return ApplicationRoute(url=url, route_type="COMPANY_FORM", ats_name="Generic Browser")


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
