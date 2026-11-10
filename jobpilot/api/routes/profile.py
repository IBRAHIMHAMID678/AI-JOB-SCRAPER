"""User profile and system settings management — Strictly isolated per authenticated user."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import CandidateProfile, SystemSetting, UploadedCV
from .auth import get_current_user

router = APIRouter(tags=["profile"])


# ── Profile Schemas ───────────────────────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    remote_preference: Optional[str] = None
    work_authorization: Optional[str] = None
    skills: Optional[List[str]] = None
    preferred_roles: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    salary_min_usd_hourly: Optional[float] = None
    salary_max_usd_hourly: Optional[float] = None
    years_experience: Optional[float] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    summary: Optional[str] = None


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Fetches the authenticated user's isolated profile."""
    profile = db.query(CandidateProfile).filter_by(id=user.id).first()
    if not profile:
        profile = CandidateProfile(
            id=user.id,
            name=user.username.capitalize(),
            email=user.email,
            location="Worldwide Remote",
            skills=["Python", "FastAPI", "React"],
            preferred_roles=["Software Engineer"],
            years_experience=1.0,
            remote_preference="worldwide_remote",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    # Also check default CV
    default_cv = db.query(UploadedCV).filter_by(user_id=user.id, is_default=True).first()

    return {
        "id": profile.id,
        "name": profile.name,
        "email": profile.email,
        "phone": profile.phone or "",
        "location": profile.location or "",
        "timezone": profile.timezone or "UTC",
        "remote_preference": profile.remote_preference or "worldwide_remote",
        "work_authorization": profile.work_authorization or "Authorized Worldwide",
        "skills": profile.skills or [],
        "preferred_roles": profile.preferred_roles or [],
        "preferred_locations": profile.preferred_locations or [],
        "salary_min_usd_hourly": profile.salary_min_usd_hourly or 25.0,
        "salary_max_usd_hourly": profile.salary_max_usd_hourly or 60.0,
        "years_experience": profile.years_experience or 0.0,
        "linkedin_url": profile.linkedin_url or "",
        "github_url": profile.github_url or "",
        "portfolio_url": profile.portfolio_url or "",
        "summary": profile.summary or "",
        "has_cv": default_cv is not None,
        "cv_filename": default_cv.filename if default_cv else None,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@router.put("/profile")
def update_profile(req: ProfileUpdateRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Updates the authenticated user's isolated profile."""
    profile = db.query(CandidateProfile).filter_by(id=user.id).first()
    if not profile:
        profile = CandidateProfile(id=user.id, name=user.username, email=user.email)
        db.add(profile)

    update_dict = req.model_dump(exclude_none=True)
    for field, value in update_dict.items():
        if hasattr(profile, field):
            setattr(profile, field, value)

    db.commit()
    db.refresh(profile)

    # Trigger re-matching for this user with their updated profile in background
    import threading
    def _rematch():
        try:
            from ...services.matching_service import compute_user_job_matches
            compute_user_job_matches(user.id)
        except Exception:
            pass
    threading.Thread(target=_rematch, daemon=True).start()

    return {"status": "updated", "profile": {"name": profile.name, "skills": profile.skills}}


# ── System Settings ────────────────────────────────────────────────────────────

class SettingUpdateRequest(BaseModel):
    value: Any


@router.get("/settings")
def get_settings_store(db: Session = Depends(get_db)):
    """Return persisted system settings."""
    rows = db.query(SystemSetting).all()
    return {r.key: {"value": r.value, "description": r.description} for r in rows}


@router.put("/settings/{key}")
def upsert_setting(key: str, req: SettingUpdateRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Persist a setting override."""
    ALLOWED_KEYS = {
        "SCORE_AUTO_APPROVE", "SCORE_MIN_THRESHOLD", "SCORE_HIGH_PRIORITY",
        "SCORE_GOOD_MATCH", "SCORE_POSSIBLE_MATCH",
        "APPLICATION_MODE", "MAX_APPLICATIONS_PER_DAY", "REQUIRE_APPROVAL",
        "NOTIFY_HIGH_SCORE_JOBS", "NOTIFY_APPLICATION_READY",
        "NOTIFY_RECRUITER_RESPONSE", "NOTIFY_INTERVIEW", "NOTIFY_DAILY_SUMMARY",
        "SCRAPE_INTERVAL_HOURS", "QUEUE_MAX_WORKERS",
    }
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Key '{key}' is not configurable.")

    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        setting = SystemSetting(key=key, value=req.value)
        db.add(setting)
    else:
        setting.value = req.value

    db.commit()
    return {"status": "saved", "key": key, "value": req.value}
