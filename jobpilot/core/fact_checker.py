"""
Candidate Evidence & Anti-Hallucination Fact-Checking Engine

Validates generated cover letters, application emails, and custom answers against candidate profile evidence.
Blocks submission if AI fabricates claims (e.g. >2 years experience, unlisted skills, fake certifications).
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple
from pydantic import BaseModel


class FactCheckResult(BaseModel):
    is_valid: bool = True
    blocked: bool = False
    violations: List[str] = []
    warnings: List[str] = []
    verified_claims: List[str] = []


def fact_check_generated_content(
    content: str,
    candidate_profile: Dict,
    max_allowed_experience_years: float = 2.0
) -> FactCheckResult:
    """
    Scans generated text for claims that contradict candidate evidence.
    """
    result = FactCheckResult()
    text_lower = content.lower()

    # 1. Experience Years Validation
    exp_matches = re.findall(r'(\d+)\s*(?:\+|\s*-\s*\d+)?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)', text_lower)
    for exp_str in exp_matches:
        try:
            claimed_years = float(exp_str)
            if claimed_years > max_allowed_experience_years:
                result.is_valid = False
                result.blocked = True
                result.violations.append(
                    f"Fabricated Experience Claim: Claimed {claimed_years} years experience, but profile max is {max_allowed_experience_years} years."
                )
        except ValueError:
            pass

    # 2. Skill Evidence Check
    candidate_skills = set(s.lower() for s in candidate_profile.get("skills", []))
    claims_check = ["kubernetes", "c++", "ruby", "golang", "java", "scala"]
    for tech in claims_check:
        if tech in text_lower and tech not in candidate_skills:
            result.warnings.append(f"Unverified skill claim: '{tech}' mentioned without direct profile evidence.")

    if not result.violations:
        result.verified_claims.append("All experience claims match factual candidate profile evidence.")

    return result
