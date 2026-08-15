"""Application tracking and management endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import Application, ApplicationEvent, Job, JobMatch, CoverLetter, ResumeVersion
from sqlalchemy import desc
from ...core.state_machine import StateMachineError, transition

router = APIRouter(tags=["applications"])


class ApproveRequest(BaseModel):
    notes: Optional[str] = None


class StatusUpdateRequest(BaseModel):
    status: str
    note: Optional[str] = None


@router.get("/applications")
def list_applications(db: Session = Depends(get_db), status: Optional[str] = None):
    query = db.query(Application, Job, JobMatch).join(Job, Application.job_id == Job.id).outerjoin(JobMatch, Job.id == JobMatch.job_id)
    if status:
        query = query.filter(Application.status == status.upper())
    rows = query.order_by(Application.updated_at.desc()).all()
    results = []
    for app, job, match in rows:
        results.append({
            "id": app.id,
            "job_id": app.job_id,
            "job_title": job.title,
            "company": job.company,
            "application_url": job.application_url,
            "status": app.status,
            "mode": app.mode,
            "overall_score": match.overall_score if match else 0,
            "score_label": match.score_label if match else None,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
            "next_followup_at": app.next_followup_at.isoformat() if app.next_followup_at else None,
            "followup_count": app.followup_count,
            "created_at": app.created_at.isoformat() if app.created_at else None,
            "updated_at": app.updated_at.isoformat() if app.updated_at else None,
        })
    return results


@router.get("/applications/{app_id}")
def get_application(app_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    job = db.query(Job).filter(Job.id == app.job_id).first()
    events = db.query(ApplicationEvent).filter(ApplicationEvent.application_id == app_id).order_by(ApplicationEvent.created_at).all()

    return {
        "id": app.id,
        "job": {"id": job.id, "title": job.title, "company": job.company, "url": job.application_url} if job else None,
        "status": app.status,
        "mode": app.mode,
        "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        "user_notes": app.user_notes,
        "events": [
            {"from": e.from_status, "to": e.to_status, "actor": e.actor, "note": e.note,
             "at": e.created_at.isoformat() if e.created_at else None}
            for e in events
        ],
    }


@router.post("/applications/{app_id}/approve")
def approve_application(app_id: str, req: ApproveRequest, db: Session = Depends(get_db)):
    """Approve an application for submission. Moves to APPROVED state."""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        evt = transition(app, "APPROVED", actor="user", note=req.notes)
        db.add(evt)
        db.commit()
        return {"status": "approved"}
    except StateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/applications/{app_id}/reject")
def reject_application(app_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        evt = transition(app, "REJECTED", actor="user")
        db.add(evt)
        db.commit()
        return {"status": "rejected"}
    except StateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/applications/{app_id}/submit")
def mark_submitted(app_id: str, db: Session = Depends(get_db)):
    """Mark an application as submitted (after user manually submits)."""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    from datetime import datetime
    try:
        evt = transition(app, "SUBMITTED", actor="user", note="Manually submitted")
        app.submitted_at = datetime.utcnow()
        db.add(evt)
        db.commit()
        return {"status": "submitted"}
    except StateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/applications/{app_id}/status")
def update_status(app_id: str, req: StatusUpdateRequest, db: Session = Depends(get_db)):
    """Generic status update with state machine validation."""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        evt = transition(app, req.status.upper(), actor="user", note=req.note)
        db.add(evt)
        db.commit()
        return {"status": req.status.upper()}
    except StateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/applications/{app_id}/generate-resume")
def generate_resume(app_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Trigger resume optimization for this application."""
    from fastapi import BackgroundTasks
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    job = db.query(Job).filter(Job.id == app.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from ...agents.resume.agent import ResumeAgent
    from ...core.models import JobAnalysis

    analysis = db.query(JobAnalysis).filter(JobAnalysis.job_id == job.id).first()

    def _run():
        agent = ResumeAgent()
        agent.run({
            "job_id": job.id,
            "application_id": app.id,
            "job_title": job.title,
            "company": job.company,
            "job_description": job.description or "",
            "required_skills": analysis.required_skills if analysis else [],
        })

    background_tasks.add_task(_run)
    return {"status": "generating"}


@router.get("/applications/{app_id}/resume")
def get_resume(app_id: str, db: Session = Depends(get_db)):
    """Get the latest generated resume for this application."""
    version = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.application_id == app_id)
        .order_by(ResumeVersion.version_number.desc())
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="No resume generated for this application yet")
    return {
        "version_number": version.version_number,
        "content_markdown": version.content_markdown,
        "keywords_added": version.keywords_added or [],
        "ats_score": version.ats_score,
        "model_used": version.model_used,
        "generated_at": version.generated_at.isoformat() if version.generated_at else None,
    }


@router.get("/applications/{app_id}/cover-letter")
def get_cover_letter(app_id: str, db: Session = Depends(get_db)):
    """Get the generated cover letter for this application."""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    letter = (
        db.query(CoverLetter)
        .filter(CoverLetter.job_id == app.job_id)
        .order_by(CoverLetter.generated_at.desc())
        .first()
    )
    if not letter:
        raise HTTPException(status_code=404, detail="No cover letter generated for this application yet")
    return {
        "content": letter.content,
        "model_used": letter.model_used,
        "generated_at": letter.generated_at.isoformat() if letter.generated_at else None,
    }


@router.post("/applications/{app_id}/generate-cover-letter")
def generate_cover_letter(app_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Trigger cover letter generation for this application."""
    from fastapi import BackgroundTasks
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    job = db.query(Job).filter(Job.id == app.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from ...agents.cover_letter.agent import CoverLetterAgent
    from ...core.models import JobMatch

    match = db.query(JobMatch).filter(JobMatch.job_id == job.id).first()

    def _run():
        agent = CoverLetterAgent()
        agent.run({
            "job_id": job.id,
            "application_id": app.id,
            "job_title": job.title,
            "company": job.company,
            "job_description": job.description or "",
            "required_skills": [],
            "match_reason": match.match_reason_summary if match else "",
        })

    background_tasks.add_task(_run)
    return {"status": "generating"}
