"""
Candidate Profile Service — Multi-user profile management.
All form fillers and evaluation engines consume profile data dynamically
from the authenticated user's profile and uploaded CV.
"""
from __future__ import annotations

import os
import pathlib
from datetime import date
from typing import Any, Dict, List, Optional
from .config import settings


def get_canonical_candidate_profile(user_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Returns candidate profile data.
    If a user_profile dictionary is passed, it uses that data.
    Otherwise, returns configurable generic defaults (never hardcoded personal identities).
    """
    up = user_profile or {}

    name = up.get("name") or settings.CANDIDATE_NAME or "Job Seeker"
    parts = name.split()
    first_name = up.get("first_name") or (parts[0] if parts else "Job")
    last_name = up.get("last_name") or (" ".join(parts[1:]) if len(parts) > 1 else "Seeker")
    email = up.get("email") or settings.CANDIDATE_EMAIL or "user@example.com"
    phone_raw = up.get("phone") or getattr(settings, "CANDIDATE_PHONE", None) or "+1 555 0100"

    digits_only = "".join(filter(str.isdigit, phone_raw))
    location = up.get("location") or settings.CANDIDATE_LOCATION or "Remote"

    return {
        # Identity
        "first_name": first_name,
        "last_name": last_name,
        "full_name": name,
        "email": email,
        "phone": phone_raw,
        "phone_intl": f"+{digits_only}" if digits_only else phone_raw,
        "phone_national": digits_only,
        "phone_country_code": "+1" if not phone_raw.startswith("+") else phone_raw.split()[0] if " " in phone_raw else phone_raw[:3],
        "city": up.get("city") or "Remote",
        "state": up.get("state") or "",
        "country": up.get("country") or "Worldwide",
        "location": location,
        "address": location,
        "timezone": getattr(settings, "CANDIDATE_TIMEZONE", "UTC"),

        # Online Profiles
        "linkedin": up.get("linkedin_url") or "",
        "linkedin_url": up.get("linkedin_url") or "",
        "github": up.get("github_url") or "",
        "github_url": up.get("github_url") or "",
        "portfolio": up.get("portfolio_url") or "",
        "portfolio_url": up.get("portfolio_url") or "",

        # Work Authorization & Geographic Eligibility
        "work_authorization": "Yes",
        "authorized_in_country": "Yes",
        "authorized_to_work": "Authorized to work remotely worldwide",
        "citizenship": up.get("country") or "Worldwide",
        "eligible_countries": ["Worldwide Remote", "Anywhere", "Remote"],
        "visa_needed": "No",
        "visa_sponsorship": "No",
        "sponsorship_needed": "No",
        "currently_employed": "Yes",
        "notice_period": "Immediately",
        "earliest_start_date": date.today().strftime("%Y-%m-%d"),
        "employment_type_pref": "Full-time, Contract, Remote",
        "available_immediately": "Yes",
        "remote_ok": "Yes",
        "remote_preference": up.get("remote_preference") or "Worldwide Remote",

        # Education
        "education_level": "Bachelor's Degree",
        "highest_education": "Bachelor's Degree",
        "degree": up.get("degree") or "Bachelor of Science in Computer Science",
        "field_of_study": "Computer Science",
        "institution": up.get("institution") or "University",
        "university": up.get("institution") or "University",
        "graduation_month": "July",
        "graduation_date": "2026-07-01",

        # Professional & Experience
        "title": up.get("title") or "Software Engineer",
        "current_title": up.get("title") or "Software Engineer",
        "current_company": up.get("company") or "Technology Solutions",
        "experience_years": up.get("experience_years", 2),
        "years_experience": up.get("experience_years", 2),
        "industry": up.get("industry") or "Software Engineering",

        # Technical Skills
        "skills": ", ".join(up.get("skills", ["Python", "FastAPI", "React", "TypeScript", "SQL"])),
        "skills_list": up.get("skills", ["Python", "FastAPI", "React", "TypeScript", "SQL"]),
        "primary_skills": "Python, FastAPI, React",
        "languages": "English (Fluent)",

        # Compensation
        "salary_range": "$30 - $60 per hour",
        "salary_min_usd": str(up.get("salary_min_usd", 30)),
        "salary_max_usd": str(up.get("salary_max_usd", 60)),
        "hourly_rate": "$30/hr",
        "desired_salary": "$60,000",
        "currency": "USD",

        # Summary
        "about_me": up.get("summary") or "Software Engineer with hands-on experience building web applications, scalable backend APIs, and modern frontend interfaces.",
        "why_interested": "I am interested in this role to contribute technical skills and solve real-world problems with scalable code.",
        "project_experience": "Architected and built full-stack applications with FastAPI, modern web frontends, and automated RAG data pipelines.",
        "discipline": "Computer Science",
    }


def resolve_resume_path(cv_path: Optional[str] = None) -> Optional[str]:
    """Finds and validates the resume PDF file if provided."""
    if cv_path and os.path.exists(cv_path) and os.path.getsize(cv_path) > 0:
        return os.path.abspath(cv_path)
    return None
