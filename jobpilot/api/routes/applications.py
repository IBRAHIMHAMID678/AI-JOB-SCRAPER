"""Application tracking — user-scoped."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import Application, ApplicationEvent, Job, JobMatch, CoverLetter, ResumeVersion
from ...core.state_machine import StateMachineError, transition
from .auth import get_current_user

router = APIRouter(tags=["applications"])


class ApproveRequest(BaseModel):
    notes: Optional[str] = None


class StatusUpdateRequest(BaseModel):
    status: str
    note: Optional[str] = None


@router.get("/applications")
def list_applications(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    status: Optional[str] = None,
    limit: int = 100,
):
    query = (
        db.query(Application, Job, JobMatch)
        .join(Job, Application.job_id == Job.id)
        .outerjoin(JobMatch, (Job.id == JobMatch.job_id) & (JobMatch.user_id == user.id))
        .filter(Application.user_id == user.id)
    )
    if status:
        query = query.filter(Application.status == status.upper())
    rows = query.order_by(desc(Application.updated_at)).limit(limit).all()
    return [
        {
            "id": app.id,
            "job_id": app.job_id,
            "job_title": job.title,
            "company": job.company,
            "application_url": job.application_url,
            "job_url": job.application_url,
            "status": app.status,
            "mode": app.mode,
            "overall_score": match.overall_score if match else 0,
            "score_label": match.score_label if match else None,
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
            "next_followup_at": app.next_followup_at.isoformat() if app.next_followup_at else None,
            "followup_count": app.followup_count,
            "created_at": app.created_at.isoformat() if app.created_at else None,
            "updated_at": app.updated_at.isoformat() if app.updated_at else None,
        }
        for app, job, match in rows
    ]


@router.get("/applications/{app_id}")
def get_application(app_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
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
def approve_application(app_id: str, req: ApproveRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
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
def reject_application(app_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
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
def mark_submitted(app_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    from datetime import datetime
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        evt = transition(app, "SUBMITTED", actor="user", note="Manually submitted")
        app.submitted_at = datetime.utcnow()
        db.add(evt)
        db.commit()
        return {"status": "submitted"}
    except StateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/applications/{app_id}/status")
def update_status(app_id: str, req: StatusUpdateRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user.id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        evt = transition(app, req.status.upper(), actor="user", note=req.note)
        db.add(evt)
        db.commit()
        return {"status": req.status.upper()}
    except StateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))
