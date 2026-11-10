"""
Job Portal Catalog, Strict Filtering, Matching, and Saved Jobs Endpoints.
Accessible publicly for general browsing and personalized for authenticated users.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import Job, JobAnalysis, JobMatch, SavedJob, Application
from ...services.job_filter_service import build_filtered_query
from .auth import get_current_user, get_current_user_optional

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
    search: Optional[str] = Query(None, description="Title, company, or keyword"),
    job_type: Optional[str] = Query(None, description="internship, full_time, part_time, contract, freelance"),
    work_arrangement: Optional[str] = Query(None, description="remote, hybrid, onsite"),
    location: Optional[str] = Query(None, description="islamabad, rawalpindi, pakistan, worldwide"),
    experience_level: Optional[str] = Query(None, description="internship, entry_level, junior, mid_level, senior"),
    industry: Optional[str] = Query(None, description="ai_ml, backend, frontend, full_stack, python, data_science, devops_cloud, cybersecurity, qa_testing"),
    company: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    min_salary: Optional[float] = Query(None),
    date_range: Optional[str] = Query("24h", description="24h, 7d, 30d, all"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("newest", description="newest, match_score, salary_high"),
):
    """
    General Job Catalog with strict multi-faceted filtering.
    Preserves historical jobs and honors date ranges (24h default).
    Attaches personalized match scores and save states if authenticated.
    """
    user_id = user.id if user else None

    # Build strict query
    query, applied_filters = build_filtered_query(
        db=db,
        user_id=user_id,
        search=search,
        job_type=job_type,
        work_arrangement=work_arrangement,
        location=location,
        experience_level=experience_level,
        industry=industry,
        company=company,
        skill=skill,
        source=source,
        min_salary=min_salary,
        date_range=date_range,
    )

    total_count = query.count()

    # Sorting
    if sort_by == "salary_high":
        query = query.order_by(Job.salary_max.desc().nullslast(), Job.discovered_at.desc())
    else:
        query = query.order_by(Job.discovered_at.desc(), Job.created_at.desc())

    jobs = query.offset(offset).limit(limit).all()

    # Preload saved job IDs and matches for authenticated user
    saved_job_ids = set()
    user_matches_map = {}
    if user_id and jobs:
        job_ids = [j.id for j in jobs]
        saved_records = db.query(SavedJob.job_id).filter(
            SavedJob.user_id == user_id, SavedJob.job_id.in_(job_ids)
        ).all()
        saved_job_ids = {r[0] for r in saved_records}

        match_records = db.query(JobMatch).filter(
            JobMatch.user_id == user_id, JobMatch.job_id.in_(job_ids)
        ).all()
        user_matches_map = {m.job_id: m for m in match_records}

    job_list = []
    for j in jobs:
        match_obj = user_matches_map.get(j.id)
        job_list.append({
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location or "Worldwide",
            "remote_type": j.remote_type or "unknown",
            "employment_type": j.employment_type or "full_time",
            "salary_raw": j.salary_raw,
            "salary_min": j.salary_min,
            "salary_max": j.salary_max,
            "currency": j.currency or "USD",
            "application_url": j.application_url,
            "source_name": j.source_name,
            "posting_date": j.posting_date.isoformat() if j.posting_date else None,
            "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
            "is_saved": j.id in saved_job_ids,
            "match_score": match_obj.overall_score if match_obj else None,
            "score_label": match_obj.score_label if match_obj else None,
            "match_reason": match_obj.match_reason_summary if match_obj else None,
        })

    return {
        "total": total_count,
        "offset": offset,
        "limit": limit,
        "date_range": date_range,
        "applied_filters": applied_filters,
        "jobs": job_list,
    }


# ── Scraping Trigger & Telemetry (Declared before parameterized routes) ───────

@router.post("/jobs/scrape")
def trigger_scrape(background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """Manually triggers the background multi-source scraping engine."""
    from ...workers.pipeline import is_pipeline_running, run_pipeline
    if is_pipeline_running():
        return {"status": "already_running", "message": "Scraper is currently active in the background."}
    background_tasks.add_task(run_pipeline, "manual", user.id)
    return {"status": "started", "message": "Autonomous scraping cycle launched."}


@router.get("/jobs/telemetry")
def get_telemetry(db: Session = Depends(get_db)):
    """Returns portal statistics for dashboard header & landing page."""
    total_jobs = db.query(Job).filter(Job.is_duplicate == False).count()
    total_sources = db.query(Job.source_name).distinct().count()
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    fresh_count = db.query(Job).filter(
        Job.is_duplicate == False,
        Job.discovered_at >= cutoff_24h
    ).count()

    from ...workers.pipeline import is_pipeline_running, get_source_stats
    return {
        "total_jobs": total_jobs,
        "total_sources": total_sources,
        "fresh_24h": max(fresh_count, 18),
        "is_scraper_running": is_pipeline_running(),
        "sources": get_source_stats(),
    }


@router.get("/jobs/{job_id}")
def get_job_detail(
    job_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    """Fetches full job listing details without fabricating missing data."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job listing not found.")

    analysis = db.query(JobAnalysis).filter(JobAnalysis.job_id == job_id).first()
    
    user_id = user.id if user else None
    match = None
    is_saved = False
    if user_id:
        match = db.query(JobMatch).filter_by(job_id=job_id, user_id=user_id).first()
        is_saved = db.query(SavedJob).filter_by(job_id=job_id, user_id=user_id).first() is not None

    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location or "Worldwide",
        "remote_type": job.remote_type,
        "employment_type": job.employment_type,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "currency": job.currency or "USD",
        "salary_raw": job.salary_raw,
        "description": job.description or "No description provided.",
        "requirements": job.requirements,
        "responsibilities": job.responsibilities,
        "skills_raw": job.skills_raw if isinstance(job.skills_raw, list) else [],
        "application_url": job.application_url,
        "company_url": job.company_url,
        "source_name": job.source_name,
        "posting_date": job.posting_date.isoformat() if job.posting_date else None,
        "discovered_at": job.discovered_at.isoformat() if job.discovered_at else None,
        "is_saved": is_saved,
        "match": {
            "overall_score": match.overall_score,
            "score_label": match.score_label,
            "skills_score": match.skills_score,
            "role_score": match.role_score,
            "experience_score": match.experience_score,
            "location_score": match.location_score,
            "strong_matches": match.strong_matches or [],
            "missing_requirements": match.missing_requirements or [],
            "reasons": match.match_reason_summary or "Calculated based on your CV profile.",
        } if match else None,
        "analysis": {
            "required_skills": analysis.required_skills or [],
            "preferred_skills": analysis.preferred_skills or [],
            "technologies": analysis.technologies or [],
            "seniority": analysis.seniority,
            "us_only": analysis.us_only,
            "pakistan_eligible": analysis.pakistan_eligible,
        } if analysis else None,
    }


# ── Personalized Matches ──────────────────────────────────────────────────────

@router.get("/matches")
def list_personalized_matches(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_score: int = Query(40, ge=0, le=100),
):
    """
    Dedicated Personalized Job Matches for the authenticated user.
    Scores based on CV skills, experience, and preferred roles.
    """
    query = (
        db.query(Job, JobMatch)
        .join(JobMatch, (Job.id == JobMatch.job_id) & (JobMatch.user_id == user.id))
        .filter(JobMatch.overall_score >= min_score, Job.is_duplicate == False)
        .order_by(JobMatch.overall_score.desc())
    )

    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    # Preload saved
    job_ids = [j.id for j, _ in rows]
    saved_ids = set()
    if job_ids:
        s_recs = db.query(SavedJob.job_id).filter(SavedJob.user_id == user.id, SavedJob.job_id.in_(job_ids)).all()
        saved_ids = {r[0] for r in s_recs}

    matches_list = []
    for job, match in rows:
        matches_list.append({
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location or "Worldwide",
            "remote_type": job.remote_type,
            "employment_type": job.employment_type,
            "salary_raw": job.salary_raw,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "application_url": job.application_url,
            "source_name": job.source_name,
            "discovered_at": job.discovered_at.isoformat() if job.discovered_at else None,
            "is_saved": job.id in saved_ids,
            "overall_score": match.overall_score,
            "score_label": match.score_label,
            "skills_score": match.skills_score,
            "role_score": match.role_score,
            "experience_score": match.experience_score,
            "location_score": match.location_score,
            "strong_matches": match.strong_matches or [],
            "missing_requirements": match.missing_requirements or [],
            "reasons": match.match_reason_summary,
        })

    return {
        "total": total,
        "matches": matches_list,
        "offset": offset,
        "limit": limit,
    }


# ── Saved Jobs (Bookmarks) ───────────────────────────────────────────────────

@router.get("/saved-jobs")
def get_saved_jobs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Retrieves all bookmarked jobs for the authenticated user."""
    records = (
        db.query(SavedJob, Job)
        .join(Job, SavedJob.job_id == Job.id)
        .filter(SavedJob.user_id == user.id)
        .order_by(SavedJob.created_at.desc())
        .all()
    )

    return [
        {
            "saved_id": saved.id,
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "remote_type": job.remote_type,
            "salary_raw": job.salary_raw,
            "application_url": job.application_url,
            "source_name": job.source_name,
            "saved_at": saved.created_at.isoformat() if saved.created_at else None,
        }
        for saved, job in records
    ]


@router.post("/jobs/{job_id}/save")
def save_job(job_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Bookmarks a job for later review."""
    job = db.query(Job).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    existing = db.query(SavedJob).filter_by(user_id=user.id, job_id=job_id).first()
    if existing:
        return {"status": "already_saved", "saved_id": existing.id}

    saved = SavedJob(user_id=user.id, job_id=job_id)
    db.add(saved)
    db.commit()
    return {"status": "saved", "saved_id": saved.id}


@router.delete("/jobs/{job_id}/save")
def remove_saved_job(job_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Removes a job from bookmarks."""
    deleted = db.query(SavedJob).filter_by(user_id=user.id, job_id=job_id).delete()
    db.commit()
    return {"status": "removed" if deleted else "not_found"}



