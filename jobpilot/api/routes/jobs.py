"""Job discovery and management endpoints."""
from __future__ import annotations

import threading
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import Job, JobAnalysis, JobMatch, Application
from ...core.schemas import JobOut, JobDetailOut

router = APIRouter(tags=["jobs"])


@router.post("/jobs/discover")
def trigger_discovery(background_tasks: BackgroundTasks):
    """Start the job discovery pipeline in the background."""
    from ...workers.pipeline import is_pipeline_running, run_pipeline
    if is_pipeline_running():
        return {"status": "already_running", "message": "Pipeline is already running"}
    background_tasks.add_task(run_pipeline, "manual")
    return {"status": "started", "message": "Job discovery pipeline started"}


@router.get("/jobs", response_model=List[dict])
def list_jobs(
    db: Session = Depends(get_db),
    score_min: int = Query(0, ge=0, le=100),
    status: Optional[str] = None,
    decision: Optional[str] = None,
    remote_only: bool = False,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """List all discovered jobs with optional filters."""
    query = db.query(Job, JobMatch).outerjoin(JobMatch, Job.id == JobMatch.job_id)

    if remote_only:
        query = query.filter(Job.remote_type == "remote")

    if score_min > 0:
        query = query.filter(JobMatch.overall_score >= score_min)

    if decision:
        query = query.filter(JobMatch.decision == decision)

    rows = query.order_by(JobMatch.overall_score.desc()).offset(offset).limit(limit).all()

    results = []
    for job, match in rows:
        d = {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "remote_type": job.remote_type,
            "salary_raw": job.salary_raw,
            "application_url": job.application_url,
            "source_name": job.source_name,
            "discovered_at": job.discovered_at.isoformat() if job.discovered_at else None,
            "overall_score": match.overall_score if match else None,
            "score_label": match.score_label if match else None,
            "decision": match.decision if match else None,
            "match_reason": match.match_reason_summary if match else None,
        }
        results.append(d)
    return results


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get full job details including analysis and match breakdown."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    analysis = db.query(JobAnalysis).filter(JobAnalysis.job_id == job_id).first()
    match = db.query(JobMatch).filter(JobMatch.job_id == job_id).first()
    application = db.query(Application).filter(Application.job_id == job_id).first()

    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote_type": job.remote_type,
        "employment_type": job.employment_type,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "currency": job.currency,
        "salary_raw": job.salary_raw,
        "description": job.description,
        "requirements": job.requirements,
        "skills_raw": job.skills_raw,
        "application_url": job.application_url,
        "source_name": job.source_name,
        "posting_date": job.posting_date.isoformat() if job.posting_date else None,
        "discovered_at": job.discovered_at.isoformat() if job.discovered_at else None,
        "analysis": {
            "required_skills": analysis.required_skills if analysis else [],
            "preferred_skills": analysis.preferred_skills if analysis else [],
            "technologies": analysis.technologies if analysis else [],
            "seniority": analysis.seniority if analysis else None,
            "us_only": analysis.us_only if analysis else False,
            "pakistan_eligible": analysis.pakistan_eligible if analysis else True,
            "red_flags": analysis.red_flags if analysis else [],
        } if analysis else None,
        "match": {
            "overall_score": match.overall_score if match else 0,
            "score_label": match.score_label if match else None,
            "breakdown": {
                "role": match.role_score,
                "skills": match.skills_score,
                "technology": match.technology_score,
                "experience": match.experience_score,
                "location": match.location_score,
                "salary": match.salary_score,
                "education": match.education_score,
            } if match else {},
            "strong_matches": match.strong_matches if match else [],
            "missing_requirements": match.missing_requirements if match else [],
            "risks": match.risks if match else [],
            "reasons_to_apply": match.reasons_to_apply if match else [],
            "reasons_to_reject": match.reasons_to_reject if match else [],
            "auto_approved": match.auto_approved if match else False,
            "decision": match.decision if match else "pending",
            "match_reason_summary": match.match_reason_summary if match else None,
        } if match else None,
        "application_status": application.status if application else None,
    }


@router.post("/jobs/{job_id}/shortlist")
def shortlist_job(job_id: str, db: Session = Depends(get_db)):
    """Manually shortlist a job."""
    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    from ...core.state_machine import transition, StateMachineError
    try:
        event = transition(app, "SHORTLISTED", actor="user", note="Manually shortlisted")
        db.add(event)
        db.commit()
        return {"status": "shortlisted"}
    except StateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/jobs/{job_id}/reject")
def reject_job(job_id: str, db: Session = Depends(get_db)):
    """Manually reject a job."""
    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    from ...core.state_machine import transition, StateMachineError
    try:
        event = transition(app, "REJECTED", actor="user")
        db.add(event)
        db.commit()
        return {"status": "rejected"}
    except StateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/jobs/clear")
def clear_all_jobs(db: Session = Depends(get_db)):
    """Clear all jobs from the database (development use)."""
    db.query(JobAnalysis).delete()
    db.query(JobMatch).delete()
    db.query(Application).delete()
    db.query(Job).delete()
    db.commit()
    return {"status": "cleared"}
