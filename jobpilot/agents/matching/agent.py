"""
Job Matching Agent.
Scores every job against the candidate profile.
Uses a deterministic weighted scorer first (cheap, fast, explainable).
LLM adds nuance for borderline jobs above a threshold.

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


# ── Candidate profile (source of truth) ──────────────────────────────────────
# This is derived from settings — it NEVER hallucinated.

_PROFILE = {
    "name": settings.CANDIDATE_NAME,
    "location": settings.CANDIDATE_LOCATION,
    "work_auth": settings.CANDIDATE_WORK_AUTHORIZATION,
    "remote_pref": settings.CANDIDATE_REMOTE_PREFERENCE,
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
    "education": "computer science degree",
    "years_experience": 0,  # fresh graduate
    "career_level": "junior",
}

_ROLE_KEYWORDS = {
    "ai engineer": 25, "ai developer": 25, "llm engineer": 25, "ml engineer": 22,
    "full stack": 20, "fullstack": 20, "python developer": 20,
    "backend developer": 18, "backend engineer": 18,
    "software engineer": 15, "software developer": 15,
    "react developer": 15, "frontend developer": 12,
    "web developer": 12, "developer": 10,
}


def _role_score(title: str) -> tuple[int, List[str]]:
    title_lower = title.lower()
    matches = []
    best = 0
    for role, pts in _ROLE_KEYWORDS.items():
        if role in title_lower:
            best = max(best, pts)
            matches.append(role)
    return min(best, 25), matches


def _skills_score(job_skills: List[str], job_desc: str) -> tuple[int, List[str]]:
    text = " ".join(job_skills).lower() + " " + (job_desc or "").lower()
    found = []
    for skill in _PROFILE["skills"]:
        if re.search(r"\b" + re.escape(skill) + r"\b", text):
            found.append(skill)
    coverage = len(found) / len(_PROFILE["skills"])
    return min(int(coverage * 25), 25), found


def _tech_score(job_analysis: Optional[JobAnalysisResult]) -> tuple[int, List[str]]:
    if not job_analysis:
        return 5, []
    all_tech = [t.lower() for t in (job_analysis.technologies + job_analysis.required_skills)]
    matches = [t for t in _PROFILE["technologies"] if any(t in jt for jt in all_tech)]
    coverage = len(matches) / max(len(_PROFILE["technologies"]), 1)
    return min(int(coverage * 15), 15), matches


def _experience_score(seniority: Optional[str], years_min: Optional[int]) -> tuple[int, bool]:
    is_junior = False
    if seniority in ("junior", "entry"):
        is_junior = True
        return 15, True
    if seniority == "mid" or seniority is None:
        if years_min is None or years_min <= 2:
            is_junior = True
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
        if any(k in loc for k in ["worldwide", "anywhere", "pakistan", "global"]):
            reasons.append("Worldwide remote")
            return 10, reasons
        reasons.append("Remote role")
        return 8, reasons
    if job.remote_type == "hybrid":
        reasons.append("Hybrid (partial remote)")
        return 5, reasons
    if "pakistan" in (job.location or "").lower() or "islamabad" in (job.location or "").lower():
        reasons.append("Pakistan location")
        return 8, reasons
    return 2, reasons


def _salary_score(job: NormalizedJob) -> tuple[int, List[str]]:
    if job.salary_min and job.salary_max:
        if job.currency == "USD":
            # Hourly check
            if 15 <= job.salary_min <= 60 or 15 <= job.salary_max <= 60:
                return 5, [f"USD salary in range: {job.salary_min}-{job.salary_max}"]
            # Annual check
            if 30000 <= job.salary_min <= 200000:
                return 4, [f"USD annual salary: {job.salary_min}-{job.salary_max}"]
    if not job.salary_min:
        return 2, ["Salary not disclosed"]
    return 1, []


def _education_score(education: Optional[str]) -> int:
    if not education:
        return 5  # no requirement = fine for us
    edu_lower = education.lower()
    if "phd" in edu_lower or "doctorate" in edu_lower:
        return 0
    if "master" in edu_lower:
        return 2
    return 5  # bachelor or less


class MatchingAgent(BaseAgent):
    name = "matching_agent"

    def _execute(self, input_data: dict) -> JobMatchResult:
        """
        input_data = {"job": NormalizedJob, "analysis": Optional[JobAnalysisResult]}
        """
        job: NormalizedJob = input_data["job"]
        analysis: Optional[JobAnalysisResult] = input_data.get("analysis")

        title = job.title or ""
        desc = job.description or ""

        # Score each dimension
        role_pts, role_matches = _role_score(title)
        skills_pts, skill_matches = _skills_score(job.skills_raw, desc)
        tech_pts, tech_matches = _tech_score(analysis)
        exp_pts, is_junior = _experience_score(
            analysis.seniority if analysis else None,
            analysis.years_experience_min if analysis else None,
        )
        loc_pts, loc_reasons = _location_score(job, analysis)
        sal_pts, sal_reasons = _salary_score(job)
        edu_pts = _education_score(analysis.education_required if analysis else None)

        total = role_pts + skills_pts + tech_pts + exp_pts + loc_pts + sal_pts + edu_pts
        total = min(total, 100)

        # Build human-readable reasons
        strong_matches = role_matches + skill_matches[:5] + tech_matches[:3] + loc_reasons
        missing = []
        if analysis:
            for skill in analysis.required_skills:
                if not any(skill.lower() in s.lower() for s in _PROFILE["skills"]):
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

        # Decision
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
            match_reason_summary=" | ".join(summary_parts) if summary_parts else "Rule-based matching",
            auto_approved=auto_approved,
            requires_manual_review=requires_review,
            decision=decision,
            model_used="rule-based",
        )
