"""
Job Matching Agent.
Scores every job against the candidate profile.
Uses a deterministic weighted scorer (cheap, fast, explainable).

Score breakdown (max 100):
  Role/Title match:    25 pts
  Skills match:        25 pts
  Technology match:    15 pts
  Experience level:    15 pts
  Remote/Location:     10 pts
  Salary range:         5 pts
  Education:            5 pts
"""
from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel

from ...core.config import settings
from ...core.schemas import JobAnalysisResult, JobMatchResult, NormalizedJob, ScoreBreakdown
from ...core.security import sanitize_for_prompt
from ..base import BaseAgent


# ── Default fallback profile (used only when no CV is uploaded) ───────────────

_DEFAULT_PROFILE = {
    "skills": [
        "python", "fastapi", "react", "next.js", "node.js", "nestjs",
        "langchain", "rag", "mongodb", "llm", "typescript", "javascript",
        "docker", "git", "rest api", "vector database",
    ],
    "technologies": [
        "python", "fastapi", "react", "nextjs", "nodejs", "nestjs", "langchain",
        "mongodb", "postgresql", "redis", "docker", "aws", "openai api",
    ],
    "preferred_roles": [
        "ai engineer", "ai developer", "llm engineer", "full stack developer",
        "python developer", "backend developer", "software engineer",
    ],
    "seniority_preference": ["junior", "entry", "mid"],
    "min_hourly_usd": 15,
    "max_hourly_usd": 60,
    "years_experience": 0,
    "career_level": "junior",
}


def _build_role_map(preferred_roles: List[str]) -> dict:
    """Build a role→points map from the user's preferred roles."""
    role_map: dict[str, int] = {
        "ai engineer": 25,
        "ai developer": 25,
        "llm engineer": 25,
        "full stack developer": 20,
        "python developer": 20,
        "backend developer": 18,
        "software engineer": 15,
    }
    for i, role in enumerate(preferred_roles):
        role_lower = role.lower().strip()
        if role_lower and role_lower not in role_map:
            role_map[role_lower] = max(25 - i * 2, 10)
    role_map.setdefault("developer", 10)
    role_map.setdefault("engineer", 12)
    role_map.setdefault("programmer", 10)
    return role_map


def _role_score(title: str, profile: dict = None) -> tuple[int, List[str]]:
    profile = profile or _DEFAULT_PROFILE
    title_lower = title.lower()
    role_map = _build_role_map(profile.get("preferred_roles", []))
    matches = []
    best = 0
    for role, pts in role_map.items():
        if role in title_lower:
            best = max(best, pts)
            matches.append(role)
    return min(best, 25), matches


def _skills_score(job_skills: List[str], job_desc: str, profile: dict = None) -> tuple[int, List[str]]:
    profile = profile or _DEFAULT_PROFILE
    text = " ".join(job_skills).lower() + " " + (job_desc or "").lower()
    user_skills = profile.get("skills", [])
    if not user_skills:
        return 5, []
    found = []
    for skill in user_skills:
        if re.search(r"\b" + re.escape(skill.lower()) + r"\b", text):
            found.append(skill)
    coverage = len(found) / len(user_skills)
    return min(int(coverage * 25), 25), found


def _tech_score(job_analysis: Optional[JobAnalysisResult], profile: dict) -> tuple[int, List[str]]:
    if not job_analysis:
        return 5, []
    user_tech = [t.lower() for t in profile.get("technologies", [])]
    if not user_tech:
        return 5, []
    all_tech = [t.lower() for t in (job_analysis.technologies + job_analysis.required_skills)]
    matches = [t for t in user_tech if any(t in jt for jt in all_tech)]
    coverage = len(matches) / max(len(user_tech), 1)
    return min(int(coverage * 15), 15), matches


def _experience_score(seniority: Optional[str], years_min: Optional[int]) -> tuple[int, bool]:
    if seniority in ("junior", "entry"):
        return 15, True
    if seniority == "mid" or seniority is None:
        if years_min is None or years_min <= 2:
            return 12, True
        return 5, False
    # senior
    return 0, False


def _location_score(job: NormalizedJob, analysis: Optional[JobAnalysisResult]) -> tuple[int, List[str]]:
    reasons = []
    if analysis and not analysis.pakistan_eligible:
        return 0, ["Pakistan not eligible"]
    if job.remote_type == "remote":
        loc = (job.location or "").lower()
        if any(k in loc for k in ["worldwide", "anywhere", "pakistan", "global", ""]):
            reasons.append("Worldwide remote")
            return 10, reasons
        reasons.append("Remote role")
        return 8, reasons
    if job.remote_type == "hybrid":
        reasons.append("Hybrid (partial remote)")
        return 5, reasons
    if "pakistan" in (job.location or "").lower():
        reasons.append("Pakistan location")
        return 8, reasons
    return 2, reasons


def _salary_score(job: NormalizedJob) -> tuple[int, List[str]]:
    if job.salary_min and job.salary_max:
        if job.currency == "USD":
            if 15 <= job.salary_min <= 60 or 15 <= job.salary_max <= 60:
                return 5, [f"USD salary in range: {job.salary_min}-{job.salary_max}"]
            if 30000 <= job.salary_min <= 200000:
                return 4, [f"USD annual salary: {job.salary_min}-{job.salary_max}"]
    if not job.salary_min:
        return 2, ["Salary not disclosed"]
    return 1, []


def _education_score(education: Optional[str]) -> int:
    if not education:
        return 5
    edu_lower = education.lower()
    if "phd" in edu_lower or "doctorate" in edu_lower:
        return 0
    if "master" in edu_lower:
        return 2
    return 5


class MatchingAgent(BaseAgent):
    name = "matching_agent"

    def _execute(self, input_data: dict) -> JobMatchResult:
        """
        input_data keys:
          - job: NormalizedJob
          - analysis: Optional[JobAnalysisResult]
          - user_profile: Optional[dict]  ← from user's uploaded CV
        """
        job: NormalizedJob = input_data["job"]
        analysis: Optional[JobAnalysisResult] = input_data.get("analysis")

        # Use CV-based profile if provided; fall back to defaults
        user_profile = input_data.get("user_profile") or _DEFAULT_PROFILE

        title = job.title or ""
        desc = job.description or ""

        role_pts, role_matches = _role_score(title, user_profile)
        skills_pts, skill_matches = _skills_score(job.skills_raw, desc, user_profile)
        tech_pts, tech_matches = _tech_score(analysis, user_profile)
        exp_pts, is_junior = _experience_score(
            analysis.seniority if analysis else None,
            analysis.years_experience_min if analysis else None,
        )
        loc_pts, loc_reasons = _location_score(job, analysis)
        sal_pts, sal_reasons = _salary_score(job)
        edu_pts = _education_score(analysis.education_required if analysis else None)

        total = min(role_pts + skills_pts + tech_pts + exp_pts + loc_pts + sal_pts + edu_pts, 100)

        strong_matches = role_matches + skill_matches[:5] + tech_matches[:3] + loc_reasons
        missing = []
        if analysis:
            user_skills_lower = [s.lower() for s in user_profile.get("skills", [])]
            for skill in analysis.required_skills:
                if not any(skill.lower() in s for s in user_skills_lower):
                    missing.append(f"Missing required skill: {skill}")
        risks = []
        if analysis and analysis.red_flags:
            risks = analysis.red_flags
        if analysis and not analysis.pakistan_eligible:
            risks.append("Location restriction: Pakistan may not be eligible")

        reasons_to_apply = [r for r in strong_matches if r]
        reasons_to_reject = list(missing[:3]) + [r for r in risks if r]

        summary_parts = []
        if role_matches:
            summary_parts.append(f"Role match: {', '.join(role_matches[:2])}")
        if skill_matches:
            summary_parts.append(f"Skills: {', '.join(skill_matches[:4])}")
        if loc_reasons:
            summary_parts.append(loc_reasons[0])

        pak_eligible = (analysis.pakistan_eligible if analysis else True)
        auto_approved = total >= settings.SCORE_AUTO_APPROVE and pak_eligible
        requires_review = not auto_approved or total < settings.SCORE_GOOD_MATCH
        decision = "approved" if auto_approved else "pending"

        return JobMatchResult(
            overall_score=total,
            score_label=settings.get_score_label(total),
            breakdown=ScoreBreakdown(
                skills_score=skills_pts,
                experience_score=exp_pts,
                role_score=role_pts,
                seniority_score=exp_pts,
                location_score=loc_pts,
                remote_score=loc_pts,
                salary_score=sal_pts,
                education_score=edu_pts,
                technology_score=tech_pts,
            ),
            strong_matches=list(set(strong_matches))[:10],
            missing_requirements=missing[:5],
            transferable_skills=[s for s in skill_matches if s not in (analysis.required_skills if analysis else [])],
            risks=risks[:5],
            reasons_to_apply=reasons_to_apply[:5],
            reasons_to_reject=reasons_to_reject[:5],
            match_reason_summary=" | ".join(summary_parts) if summary_parts else "CV-based matching",
            auto_approved=auto_approved,
            requires_manual_review=requires_review,
            decision=decision,
            model_used="rule-based",
        )
