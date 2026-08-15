"""Analytics and reporting endpoints."""
from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import List

import pandas as pd
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import Application, Job, JobMatch

router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db)):
    total_jobs = db.query(Job).count()
    total_apps = db.query(Application).count()
    submitted = db.query(Application).filter(Application.status == "SUBMITTED").count()
    interviews = db.query(Application).filter(Application.status == "INTERVIEW").count()
    offers = db.query(Application).filter(Application.status == "OFFER").count()
    matched = db.query(JobMatch).filter(JobMatch.overall_score >= 40).count()

    response_rate = (interviews / submitted * 100) if submitted > 0 else 0
    interview_rate = (interviews / submitted * 100) if submitted > 0 else 0

    return {
        "jobs_discovered": total_jobs,
        "jobs_matched": matched,
        "applications_total": total_apps,
        "applications_submitted": submitted,
        "interviews": interviews,
        "offers": offers,
        "response_rate": round(response_rate, 1),
        "interview_rate": round(interview_rate, 1),
    }


@router.get("/analytics/score-distribution")
def score_distribution(db: Session = Depends(get_db)):
    rows = db.query(JobMatch.overall_score).all()
    scores = [r[0] for r in rows if r[0] is not None]
    buckets = {"0-29": 0, "30-59": 0, "60-74": 0, "75-89": 0, "90-100": 0}
    for s in scores:
        if s < 30:
            buckets["0-29"] += 1
        elif s < 60:
            buckets["30-59"] += 1
        elif s < 75:
            buckets["60-74"] += 1
        elif s < 90:
            buckets["75-89"] += 1
        else:
            buckets["90-100"] += 1
    return buckets


@router.get("/analytics/source-performance")
def source_performance(db: Session = Depends(get_db)):
    rows = db.query(Job.source_name, func.count(Job.id)).group_by(Job.source_name).all()
    return [{"source": r[0], "count": r[1]} for r in rows]


@router.get("/analytics/application-timeline")
def application_timeline(db: Session = Depends(get_db), days: int = 30):
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(
        func.date(Application.created_at),
        func.count(Application.id)
    ).filter(Application.created_at >= since).group_by(func.date(Application.created_at)).all()
    return [{"date": str(r[0]), "count": r[1]} for r in rows]


@router.get("/analytics/status-breakdown")
def status_breakdown(db: Session = Depends(get_db)):
    rows = db.query(Application.status, func.count(Application.id)).group_by(Application.status).all()
    return [{"status": r[0], "count": r[1]} for r in rows]


@router.get("/download/csv")
def download_csv(db: Session = Depends(get_db), score_min: int = 40):
    rows = db.query(Job, JobMatch).outerjoin(JobMatch, Job.id == JobMatch.job_id).filter(
        JobMatch.overall_score >= score_min
    ).order_by(JobMatch.overall_score.desc()).all()

    data = []
    for job, match in rows:
        data.append({
            "Score": match.overall_score if match else 0,
            "Title": job.title,
            "Company": job.company,
            "Location": job.location,
            "Remote": job.remote_type,
            "Salary": job.salary_raw or "Not Disclosed",
            "Source": job.source_name,
            "URL": job.application_url,
            "Match Reason": match.match_reason_summary if match else "",
            "Discovered": job.discovered_at.strftime("%Y-%m-%d") if job.discovered_at else "",
        })

    if not data:
        return {"error": "No jobs to export"}

    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="jobpilot_jobs_{datetime.now().strftime("%Y%m%d")}.csv"'},
    )
