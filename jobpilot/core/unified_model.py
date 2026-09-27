"""
Unified Job Opportunity Model — Canonical Representation (Section 3 of Master Spec)

Every job source, social lead, or ATS scanner MUST normalize its output into
this canonical structure before evaluation, verification, matching, and application.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Identity(BaseModel):
    internal_id: str
    source: str
    source_job_id: Optional[str] = None
    source_url: str
    canonical_url: str
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyInfo(BaseModel):
    company_name: str
    company_website: Optional[str] = None
    company_domain: Optional[str] = None
    company_verified: bool = False
    ats_identifier: Optional[str] = None
    industry: Optional[str] = None
    remote_policy: Optional[str] = None


class RoleInfo(BaseModel):
    title: str
    normalized_title: str
    description: str
    employment_type: str = "full_time"  # full_time, part_time, contract, internship
    seniority: str = "junior"           # junior, mid, senior, lead, staff
    experience_required_min: float = 0.0
    experience_required_max: float = 3.0  # item 36: approved range is 1-3 years
    skills: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)


class LocationInfo(BaseModel):
    raw_location: str
    normalized_location: str
    remote: bool = True
    remote_scope: str = "worldwide"  # worldwide, regional, country_specific, local_pk
    allowed_countries: List[str] = Field(default_factory=list)
    excluded_countries: List[str] = Field(default_factory=list)
    work_authorization: Optional[str] = None
    pakistan_eligible: bool = True
    is_local_pk: bool = False  # Islamabad / Rawalpindi local role
    eligibility_confidence: float = 1.0  # 0.0 to 1.0
    eligibility_reason: str = ""


class CompensationInfo(BaseModel):
    salary_raw: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "USD"
    salary_period: str = "hourly"  # hourly, monthly, annual
    hourly_equivalent: Optional[float] = None
    compensation_type: str = "disclosed"  # disclosed, estimated, undisclosed
    is_derived: bool = False


class ApplicationInfo(BaseModel):
    application_url: str
    application_type: str = "UNKNOWN"  # EMAIL, GREENHOUSE, LEVER, WORKDAY, GOOGLE_FORM, COMPANY_FORM, OTHER_ATS, MANUAL
    email: Optional[str] = None
    form_url: Optional[str] = None
    ats_platform: Optional[str] = None
    requires_account: bool = False
    application_status: str = "DISCOVERED"  # DISCOVERED, VERIFIED, READY, STARTED, PAGE_IN_PROGRESS, WAITING_FOR_INPUT, READY_TO_SUBMIT, SUBMITTED, FAILED, PAUSED, COMPLETED


class QualityInfo(BaseModel):
    verification_score: int = 0  # 0-100
    scam_score: int = 0          # 0-100 (0 = safe, 100 = definite scam)
    source_quality: int = 100    # 0-100
    freshness_days: int = 0
    duplicate_group: Optional[str] = None
    job_quality: str = "VERIFIED_JOB"  # VERIFIED_JOB, UNVERIFIED_LEAD, REJECTED_LEAD


class MatchingInfo(BaseModel):
    cv_match_score: int = 0  # 0-100
    skill_match: float = 0.0
    experience_match: float = 0.0
    project_match: float = 0.0
    title_match: float = 0.0
    overall_match: int = 0
    match_reasons: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)


class EvidenceInfo(BaseModel):
    eligibility_evidence: str = ""
    salary_evidence: str = ""
    experience_evidence: str = ""
    company_evidence: str = ""
    application_evidence: str = ""


class UnifiedJobOpportunity(BaseModel):
    identity: Identity
    company: CompanyInfo
    role: RoleInfo
    location: LocationInfo
    compensation: CompensationInfo
    application: ApplicationInfo
    quality: QualityInfo
    matching: MatchingInfo
    evidence: EvidenceInfo
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)
