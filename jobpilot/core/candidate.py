"""
Canonical Candidate Profile — Single Source of Truth for Ibrahim Hamid.
All ATS adapters, form fillers, and evaluation engines consume this profile.

Education note:
Graduated: July 2026 (Bachelor of Science in Computer Science)
University: Capital University of Science and Technology (CUST), Islamabad, Pakistan
"""
from __future__ import annotations

import os
import pathlib
from datetime import date
from typing import Any, Dict, List, Optional
from .config import settings


def get_canonical_candidate_profile() -> Dict[str, Any]:
    """
    Returns the authoritative, canonical candidate profile for Ibrahim Hamid.
    Never invents unverified data.
    """
    name = settings.CANDIDATE_NAME or "Ibrahim Hamid"
    parts = name.split()
    first_name = parts[0] if parts else "Ibrahim"
    last_name = " ".join(parts[1:]) if len(parts) > 1 else "Hamid"
    email = settings.CANDIDATE_EMAIL or "ibrahimhamid.2600@gmail.com"
    phone_raw = getattr(settings, "CANDIDATE_PHONE", None) or "+923180584128"

    # Normalize phone representation
    # Pakistan: country code +92, national subscriber number 3180584128
    digits_only = "".join(filter(str.isdigit, phone_raw))
    if digits_only.startswith("92"):
        national_number = digits_only[2:]
    elif digits_only.startswith("0"):
        national_number = digits_only[1:]
    else:
        national_number = digits_only

    location = settings.CANDIDATE_LOCATION or "Islamabad, Pakistan"

    return {
        # Identity
        "first_name": first_name,
        "last_name": last_name,
        "full_name": name,
        "email": email,
        "phone": f"+92 {national_number[:3]} {national_number[3:]}",
        "phone_intl": f"+92{national_number}",
        "phone_country_code": "+92",
        "phone_dial_code": "92",
        "phone_national": national_number,       # e.g. "3180584128"
        "phone_national_with_zero": f"0{national_number}",  # e.g. "03180584128"
        "city": "Islamabad",
        "state": "Islamabad Capital Territory",
        "province": "Federal",
        "country": "Pakistan",
        "country_code": "PK",
        "location": location,
        "address": "Islamabad, Pakistan",
        "street_address": "Sector H-12, Islamabad",
        "zip": "44000",
        "postal_code": "44000",
        "timezone": getattr(settings, "CANDIDATE_TIMEZONE", None) or "Asia/Karachi",
        "utc_offset": "+05:00",

        # Online Profiles
        "linkedin": getattr(settings, "CANDIDATE_LINKEDIN", None) or "https://linkedin.com/in/ibrahim-hamid678",
        "linkedin_url": getattr(settings, "CANDIDATE_LINKEDIN", None) or "https://linkedin.com/in/ibrahim-hamid678",
        "github": getattr(settings, "CANDIDATE_GITHUB", None) or "https://github.com/IBRAHIMHAMID678",
        "github_url": getattr(settings, "CANDIDATE_GITHUB", None) or "https://github.com/IBRAHIMHAMID678",
        "portfolio": getattr(settings, "CANDIDATE_PORTFOLIO", None) or "https://github.com/IBRAHIMHAMID678",
        "portfolio_url": getattr(settings, "CANDIDATE_PORTFOLIO", None) or "https://github.com/IBRAHIMHAMID678",
        "website": "https://github.com/IBRAHIMHAMID678",
        "personal_website": "https://github.com/IBRAHIMHAMID678",
        "twitter": "https://twitter.com/ibrahimhamid",

        # Work Authorization & Geographic Eligibility
        "work_authorization": "Yes",
        "authorized_in_country": "Yes",
        "authorized_to_work": "Authorized to work remotely worldwide as an independent contractor or full-time remote employee (based in Pakistan)",
        "work_authorization_short": "Yes",
        "citizenship": "Pakistan",
        "residency": "Pakistan",
        "eligible_countries": ["Pakistan", "Worldwide Remote", "Anywhere"],
        "visa_needed": "No",
        "visa_sponsorship": "No",
        "sponsorship_needed": "No",
        "sponsorship_required": "No",
        "will_require_sponsorship": "No",
        "currently_employed": "Yes",
        "notice_period": "Immediately",
        "notice_period_days": "0",
        "notice_period_weeks": "0",
        "earliest_start_date": date.today().strftime("%Y-%m-%d"),
        "start_date": date.today().strftime("%Y-%m-%d"),
        "employment_type_pref": "Full-time, Contract, Remote",
        "available_immediately": "Yes",
        "remote_ok": "Yes",
        "remote_preference": "Worldwide Remote",
        "relocation": "No, seeking remote positions",
        "security_clearance": "No",
        "legally_authorized": "Yes",

        # Education (GRADUATED JULY 2026 - CUST)
        "education_level": "Bachelor's Degree",
        "highest_education": "Bachelor's Degree",
        "degree": "Bachelor of Science in Computer Science",
        "degree_short": "BSc Computer Science",
        "field_of_study": "Computer Science",
        "major": "Computer Science",
        "university": "Capital University of Science and Technology (CUST)",
        "school": "Capital University of Science and Technology (CUST), Islamabad",
        "institution": "CUST",
        "graduation_date": "2026-07-01",
        "graduation_month": "July",
        "graduation_month_num": "07",
        "graduation_year": "2026",
        "graduation_text": "July 2026",
        "education_year": "2026",
        "gpa": "3.6/4.0",

        # Professional & Experience
        "title": "AI Engineer",
        "current_title": "AI Engineer",
        "current_company": "Brandlya Group",
        "experience_years": 2,
        "experience_years_text": "2 years",
        "years_experience": "2",
        "years_of_experience": "2",
        "industry": "Software Development / Artificial Intelligence",

        # Technical Skills
        "skills": "Python, FastAPI, Django, React, Next.js, Node.js, NestJS, TypeScript, LangChain, RAG, MongoDB Atlas, PostgreSQL, Redis, Docker, Git",
        "skills_list": [
            "Python", "FastAPI", "React", "Next.js", "Node.js", "NestJS",
            "TypeScript", "LangChain", "RAG", "MongoDB", "PostgreSQL",
            "Redis", "Docker", "Git",
        ],
        "primary_skills": "Python, FastAPI, LangChain, RAG, React",
        "languages": "English (Fluent), Urdu (Native)",
        "english_proficiency": "Fluent / Professional Working Proficiency",
        "english_level": "Fluent",

        # Compensation (ground truth: remote $10-40/hr; onsite Isb/Rwp ~PKR 100k/mo)
        "salary_range": "$10 - $40 per hour",
        "salary_min_usd": "10",
        "salary_max_usd": "40",
        "desired_salary": "$20 - $40 per hour",
        "expected_salary": "$20 - $40 per hour",
        "hourly_rate": "$30",
        "currency": "USD",

        # Structured Paragraph Answers for Custom Questions & Textareas
        "about_me": (
            "Computer Science graduate (July 2026, Capital University of Science and Technology) and Junior AI / Full-Stack Engineer "
            "with hands-on experience developing production-ready AI applications using Python, FastAPI, LangChain, and RAG "
            "architectures over vector databases (MongoDB Atlas, Pinecone). Experienced in React, Next.js, "
            "Node.js, and modern TypeScript on the frontend and backend. Passionate about building robust, "
            "scalable systems and rapid feature delivery."
        ),
        "why_interested": (
            "I am very excited about this role because it aligns directly with my core technical expertise "
            "in Python, FastAPI, React, and LLM/RAG application development. I want to contribute to high-impact "
            "products, optimize backend performance, and build intelligent features with clean, maintainable code."
        ),
        "project_experience": (
            "I contributed to Createlya (an AI-powered presentation platform with Next.js/NestJS/MongoDB vector search) "
            "and built Chatbot-Agent (multi-turn AI assistant using Python, FastAPI, React, and LangChain RAG). "
            "I have practical experience with end-to-end vector search pipelines and production API design."
        ),
        "additional_info": (
            "Available immediately for full-time or contract remote roles. Fully flexible to work across "
            "US/UK/EU time zones. High proficiency in asynchronous communication, Git workflows, and CI/CD."
        ),
        "hear_about": "LinkedIn / Online Job Board",
        "reference": "LinkedIn",
        "gender": "Male",
        "pronouns": "He/Him",
        "veteran": "No",
        "disability": "No",
        "race": "Asian",
        "ethnicity": "Asian",
    }


def resolve_resume_path(cv_path: Optional[str] = None) -> Optional[str]:
    """Finds and validates the authoritative resume PDF file.

    Candidates are resolved relative to this file (jobpilot/core/ -> repo root)
    so the lookup works regardless of the process working directory (audit item 51).
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    candidates = [
        cv_path,
        os.environ.get("CANDIDATE_RESUME_PATH"),
        str(repo_root / "jobpilot" / "uploads" / "cvs" / "Ibrahim_Hamid_Resume.pdf"),
        str(repo_root / "Ibrahim_Hamid_Resume.pdf"),
    ]
    for path in candidates:
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            return os.path.abspath(path)
    return None
