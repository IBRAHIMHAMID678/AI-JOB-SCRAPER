"""
Personalized Job Matching Service.
Computes deterministic, explainable match scores between a user's profile/CV
and available jobs based on skills, experience level, preferred roles,
work arrangement, and location.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from ..core.database import db_session
from ..core.logging import get_logger
from ..core.models import CandidateProfile, Job, JobAnalysis, JobMatch

logger = get_logger(__name__)


def _normalize_tokens(items: List[str]) -> Set[str]:
    tokens = set()
    for item in items or []:
        cleaned = re.sub(r"[^\w\s]", "", item.lower()).strip()
        if cleaned:
            tokens.add(cleaned)
            for part in cleaned.split():
                if len(part) > 2:
                    tokens.add(part)
    return tokens


def calculate_match(profile: CandidateProfile, job: Job, analysis: Optional[JobAnalysis] = None) -> Dict[str, Any]:
    """
    Computes a weighted, fully explainable match score (0-100).
    """
    reasons: List[str] = []
    strong_matches: List[str] = []
    missing_requirements: List[str] = []

    # 1. Skills Matching (40% weight)
    candidate_skills = profile.skills or []
    candidate_tokens = _normalize_tokens(candidate_skills)

    job_text = f"{job.title} {job.description or ''} {job.requirements or ''}".lower()
    
    # Required skills from analysis or raw job
    required_skills = []
    if analysis and analysis.required_skills:
        required_skills = analysis.required_skills
    elif job.skills_raw:
        required_skills = job.skills_raw if isinstance(job.skills_raw, list) else []

    matched_skills = []
    for skill in candidate_skills:
        s_clean = skill.lower()
        if re.search(r"\b" + re.escape(s_clean) + r"\b", job_text):
            matched_skills.append(skill)
            strong_matches.append(skill)

    if required_skills:
        for req in required_skills:
            if req.lower() not in [m.lower() for m in matched_skills]:
                missing_requirements.append(req)

    if candidate_skills:
        skill_ratio = min(1.0, len(matched_skills) / max(3, len(candidate_skills) * 0.4))
        skills_score = int(skill_ratio * 100)
    else:
        skills_score = 50

    if matched_skills:
        reasons.append(f"Matches {len(matched_skills)} of your skills ({', '.join(matched_skills[:3])})")

    # 2. Role / Title Alignment (30% weight)
    preferred_roles = profile.preferred_roles or []
    preferred_tokens = _normalize_tokens(preferred_roles)
    title_lower = job.title.lower()

    role_score = 40
    for role in preferred_roles:
        if role.lower() in title_lower:
            role_score = 100
            reasons.append(f"Role title matches preferred role '{role}'")
            break
        elif any(tok in title_lower for tok in role.lower().split() if len(tok) > 3):
            role_score = max(role_score, 75)

    if role_score == 40 and any(t in title_lower for t in candidate_tokens if len(t) > 3):
        role_score = 65

    # 3. Experience & Seniority Level (15% weight)
    user_exp = profile.years_experience or 1.0
    exp_score = 70

    is_intern = any(w in title_lower for w in ["intern", "internship", "trainee"])
    is_junior = any(w in title_lower for w in ["junior", "entry", "associate", "jr"])
    is_senior = any(w in title_lower for w in ["senior", "lead", "principal", "staff", "architect", "head", "director"])

    if user_exp < 2.0:
        if is_intern or is_junior:
            exp_score = 100
            reasons.append("Experience level is a prime match for entry / junior candidates")
        elif is_senior:
            exp_score = 30
    elif user_exp >= 5.0:
        if is_senior:
            exp_score = 100
            reasons.append("Seniority requirements match your extensive experience")
        elif is_intern:
            exp_score = 40
    else:
        # Mid level (2-5 years)
        if not is_intern and not is_senior:
            exp_score = 95
            reasons.append("Fits mid-level engineering experience requirements")
        elif is_senior:
            exp_score = 65

    # 4. Location & Remote Arrangement (15% weight)
    loc_score = 70
    remote_pref = (profile.remote_preference or "worldwide_remote").lower()
    job_remote = (job.remote_type or "").lower()
    job_loc = (job.location or "").lower()
    cand_loc = (profile.location or "").lower()

    if "remote" in remote_pref:
        if job_remote == "remote" or "remote" in job_loc:
            loc_score = 100
            reasons.append("Remote work arrangement matches your preference")
        elif job_remote == "hybrid":
            loc_score = 60
        else:
            loc_score = 40
    elif cand_loc and (cand_loc in job_loc or any(city in job_loc for city in ["islamabad", "rawalpindi"] if city in cand_loc)):
        loc_score = 100
        reasons.append(f"Located in your preferred geographic area ({profile.location})")

    # Weighted Overall Score
    overall = int((skills_score * 0.40) + (role_score * 0.30) + (exp_score * 0.15) + (loc_score * 0.15))
    overall = max(10, min(99, overall))

    if overall >= 85:
        score_label = "HIGH_PRIORITY"
    elif overall >= 70:
        score_label = "GOOD_MATCH"
    elif overall >= 50:
        score_label = "POSSIBLE_MATCH"
    else:
        score_label = "LOW_MATCH"

    summary_text = " • ".join(reasons) if reasons else "General technical role alignment based on catalog criteria."

    return {
        "overall_score": overall,
        "score_label": score_label,
        "skills_score": skills_score,
        "role_score": role_score,
        "experience_score": exp_score,
        "location_score": loc_score,
        "strong_matches": strong_matches[:6],
        "missing_requirements": missing_requirements[:5],
        "reasons": reasons,
        "summary": summary_text,
    }


def compute_user_job_matches(user_id: str, limit: int = 400) -> int:
    """
    Calculates and persists personalized job match scores for a user.
    """
    with db_session() as db:
        profile = db.query(CandidateProfile).filter_by(id=user_id).first()
        if not profile:
            logger.info("[MATCHING] No profile found for user %s. Skipping match computation.", user_id)
            return 0

        jobs = db.query(Job).filter(Job.is_duplicate == False).order_by(Job.discovered_at.desc()).limit(limit).all()
        if not jobs:
            return 0

        analyses = {a.job_id: a for a in db.query(JobAnalysis).filter(JobAnalysis.job_id.in_([j.id for j in jobs])).all()}

        count = 0
        now = datetime.utcnow()

        for job in jobs:
            match_data = calculate_match(profile, job, analyses.get(job.id))
            
            existing_match = db.query(JobMatch).filter_by(job_id=job.id, user_id=user_id).first()
            if existing_match:
                existing_match.overall_score = match_data["overall_score"]
                existing_match.score_label = match_data["score_label"]
                existing_match.skills_score = match_data["skills_score"]
                existing_match.role_score = match_data["role_score"]
                existing_match.experience_score = match_data["experience_score"]
                existing_match.location_score = match_data["location_score"]
                existing_match.strong_matches = match_data["strong_matches"]
                existing_match.missing_requirements = match_data["missing_requirements"]
                existing_match.match_reason_summary = match_data["summary"]
                existing_match.matched_at = now
            else:
                new_match = JobMatch(
                    job_id=job.id,
                    user_id=user_id,
                    overall_score=match_data["overall_score"],
                    score_label=match_data["score_label"],
                    skills_score=match_data["skills_score"],
                    role_score=match_data["role_score"],
                    experience_score=match_data["experience_score"],
                    location_score=match_data["location_score"],
                    strong_matches=match_data["strong_matches"],
                    missing_requirements=match_data["missing_requirements"],
                    match_reason_summary=match_data["summary"],
                    matched_at=now,
                )
                db.add(new_match)
            count += 1

        db.commit()
        logger.info("[MATCHING] Successfully computed %d personalized job matches for user %s", count, user_id)
        return count

