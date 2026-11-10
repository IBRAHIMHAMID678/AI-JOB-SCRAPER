"""
Strict and Comprehensive Job Filtering Engine.
Applies exact normalization, multi-category constraints, and strict keyword exclusion
so that selecting 'internship' never returns 'senior' roles, and date ranges
preserve historical data accurately.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import or_, and_, desc, asc
from sqlalchemy.orm import Session

from ..core.models import Job, JobAnalysis, JobMatch, SavedJob


INDUSTRY_PATTERNS = {
    "ai_ml": [
        "ai", "artificial intelligence", "machine learning", "ml", "llm",
        "rag", "nlp", "deep learning", "generative ai", "langchain", "prompt"
    ],
    "backend": [
        "backend", "back-end", "fastapi", "django", "flask", "node.js",
        "nodejs", "express", "nestjs", "golang", "spring", "microservices", "rest api"
    ],
    "frontend": [
        "frontend", "front-end", "react", "next.js", "nextjs", "vue",
        "angular", "ui/ux", "tailwind", "css", "html5", "javascript"
    ],
    "full_stack": [
        "full stack", "fullstack", "full-stack", "mern", "mean stack"
    ],
    "python": [
        "python", "python developer", "python engineer"
    ],
    "data_science": [
        "data science", "data scientist", "data engineer", "data analyst",
        "big data", "etl", "analytics", "spark", "databricks"
    ],
    "devops_cloud": [
        "devops", "cloud", "aws", "gcp", "azure", "kubernetes", "docker",
        "ci/cd", "terraform", "sre", "infrastructure"
    ],
    "cybersecurity": [
        "security", "cyber", "infosec", "soc", "penetration", "vulnerability"
    ],
    "qa_testing": [
        "qa", "quality assurance", "test engineer", "automation test", "sdet", "testing"
    ],
}


def build_filtered_query(
    db: Session,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    job_type: Optional[str] = None,
    work_arrangement: Optional[str] = None,
    location: Optional[str] = None,
    experience_level: Optional[str] = None,
    industry: Optional[str] = None,
    company: Optional[str] = None,
    skill: Optional[str] = None,
    source: Optional[str] = None,
    min_salary: Optional[float] = None,
    date_range: Optional[str] = "24h",
) -> Tuple[Any, List[str]]:
    """
    Constructs a strict SQLAlchemy query respecting all selected filters.
    Returns (query, applied_filters_summary).
    """
    query = db.query(Job).filter(Job.is_duplicate == False)
    applied_summaries: List[str] = []

    # 1. Search Query
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                Job.title.ilike(term),
                Job.company.ilike(term),
                Job.description.ilike(term),
                Job.location.ilike(term)
            )
        )
        applied_summaries.append(f"Keyword: '{search}'")

    # 2. Company
    if company and company.strip():
        query = query.filter(Job.company.ilike(f"%{company.strip()}%"))
        applied_summaries.append(f"Company: {company}")

    # 3. Source
    if source and source.strip() and source.lower() != "all":
        query = query.filter(Job.source_name.ilike(f"%{source.strip()}%"))
        applied_summaries.append(f"Source: {source}")

    # 4. Work Arrangement (Remote / Hybrid / On-site)
    if work_arrangement and work_arrangement.lower() != "all":
        wa = work_arrangement.lower().strip()
        if wa == "remote":
            query = query.filter(
                or_(
                    Job.remote_type == "remote",
                    Job.location.ilike("%remote%"),
                    Job.location.ilike("%worldwide%"),
                    Job.location.ilike("%anywhere%")
                )
            )
            applied_summaries.append("Arrangement: Remote")
        elif wa == "hybrid":
            query = query.filter(
                or_(
                    Job.remote_type == "hybrid",
                    Job.location.ilike("%hybrid%")
                )
            )
            applied_summaries.append("Arrangement: Hybrid")
        elif wa == "onsite":
            query = query.filter(
                and_(
                    Job.remote_type != "remote",
                    not_(Job.location.ilike("%remote%")),
                    not_(Job.location.ilike("%anywhere%"))
                )
            )
            applied_summaries.append("Arrangement: On-site")

    # 5. Location
    if location and location.lower() != "all":
        loc = location.lower().strip()
        if loc in ("islamabad", "isb"):
            query = query.filter(
                or_(Job.location.ilike("%islamabad%"), Job.location.ilike("%isb%"))
            )
            applied_summaries.append("Location: Islamabad")
        elif loc in ("rawalpindi", "rwp"):
            query = query.filter(
                or_(Job.location.ilike("%rawalpindi%"), Job.location.ilike("%rwp%"))
            )
            applied_summaries.append("Location: Rawalpindi")
        elif loc == "pakistan":
            query = query.filter(
                or_(
                    Job.location.ilike("%pakistan%"),
                    Job.location.ilike("%pk%"),
                    Job.location.ilike("%islamabad%"),
                    Job.location.ilike("%lahore%"),
                    Job.location.ilike("%karachi%"),
                    Job.location.ilike("%rawalpindi%")
                )
            )
            applied_summaries.append("Location: Pakistan")
        elif loc in ("worldwide", "international"):
            query = query.filter(
                or_(
                    Job.location.ilike("%worldwide%"),
                    Job.location.ilike("%anywhere%"),
                    Job.location.ilike("%global%"),
                    Job.remote_type == "remote"
                )
            )
            applied_summaries.append("Location: Worldwide")
        else:
            query = query.filter(Job.location.ilike(f"%{loc}%"))
            applied_summaries.append(f"Location: {location}")

    # 6. Strict Job Type & Experience Level
    senior_exclusions = ["%senior%", "%lead%", "%principal%", "%staff%", "%director%", "%head of%", "%manager%"]
    
    if job_type and job_type.lower() != "all":
        jt = job_type.lower().strip()
        if jt in ("internship", "intern"):
            # STRICT: Must match intern/internship AND NOT senior/lead
            query = query.filter(
                or_(
                    Job.employment_type == "internship",
                    Job.title.ilike("%intern%"),
                    Job.title.ilike("%trainee%")
                )
            )
            for ex in senior_exclusions:
                query = query.filter(not_(Job.title.ilike(ex)))
            applied_summaries.append("Job Type: Internship (Strict)")
        elif jt in ("contract", "freelance"):
            query = query.filter(
                or_(
                    Job.employment_type.in_(["contract", "freelance"]),
                    Job.title.ilike("%contract%"),
                    Job.title.ilike("%freelance%")
                )
            )
            applied_summaries.append("Job Type: Contract / Freelance")
        elif jt == "full_time":
            query = query.filter(
                or_(
                    Job.employment_type == "full_time",
                    not_(Job.title.ilike("%intern%"))
                )
            )
            applied_summaries.append("Job Type: Full-time")
        elif jt == "part_time":
            query = query.filter(
                or_(
                    Job.employment_type == "part_time",
                    Job.title.ilike("%part time%"),
                    Job.title.ilike("%part-time%")
                )
            )
            applied_summaries.append("Job Type: Part-time")

    if experience_level and experience_level.lower() != "all":
        exp = experience_level.lower().strip()
        if exp in ("internship", "intern"):
            query = query.filter(
                or_(Job.title.ilike("%intern%"), Job.title.ilike("%trainee%"))
            )
            for ex in senior_exclusions:
                query = query.filter(not_(Job.title.ilike(ex)))
            applied_summaries.append("Experience: Internship")
        elif exp in ("entry_level", "junior", "0_1", "1_2"):
            # Strictly junior & entry level - NOT senior
            query = query.filter(
                or_(
                    Job.title.ilike("%junior%"),
                    Job.title.ilike("%entry%"),
                    Job.title.ilike("%associate%"),
                    Job.title.ilike("%graduate%"),
                    Job.title.ilike("%jr%")
                )
            )
            for ex in senior_exclusions:
                query = query.filter(not_(Job.title.ilike(ex)))
            applied_summaries.append("Experience: Junior / Entry Level (Strict)")
        elif exp in ("mid_level", "2_3"):
            # Mid-level: exclude both intern and senior lead
            query = query.filter(not_(Job.title.ilike("%intern%")))
            for ex in ["%principal%", "%staff%", "%director%", "%head of%"]:
                query = query.filter(not_(Job.title.ilike(ex)))
            applied_summaries.append("Experience: Mid-level")
        elif exp == "senior":
            query = query.filter(
                or_(
                    Job.title.ilike("%senior%"),
                    Job.title.ilike("%sr.%"),
                    Job.title.ilike("%lead%"),
                    Job.title.ilike("%principal%"),
                    Job.title.ilike("%staff%"),
                    Job.title.ilike("%architect%")
                )
            )
            applied_summaries.append("Experience: Senior / Lead")

    # 7. Industry / Technical Field
    if industry and industry.lower() != "all":
        ind_key = industry.lower().strip()
        patterns = INDUSTRY_PATTERNS.get(ind_key)
        if patterns:
            conds = [Job.title.ilike(f"%{p}%") for p in patterns]
            # Also match description for rich coverage
            conds.extend([Job.description.ilike(f"%{p}%") for p in patterns[:4]])
            query = query.filter(or_(*conds))
            applied_summaries.append(f"Industry: {industry.replace('_', ' ').title()}")

    # 8. Required Skill
    if skill and skill.strip():
        s_term = f"%{skill.strip()}%"
        query = query.filter(
            or_(
                Job.title.ilike(s_term),
                Job.description.ilike(s_term)
            )
        )
        applied_summaries.append(f"Skill: {skill}")

    # 9. Minimum Salary
    if min_salary and min_salary > 0:
        query = query.filter(
            or_(
                Job.salary_min >= min_salary,
                Job.salary_max >= min_salary
            )
        )
        applied_summaries.append(f"Min Salary: ${int(min_salary)}")

    # 10. Date Range (Preserves historical data while honoring 24h default)
    now = datetime.utcnow()
    if date_range == "24h":
        cutoff = now - timedelta(hours=24)
        # Check if there are jobs within 24h
        recent_count = db.query(Job).filter(Job.discovered_at >= cutoff, Job.is_duplicate == False).count()
        if recent_count >= 5:
            query = query.filter(or_(Job.discovered_at >= cutoff, Job.posting_date >= cutoff))
            applied_summaries.append("Period: Last 24 Hours")
        else:
            # In local dev with static database, don't return an empty page — show latest batch
            applied_summaries.append("Period: Latest Discovered Batch (24h fallback)")
    elif date_range == "7d":
        cutoff = now - timedelta(days=7)
        query = query.filter(or_(Job.discovered_at >= cutoff, Job.posting_date >= cutoff))
        applied_summaries.append("Period: Last 7 Days")
    elif date_range == "30d":
        cutoff = now - timedelta(days=30)
        query = query.filter(or_(Job.discovered_at >= cutoff, Job.posting_date >= cutoff))
        applied_summaries.append("Period: Last 30 Days")
    elif date_range == "all":
        # All historical jobs remain accessible
        applied_summaries.append("Period: All Historical Listings")

    return query, applied_summaries


from sqlalchemy import not_

