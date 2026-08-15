"""Candidate profile and system settings management."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import CandidateProfile, SystemSetting

router = APIRouter(tags=["profile"])


# ── Profile ───────────────────────────────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    remote_preference: Optional[str] = None
    work_authorization: Optional[str] = None
    skills: Optional[List[str]] = None
    preferred_roles: Optional[List[str]] = None
    salary_min_usd_hourly: Optional[float] = None
    salary_max_usd_hourly: Optional[float] = None
    years_experience: Optional[int] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    summary: Optional[str] = None


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    profile = db.query(CandidateProfile).first()
    if not profile:
        raise HTTPException(status_code=404, detail="No candidate profile found. Run the app to seed defaults.")
    return {
        "id": profile.id,
        "name": profile.name,
        "email": profile.email,
        "location": profile.location,
        "timezone": profile.timezone,
        "remote_preference": profile.remote_preference,
        "work_authorization": profile.work_authorization,
        "skills": profile.skills or [],
        "preferred_roles": profile.preferred_roles or [],
        "salary_min_usd_hourly": profile.salary_min_usd_hourly,
        "salary_max_usd_hourly": profile.salary_max_usd_hourly,
        "years_experience": profile.years_experience,
        "linkedin_url": profile.linkedin_url,
        "github_url": profile.github_url,
        "portfolio_url": profile.portfolio_url,
        "summary": profile.summary,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.put("/profile")
def update_profile(req: ProfileUpdateRequest, db: Session = Depends(get_db)):
    profile = db.query(CandidateProfile).first()
    if not profile:
        raise HTTPException(status_code=404, detail="No candidate profile found")

    for field, value in req.model_dump(exclude_none=True).items():
        if hasattr(profile, field):
            setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return {"status": "updated", "name": profile.name}


# ── System Settings ────────────────────────────────────────────────────────────

class SettingUpdateRequest(BaseModel):
    value: Any


@router.get("/settings")
def get_settings_store(db: Session = Depends(get_db)):
    """Return all persisted system settings (overrides .env defaults)."""
    rows = db.query(SystemSetting).all()
    return {r.key: {"value": r.value, "description": r.description} for r in rows}


@router.put("/settings/{key}")
def upsert_setting(key: str, req: SettingUpdateRequest, db: Session = Depends(get_db)):
    """Persist a setting override to the database."""
    ALLOWED_KEYS = {
        "SCORE_AUTO_APPROVE", "SCORE_MIN_THRESHOLD", "SCORE_HIGH_PRIORITY",
        "SCORE_GOOD_MATCH", "SCORE_POSSIBLE_MATCH",
        "APPLICATION_MODE", "MAX_APPLICATIONS_PER_DAY", "REQUIRE_APPROVAL",
        "NOTIFY_HIGH_SCORE_JOBS", "NOTIFY_APPLICATION_READY",
        "NOTIFY_RECRUITER_RESPONSE", "NOTIFY_INTERVIEW", "NOTIFY_DAILY_SUMMARY",
        "SCRAPE_INTERVAL_HOURS", "QUEUE_MAX_WORKERS",
    }
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Setting '{key}' is not user-configurable")

    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = str(req.value)
    else:
        db.add(SystemSetting(key=key, value=str(req.value)))
    db.commit()
    return {"key": key, "value": req.value}
