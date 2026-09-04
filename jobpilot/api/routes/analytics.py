"""Analytics endpoints — user-scoped."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import Application, Job, JobMatch, DailyApplyLog
from .auth import get_current_user

router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db), user=Depends(get_current_user)):
    today = datetime.utcnow().date().isoformat()

    total_jobs = db.query(JobMatch).filter(JobMatch.user_id == user.id).count()
    matched = db.query(JobMatch).filter(
        JobMatch.user_id == user.id,
        JobMatch.overall_score >= 40,
    ).count()
    high_match = db.query(JobMatch).filter(
        JobMatch.user_id == user.id,
        JobMatch.overall_score >= 90,
    ).count()
    good_match = db.query(JobMatch).filter(
        JobMatch.user_id == user.id,
        JobMatch.overall_score >= 80,
        JobMatch.overall_score < 90,
    ).count()

    total_apps = db.query(Application).filter(Application.user_id == user.id).count()
    submitted = db.query(Application).filter(
        Application.user_id == user.id,
        Application.status == "SUBMITTED",
    ).count()

    # Today's apply counts per tier
    t1 = db.query(DailyApplyLog).filter_by(user_id=user.id, date=today, tier=1).first()
    t2 = db.query(DailyApplyLog).filter_by(user_id=user.id, date=today, tier=2).first()
    applied_tier1_today = t1.count if t1 else 0
    applied_tier2_today = t2.count if t2 else 0
    applied_today = applied_tier1_today + applied_tier2_today

    new_today = db.query(JobMatch).filter(
        JobMatch.user_id == user.id,
        func.date(JobMatch.matched_at) == datetime.utcnow().date(),
    ).count()

    return {
        "total_jobs": total_jobs,
        "jobs_discovered": total_jobs,
        "jobs_matched": matched,
        "high_match": high_match,
        "good_match": good_match,
        "total_applied": total_apps,
        "applications_total": total_apps,
        "applications_submitted": submitted,
        "applied_today": applied_today,
        "applied_tier1_today": applied_tier1_today,
        "applied_tier2_today": applied_tier2_today,
        "pending_review": db.query(Application).filter(
            Application.user_id == user.id,
            Application.status.in_(["DISCOVERED", "MATCHED", "READY_FOR_REVIEW"]),
        ).count(),
        "new_today": new_today,
    }


@router.get("/analytics/score-distribution")
def score_distribution(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.query(JobMatch.overall_score).filter(JobMatch.user_id == user.id).all()
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
def application_timeline(db: Session = Depends(get_db), user=Depends(get_current_user), days: int = 30):
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(
        func.date(Application.created_at),
        func.count(Application.id),
    ).filter(
        Application.user_id == user.id,
        Application.created_at >= since,
    ).group_by(func.date(Application.created_at)).all()
    return [{"date": str(r[0]), "count": r[1]} for r in rows]


@router.get("/analytics/status-breakdown")
def status_breakdown(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.query(Application.status, func.count(Application.id)).filter(
        Application.user_id == user.id
    ).group_by(Application.status).all()
    return [{"status": r[0], "count": r[1]} for r in rows]
