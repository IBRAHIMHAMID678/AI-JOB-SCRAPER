"""
Experience and Seniority Gatekeeper for JOBPILOT.
Evaluates job postings against Ibrahim Hamid's verified candidate profile:
- Maximum 3 years required experience (reject 4+, 5+, 5-7, 4 years minimum, etc.).
- Rejects senior leadership roles (Manager, Director, VP, Lead, Head of, Principal, Staff, PhD).
- Truthful geographic eligibility (candidate is in Pakistan, seeks worldwide remote / contractor).
- Zero false positives on team/company context (e.g. 'reporting to Engineering Manager').
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

from .candidate import get_canonical_candidate_profile
from .logging import get_logger

logger = get_logger("core.eligibility")


class EligibilityDecision(BaseModel):
    is_eligible: bool
    decision: str  # "ELIGIBLE", "EXPERIENCE_EXCEEDED", "SENIORITY_REJECTED", "LOCATION_INELIGIBLE", "WORK_AUTH_INELIGIBLE", "UNKNOWN"
    reason: str
    matched_rule: Optional[str] = None
    evidence_text: Optional[str] = None
    evaluated_at: str = ""


# Seniority titles that exceed candidate's junior profile
# Must be matched as whole words or precise role titles to avoid substring accidents
SENIORITY_TITLE_PATTERNS = [
    r"\b(senior|sr\.?|lead|principal|staff)\b",
    r"\b(engineering\s+manager|manager|general\s+manager|product\s+manager)\b",
    r"\b(director|assoc(?:iate)?\s+director|senior\s+director)\b",
    r"\b(vp|vice\s+president)\b",
    r"\b(head\s+of\b)",
    r"\b(principal\s+software|principal\s+engineer|principal\s+developer|principal)\b",
    r"\b(staff\s+software|staff\s+engineer|staff\s+developer|staff)\b",
    r"\b(tech(?:nical)?\s+lead|team\s+lead|lead\s+developer|lead\s+software|lead\s+engineer|lead)\b",
    r"\b(phd\s+intern|phd\s+researcher|phd\s+scientist|phd)\b",
    r"\b(architect|enterprise\s+architect|solution\s+architect)\b",
]

# Patterns explicitly stating required years of experience beyond 3 years
# (4+, 5+, 4-6, minimum 4, at least 4, 4+ yrs, 5-7 years, 5 years required, 8 or more years)
EXPERIENCE_EXCEEDED_PATTERNS = [
    r"(\b[4-9]|\b[1-9]\d)\s*\+?\s*(?:to|-)\s*\d+\s*(?:years?|yrs?)",
    r"(\b[4-9]|\b[1-9]\d)\s*\+\s*(?:years?|yrs?)",
    r"(\b[4-9]|\b[1-9]\d)\s+(?:or\s+more|plus)\s+(?:years?|yrs?)",
    r"(?:minimum|at\s+least|no\s+less\s+than)\s*(\b[4-9]|\b[1-9]\d)\s*(?:years?|yrs?)",
    r"(\b[4-9]|\b[1-9]\d)\s*(?:years?|yrs?)\s*(?:of)?\s*(?:relevant\s+|professional\s+)?(?:experience|exp)?\s*(?:minimum|required|mandatory)",
    r"(?:require|requires|seeking)\s*(\b[4-9]|\b[1-9]\d)\s*\+?\s*(?:years?|yrs?)",
]

# Exclusions: do not trigger on junior or 0-3 years text
EXPERIENCE_ALLOWLIST_PATTERNS = [
    r"\b(0-2|0-3|1-3|2-3|1-2|up\s+to\s+3)\s*(?:years?|yrs?)",
    r"\b[0-3]\s*\+?\s*(?:years?|yrs?)",
]


def check_seniority(title: str, description: str = "") -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Checks whether the role is senior/management.
    Focuses primarily on the title to avoid false positives from contextual text like 'reports to Manager'.
    """
    title_clean = title.strip().lower()

    for pattern in SENIORITY_TITLE_PATTERNS:
        match = re.search(pattern, title_clean, re.IGNORECASE)
        if match:
            # Check edge cases like 'Manager tools' or 'Lead generation'
            matched_str = match.group(0)
            if matched_str == "lead" and "generation" in title_clean:
                continue
            return False, f"SENIORITY_REJECTED: {matched_str}", matched_str

    return True, None, None


def check_experience_requirement(description: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Scans job description requirements for explicit >3 years experience criteria.
    """
    if not description:
        return True, None, None

    desc_lower = description.lower()

    # Look for sections titled requirements/qualifications/what you bring first if available
    req_sections = re.findall(
        r"(?:requirements|qualifications|what\s+you(?:'ll)?\s+bring|what\s+we(?:'re)?\s+looking\s+for|minimum\s+qualifications)([\s\S]{1,1500})",
        desc_lower,
    )
    search_targets = req_sections if req_sections else [desc_lower]

    for target in search_targets:
        for pattern in EXPERIENCE_EXCEEDED_PATTERNS:
            match = re.search(pattern, target, re.IGNORECASE)
            if match:
                evidence = match.group(0)
                # Verify it's not preceded by 'preferred' or 'bonus' if strict requirement exists
                start_idx = max(0, match.start() - 30)
                preceding = target[start_idx:match.start()]
                if "preferred" in preceding or "nice to have" in preceding or "plus" in preceding:
                    continue
                return False, f"EXPERIENCE_EXCEEDED: {evidence}", evidence

    return True, None, None


def check_geographic_eligibility(
    job_location: Optional[str] = None,
    description: str = "",
    allowed_countries: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Evaluates whether the candidate truthfully qualifies for the job location / work auth.
    Ibrahim Hamid is based in Pakistan and eligible for worldwide remote / contractor roles.
    """
    candidate = get_canonical_candidate_profile()
    combined = f"{job_location or ''} {description[:800]}".lower()

    # If the job explicitly states 'Must reside in US/UK/Canada/Japan/etc.' or is on-site in restricted locations:
    restricted_keywords = [
        "must be located in the us",
        "must reside in the united states",
        "us citizenship required",
        "must be located in the uk",
        "must reside in japan",
        "only accepting applications from candidates residing in",
        "must hold active security clearance",
        "remote - united states",
        "remote – united states",
        "remote - us",
        "remote – us",
        "remote (us)",
        "remote - usa",
        "remote – usa",
        "remote (usa)",
        "remote - latam",
        "remote – latam",
        "remote | colombia",
        "remote (india)",
        "remote - india",
        "remote – india",
        "remote - uk",
        "remote – uk",
        "remote - canada",
        "remote – canada",
        "remote - europe",
        "remote – europe",
        "remote - emea",
        "remote – emea",
        "bengaluru",
        "bangalore",
        "mumbai",
        "delhi",
        "hyderabad",
        "pune",
        "chennai",
        "noida",
        "gurgaon",
        "india",
        "us only",
        "usa only",
        "uk only",
    ]
    for rk in restricted_keywords:
        if rk in combined:
            return False, "LOCATION_INELIGIBLE", rk

    # If onsite or hybrid role outside Pakistan (Islamabad / Rawalpindi / Pakistan)
    loc_clean = (job_location or "").lower()
    is_pk_location = any(pk in loc_clean for pk in ["pakistan", "islamabad", "rawalpindi"])
    is_worldwide_remote = any(rem in loc_clean for rem in ["worldwide", "anywhere", "global", "work from anywhere"])

    # If location is not in Pakistan and not explicitly worldwide remote:
    if not is_pk_location and not is_worldwide_remote:
        # If explicitly marked onsite/hybrid
        if any(w in loc_clean for w in ["hybrid", "onsite", "on-site"]):
            return False, "LOCATION_INELIGIBLE", f"Non-Pakistan onsite/hybrid: {loc_clean}"

        # If it specifies a specific non-remote city/state/country
        if "remote" not in loc_clean and loc_clean.strip() != "":
            # Any physical non-remote location outside Pakistan is ineligible
            return False, "LOCATION_INELIGIBLE", f"Physical non-Pakistan location: {loc_clean}"

    return True, None, None


def check_tech_role_relevance(title: str, description: str = "") -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Ensures the job is compatible with Ibrahim Hamid's profile:
    Software/AI/Web/Backend/Full-Stack/Python developer and related engineering roles.
    Rejects sales, deal teams, account executive, marketing, finance, HR, legal, etc.
    """
    title_lower = title.lower()
    tech_keywords = [
        "software", "developer", "engineer", "programmer", "ai", "machine learning",
        "python", "react", "full stack", "fullstack", "backend", "frontend",
        "web", "fastapi", "django", "nextjs", "node", "typescript", "data", "devops",
        "intern", "technical"
    ]
    if not any(k in title_lower for k in tech_keywords):
        return False, "NON_TECH_ROLE", title

    # Explicit exclusions for non-engineering titles or non-software engineering fields
    non_dev_exclusions = [
        r"\b(deal\s+team|business\s+affairs|transformation\s+owner)\b",
        r"\b(account\s+executive|sales|marketing|recruiter|finance|counsel|legal|tax|accounting|support\s+specialist|bilingual\s+customer)\b",
        r"\b(civil\s+engineer|mechanical\s+engineer|electrical\s+engineer|chemical\s+engineer|hardware\s+engineer)\b",
        r"\b(product\s+designer|graphic\s+designer|ui\/ux\s+designer|designer|talent\s+acquisition|supply\s+chain|business\s+development)\b",
        r"\b(revenue\s+analyst|financial\s+analyst|workplace\s+operations|security\s+clearance)\b",
    ]
    for ex in non_dev_exclusions:
        if re.search(ex, title_lower):
            return False, "NON_DEV_ROLE", title

    return True, None, None


def evaluate_job_eligibility(
    job_id: str,
    title: str,
    company: str,
    description: str = "",
    location: Optional[str] = None,
) -> EligibilityDecision:
    """
    Comprehensive pre-flight eligibility check.
    Returns structured decision with evidence.
    """
    now = datetime.utcnow().isoformat()

    # 1. Technical Role Relevance Check
    tech_ok, tech_reason, tech_evidence = check_tech_role_relevance(title, description)
    if not tech_ok:
        logger.info("[ELIGIBILITY] REJECTED job=%s company=%s reason=%s evidence='%s'", job_id, company, tech_reason, tech_evidence)
        return EligibilityDecision(
            is_eligible=False,
            decision="NON_TECH_ROLE",
            reason=tech_reason or "Non-technical or non-engineering role",
            matched_rule="Candidate Profile Relevance Gatekeeper",
            evidence_text=tech_evidence,
            evaluated_at=now,
        )

    # 2. Seniority Check
    sen_ok, sen_reason, sen_evidence = check_seniority(title, description)
    if not sen_ok:
        logger.info("[ELIGIBILITY] REJECTED job=%s company=%s reason=%s evidence='%s'", job_id, company, sen_reason, sen_evidence)
        return EligibilityDecision(
            is_eligible=False,
            decision="SENIORITY_REJECTED",
            reason=sen_reason or "Exceeds seniority criteria",
            matched_rule="Seniority Gatekeeper",
            evidence_text=sen_evidence,
            evaluated_at=now,
        )

    # 3. Experience Check
    exp_ok, exp_reason, exp_evidence = check_experience_requirement(description)
    if not exp_ok:
        logger.info("[ELIGIBILITY] REJECTED job=%s company=%s reason=%s evidence='%s'", job_id, company, exp_reason, exp_evidence)
        return EligibilityDecision(
            is_eligible=False,
            decision="EXPERIENCE_EXCEEDED",
            reason=exp_reason or "Requires >3 years of experience",
            matched_rule="Experience Gatekeeper",
            evidence_text=exp_evidence,
            evaluated_at=now,
        )

    # 4. Geographic / Location Check
    geo_ok, geo_reason, geo_evidence = check_geographic_eligibility(location, description)
    if not geo_ok:
        logger.info("[ELIGIBILITY] REJECTED job=%s company=%s reason=%s evidence='%s'", job_id, company, geo_reason, geo_evidence)
        return EligibilityDecision(
            is_eligible=False,
            decision="LOCATION_INELIGIBLE",
            reason=geo_reason or "Geographic restriction mismatch",
            matched_rule="Geographic Eligibility Gatekeeper",
            evidence_text=geo_evidence,
            evaluated_at=now,
        )

    return EligibilityDecision(
        is_eligible=True,
        decision="ELIGIBLE",
        reason="Candidate qualifies for role profile (<=3 yrs, junior/mid, remote/contractor eligible)",
        matched_rule="All criteria passed",
        evidence_text=None,
        evaluated_at=now,
    )
