"""
SQLAlchemy ORM models for JOBPILOT.
Compatible with SQLite (dev) and PostgreSQL (production).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ── Enums ─────────────────────────────────────────────────────────────────────

import enum as _enum


class RemoteType(_enum.Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unknown = "unknown"


class EmploymentType(_enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    freelance = "freelance"
    internship = "internship"
    unknown = "unknown"


class ApplicationStatus(_enum.Enum):
    DISCOVERED = "DISCOVERED"
    ANALYZING = "ANALYZING"
    MATCHED = "MATCHED"
    REJECTED = "REJECTED"
    SHORTLISTED = "SHORTLISTED"
    RESUME_GENERATED = "RESUME_GENERATED"
    COVER_LETTER_GENERATED = "COVER_LETTER_GENERATED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    APPLICATION_STARTED = "APPLICATION_STARTED"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    FOLLOW_UP = "FOLLOW_UP"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    OFFER_REJECTED = "OFFER_REJECTED"
    WITHDRAWN = "WITHDRAWN"


class NotificationChannel(_enum.Enum):
    dashboard = "dashboard"
    email = "email"
    whatsapp = "whatsapp"


class NotificationEvent(_enum.Enum):
    JOB_HIGH_SCORE = "JOB_HIGH_SCORE"
    APPLICATION_READY = "APPLICATION_READY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    RECRUITER_RESPONSE = "RECRUITER_RESPONSE"
    INTERVIEW_RECEIVED = "INTERVIEW_RECEIVED"
    FOLLOWUP_DUE = "FOLLOWUP_DUE"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"
    SCRAPER_FAILURE = "SCRAPER_FAILURE"
    DAILY_SUMMARY = "DAILY_SUMMARY"


class AgentStatus(_enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


# ── Job Models ────────────────────────────────────────────────────────────────

class JobSource(Base):
    __tablename__ = "job_sources"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(100), unique=True, nullable=False)
    adapter_class = Column(String(200), nullable=False)
    enabled = Column(Boolean, default=True)
    success_rate = Column(Float, default=1.0)
    last_run_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    jobs_found_total = Column(Integer, default=0)
    config_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now)

    jobs = relationship("Job", back_populates="source_ref")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_id = Column(String(36), ForeignKey("job_sources.id"), nullable=True)
    source_name = Column(String(100), nullable=False, default="unknown")
    source_job_id = Column(String(500), nullable=True)

    # Core fields
    title = Column(String(500), nullable=False)
    company = Column(String(300), nullable=False)
    location = Column(String(300), nullable=True)
    remote_type = Column(String(20), default="unknown")
    employment_type = Column(String(20), default="unknown")

    # Salary
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    salary_raw = Column(String(200), nullable=True)

    # Content
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)
    responsibilities = Column(Text, nullable=True)
    skills_raw = Column(JSON, default=list)

    # Dates
    posting_date = Column(DateTime, nullable=True)
    discovered_at = Column(DateTime, default=_now)

    # URLs
    application_url = Column(String(2000), nullable=False)
    company_url = Column(String(2000), nullable=True)

    # Deduplication
    url_hash = Column(String(64), unique=True, nullable=False)
    content_hash = Column(String(64), nullable=True)
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_id = Column(String(36), nullable=True)

    # Analysis
    analysis = relationship("JobAnalysis", back_populates="job", uselist=False)
    match = relationship("JobMatch", back_populates="job", uselist=False)
    application = relationship("Application", back_populates="job", uselist=False)
    source_ref = relationship("JobSource", back_populates="jobs")

    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("url_hash", name="uq_job_url_hash"),
    )


class JobAnalysis(Base):
    __tablename__ = "job_analyses"

    id = Column(String(36), primary_key=True, default=_uuid)
    job_id = Column(String(36), ForeignKey("jobs.id"), unique=True, nullable=False)

    required_skills = Column(JSON, default=list)
    preferred_skills = Column(JSON, default=list)
    technologies = Column(JSON, default=list)
    years_experience_min = Column(Integer, nullable=True)
    years_experience_max = Column(Integer, nullable=True)
    education_required = Column(String(200), nullable=True)
    certifications = Column(JSON, default=list)
    seniority = Column(String(50), nullable=True)
    industry = Column(String(200), nullable=True)

    # Location & auth
    location_requirements = Column(Text, nullable=True)
    remote_requirements = Column(Text, nullable=True)
    visa_required = Column(Boolean, default=False)
    us_only = Column(Boolean, default=False)
    pakistan_eligible = Column(Boolean, default=True)

    # Red flags
    red_flags = Column(JSON, default=list)
    suspicious_requirements = Column(JSON, default=list)

    # Extraction metadata
    model_used = Column(String(100), nullable=True)
    prompt_version = Column(String(20), nullable=True)
    confidence = Column(Float, nullable=True)
    analyzed_at = Column(DateTime, default=_now)

    job = relationship("Job", back_populates="analysis")


class JobMatch(Base):
    __tablename__ = "job_matches"

    id = Column(String(36), primary_key=True, default=_uuid)
    job_id = Column(String(36), ForeignKey("jobs.id"), unique=True, nullable=False)

    # Overall
    overall_score = Column(Integer, default=0)
    score_label = Column(String(30), nullable=True)

    # Breakdown
    skills_score = Column(Integer, default=0)
    experience_score = Column(Integer, default=0)
    role_score = Column(Integer, default=0)
    seniority_score = Column(Integer, default=0)
    location_score = Column(Integer, default=0)
    remote_score = Column(Integer, default=0)
    salary_score = Column(Integer, default=0)
    education_score = Column(Integer, default=0)
    technology_score = Column(Integer, default=0)

    # Details
    strong_matches = Column(JSON, default=list)
    missing_requirements = Column(JSON, default=list)
    transferable_skills = Column(JSON, default=list)
    risks = Column(JSON, default=list)
    reasons_to_apply = Column(JSON, default=list)
    reasons_to_reject = Column(JSON, default=list)
    match_reason_summary = Column(Text, nullable=True)

    # Decision
    auto_approved = Column(Boolean, default=False)
    requires_manual_review = Column(Boolean, default=True)
    decision = Column(String(30), nullable=True)  # approved | rejected | pending

    model_used = Column(String(100), nullable=True)
    matched_at = Column(DateTime, default=_now)

    job = relationship("Job", back_populates="match")


# ── Resume Models ─────────────────────────────────────────────────────────────

class Resume(Base):
    __tablename__ = "resumes"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False, default="Master Resume")
    is_master = Column(Boolean, default=False)
    content_markdown = Column(Text, nullable=True)
    content_json = Column(JSON, default=dict)
    file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    versions = relationship("ResumeVersion", back_populates="resume")


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id = Column(String(36), primary_key=True, default=_uuid)
    resume_id = Column(String(36), ForeignKey("resumes.id"), nullable=False)
    application_id = Column(String(36), ForeignKey("applications.id"), nullable=True)
    job_id = Column(String(36), nullable=True)

    version_number = Column(Integer, nullable=False, default=1)
    content_markdown = Column(Text, nullable=True)
    content_json = Column(JSON, default=dict)
    file_path = Column(String(500), nullable=True)

    keywords_added = Column(JSON, default=list)
    keywords_removed = Column(JSON, default=list)
    changes_summary = Column(Text, nullable=True)
    ats_score = Column(Integer, nullable=True)

    model_used = Column(String(100), nullable=True)
    generated_at = Column(DateTime, default=_now)

    resume = relationship("Resume", back_populates="versions")


# ── Application Models ────────────────────────────────────────────────────────

class Application(Base):
    __tablename__ = "applications"

    id = Column(String(36), primary_key=True, default=_uuid)
    job_id = Column(String(36), ForeignKey("jobs.id"), unique=True, nullable=False)

    status = Column(String(50), default=ApplicationStatus.DISCOVERED.value)
    mode = Column(String(20), default="manual")

    # Materials
    resume_version_id = Column(String(36), ForeignKey("resume_versions.id"), nullable=True)
    cover_letter_id = Column(String(36), ForeignKey("cover_letters.id"), nullable=True)

    # Submission
    submitted_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    confirmation_ref = Column(String(500), nullable=True)

    # Follow-up
    next_followup_at = Column(DateTime, nullable=True)
    followup_count = Column(Integer, default=0)

    # Notes
    user_notes = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    job = relationship("Job", back_populates="application")
    events = relationship("ApplicationEvent", back_populates="application", order_by="ApplicationEvent.created_at")
    questions = relationship("ApplicationQuestion", back_populates="application")
    resume_version = relationship("ResumeVersion", foreign_keys=[resume_version_id])
    cover_letter = relationship("CoverLetter", foreign_keys=[cover_letter_id])


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    application_id = Column(String(36), ForeignKey("applications.id"), nullable=False)

    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    actor = Column(String(50), default="system")   # system | user | agent
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    application = relationship("Application", back_populates="events")


class ApplicationQuestion(Base):
    __tablename__ = "application_questions"

    id = Column(String(36), primary_key=True, default=_uuid)
    application_id = Column(String(36), ForeignKey("applications.id"), nullable=False)

    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), nullable=True)
    generated_answer = Column(Text, nullable=True)
    final_answer = Column(Text, nullable=True)
    requires_human_review = Column(Boolean, default=False)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_now)

    application = relationship("Application", back_populates="questions")


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id = Column(String(36), primary_key=True, default=_uuid)
    job_id = Column(String(36), nullable=False)
    content = Column(Text, nullable=False)
    model_used = Column(String(100), nullable=True)
    generated_at = Column(DateTime, default=_now)


# ── Email Models ──────────────────────────────────────────────────────────────

class EmailMessage(Base):
    __tablename__ = "email_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    external_id = Column(String(500), unique=True, nullable=True)
    application_id = Column(String(36), ForeignKey("applications.id"), nullable=True)

    sender = Column(String(500), nullable=True)
    subject = Column(String(1000), nullable=True)
    body_preview = Column(Text, nullable=True)
    received_at = Column(DateTime, nullable=True)

    classification = Column(String(50), nullable=True)  # confirmation | rejection | interview | ...
    confidence = Column(Float, nullable=True)
    requires_review = Column(Boolean, default=False)

    processed_at = Column(DateTime, default=_now)


# ── Notification Models ───────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=_uuid)
    event_type = Column(String(50), nullable=False)
    channel = Column(String(30), nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=True)
    payload = Column(JSON, default=dict)
    sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)


# ── Agent Monitoring Models ───────────────────────────────────────────────────

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    agent_name = Column(String(100), nullable=False)
    status = Column(String(20), default=AgentStatus.PENDING.value)
    trigger = Column(String(50), default="manual")  # manual | scheduled | event
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    items_processed = Column(Integer, default=0)
    items_succeeded = Column(Integer, default=0)
    items_failed = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)

    tasks = relationship("AgentTask", back_populates="run")


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False)
    task_type = Column(String(100), nullable=False)
    status = Column(String(20), default=AgentStatus.PENDING.value)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)
    completed_at = Column(DateTime, nullable=True)

    run = relationship("AgentRun", back_populates="tasks")


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    actor = Column(String(100), default="system")
    action = Column(String(200), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(36), nullable=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(45), nullable=True)
    severity = Column(String(20), default="info")   # info | warning | critical
    created_at = Column(DateTime, default=_now)


# ── Candidate Profile ─────────────────────────────────────────────────────────

class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False)
    phone = Column(String(50), nullable=True)
    location = Column(String(200), nullable=True)
    timezone = Column(String(100), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    portfolio_url = Column(String(500), nullable=True)

    # Professional summary
    summary = Column(Text, nullable=True)
    years_experience = Column(Float, default=0)
    education = Column(JSON, default=list)       # [{degree, institution, year, gpa}]
    work_experience = Column(JSON, default=list) # [{title, company, start, end, bullets}]
    projects = Column(JSON, default=list)        # [{name, description, tech, url}]
    skills = Column(JSON, default=list)          # ["Python", "FastAPI", ...]
    technologies = Column(JSON, default=list)
    certifications = Column(JSON, default=list)
    achievements = Column(JSON, default=list)

    # Preferences
    preferred_roles = Column(JSON, default=list)
    preferred_locations = Column(JSON, default=list)
    remote_preference = Column(String(50), default="worldwide_remote")
    salary_min_usd_hourly = Column(Float, nullable=True)
    salary_max_usd_hourly = Column(Float, nullable=True)
    salary_min_usd_annual = Column(Float, nullable=True)
    work_authorization = Column(String(200), nullable=True)
    career_goals = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


# ── Uploaded CVs ──────────────────────────────────────────────────────────────

class UploadedCV(Base):
    __tablename__ = "uploaded_cvs"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)          # user-given label
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Parsed content
    raw_text = Column(Text, nullable=True)
    skills = Column(JSON, default=list)
    keywords = Column(JSON, default=list)
    roles = Column(JSON, default=list)                  # target roles extracted
    experience_years = Column(Float, nullable=True)
    education = Column(JSON, default=list)
    summary = Column(Text, nullable=True)

    # Targeting
    target_roles = Column(JSON, default=list)           # user-defined role tags
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    parsed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


# ── Daily Apply Tracker ───────────────────────────────────────────────────────

class DailyApplyLog(Base):
    __tablename__ = "daily_apply_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    date = Column(String(10), nullable=False)           # YYYY-MM-DD
    tier = Column(Integer, nullable=False)              # 1=90%+, 2=80-89%
    count = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("date", "tier", name="uq_daily_apply_date_tier"),
    )


# ── System Settings ───────────────────────────────────────────────────────────

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
