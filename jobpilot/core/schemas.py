"""
Pydantic schemas — request/response contracts for the API and agent I/O.
These are separate from SQLAlchemy models to maintain clear boundaries.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator
from .unified_model import UnifiedJobOpportunity


# ── Raw Job (from scrapers) ───────────────────────────────────────────────────

class RawJob(BaseModel):
    """Untrusted, un-normalized input from a scraper. Treat as EXTERNAL data."""
    title: str = ""
    company: str = ""
    location: Optional[str] = None
    description: Optional[str] = None
    application_url: str
    source: str
    source_job_id: Optional[str] = None
    salary_raw: Optional[str] = None
    posting_date: Optional[str] = None
    employment_type: Optional[str] = None
    remote_type: Optional[str] = None
    skills_raw: List[str] = Field(default_factory=list)
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "company", mode="before")
    @classmethod
    def strip_str(cls, v):
        return str(v).strip() if v else ""

    @field_validator("application_url", mode="before")
    @classmethod
    def validate_url(cls, v):
        v = str(v).strip()
        if not v or v in ("nan", "None", ""):
            raise ValueError("application_url is required")
        return v


# ── Normalized Job ────────────────────────────────────────────────────────────

class NormalizedJob(BaseModel):
    id: Optional[str] = None
    source_name: str
    source_job_id: Optional[str] = None
    title: str
    company: str
    location: Optional[str] = None
    remote_type: str = "unknown"
    employment_type: str = "unknown"
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: Optional[str] = None
    salary_raw: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    skills_raw: List[str] = Field(default_factory=list)
    posting_date: Optional[datetime] = None
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    application_url: str
    url_hash: Optional[str] = None
    content_hash: Optional[str] = None
    canonical_job_id: Optional[str] = None


# ── Job Analysis ──────────────────────────────────────────────────────────────

class JobAnalysisResult(BaseModel):
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    years_experience_min: Optional[int] = None
    years_experience_max: Optional[int] = None
    education_required: Optional[str] = None
    certifications: List[str] = Field(default_factory=list)
    seniority: Optional[str] = None
    industry: Optional[str] = None
    location_requirements: Optional[str] = None
    remote_requirements: Optional[str] = None
    visa_required: bool = False
    us_only: bool = False
    pakistan_eligible: bool = True
    is_local_pk: bool = False
    eligibility_evidence: str = ""
    red_flags: List[str] = Field(default_factory=list)
    suspicious_requirements: List[str] = Field(default_factory=list)
    model_used: Optional[str] = None
    prompt_version: str = "1.0"
    confidence: Optional[float] = None


# ── Job Match ─────────────────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    skills_score: int = 0
    experience_score: int = 0
    role_score: int = 0
    seniority_score: int = 0
    location_score: int = 0
    remote_score: int = 0
    salary_score: int = 0
    education_score: int = 0
    technology_score: int = 0


class JobMatchResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    score_label: str = "LOW_PRIORITY"
    breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    strong_matches: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    transferable_skills: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    reasons_to_apply: List[str] = Field(default_factory=list)
    reasons_to_reject: List[str] = Field(default_factory=list)
    match_reason_summary: Optional[str] = None
    auto_approved: bool = False
    requires_manual_review: bool = True
    decision: str = "pending"
    model_used: Optional[str] = None


# ── Application ───────────────────────────────────────────────────────────────

class ApplicationOut(BaseModel):
    id: str
    job_id: str
    status: str
    mode: str
    submitted_at: Optional[datetime] = None
    next_followup_at: Optional[datetime] = None
    followup_count: int = 0
    user_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationStatusUpdate(BaseModel):
    status: str
    note: Optional[str] = None
    actor: str = "user"


class ApproveApplicationRequest(BaseModel):
    notes: Optional[str] = None


# ── Resume ────────────────────────────────────────────────────────────────────

class ResumeVersionOut(BaseModel):
    id: str
    version_number: int
    keywords_added: List[str] = Field(default_factory=list)
    keywords_removed: List[str] = Field(default_factory=list)
    changes_summary: Optional[str] = None
    ats_score: Optional[int] = None
    generated_at: datetime
    content_markdown: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Notification ──────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: str
    event_type: str
    channel: str
    title: str
    body: Optional[str] = None
    sent: bool
    sent_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Job API Response ──────────────────────────────────────────────────────────

class JobOut(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = None
    remote_type: str
    employment_type: str
    salary_raw: Optional[str] = None
    application_url: str
    source_name: str
    posting_date: Optional[datetime] = None
    discovered_at: datetime
    overall_score: Optional[int] = None
    score_label: Optional[str] = None
    decision: Optional[str] = None
    application_status: Optional[str] = None

    model_config = {"from_attributes": True}


class JobDetailOut(JobOut):
    description: Optional[str] = None
    requirements: Optional[str] = None
    skills_raw: List[str] = Field(default_factory=list)
    analysis: Optional[JobAnalysisResult] = None
    match: Optional[JobMatchResult] = None


# ── Analytics ────────────────────────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    jobs_discovered: int = 0
    jobs_matched: int = 0
    applications_total: int = 0
    applications_submitted: int = 0
    interviews: int = 0
    offers: int = 0
    response_rate: float = 0.0
    interview_rate: float = 0.0


# ── Agent Run ─────────────────────────────────────────────────────────────────

class AgentRunOut(BaseModel):
    id: str
    agent_name: str
    status: str
    trigger: str
    items_processed: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── System ────────────────────────────────────────────────────────────────────

class SystemStatus(BaseModel):
    app_name: str
    version: str
    database: str
    redis: str
    llm_provider: str
    sources_active: int
    jobs_total: int
    applications_total: int
    uptime_seconds: float
