"""System health and configuration endpoints."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.database import get_db
from ...core.models import Application, Job

router = APIRouter(tags=["system"])

_start_time = time.time()


@router.get("/system/status")
def system_status(db: Session = Depends(get_db)):
    total_jobs = db.query(Job).count()
    total_apps = db.query(Application).count()

    from ...integrations.whatsapp.client import get_whatsapp_client
    from ...integrations.email.oauth import get_email_client
    from ...workers.scheduler import get_next_run_time
    whatsapp = get_whatsapp_client()
    email = get_email_client()

    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected",
        "redis": "not_configured",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "whatsapp": "configured" if whatsapp.is_configured else "pending_configuration",
        "email": "configured" if email.is_configured else "pending_configuration",
        "jobs_total": total_jobs,
        "applications_total": total_apps,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "application_mode": settings.APPLICATION_MODE,
        "auto_application_enabled": settings.AUTO_APPLICATION_ENABLED,
        "next_scheduled_run": get_next_run_time(),
        "scrape_interval_hours": settings.SCRAPE_INTERVAL_HOURS,
    }


@router.get("/system/config")
def get_config():
    """Return non-sensitive configuration settings."""
    return {
        "score_thresholds": {
            "high_priority": settings.SCORE_HIGH_PRIORITY,
            "good_match": settings.SCORE_GOOD_MATCH,
            "possible_match": settings.SCORE_POSSIBLE_MATCH,
            "auto_approve": settings.SCORE_AUTO_APPROVE,
            "min_threshold": settings.SCORE_MIN_THRESHOLD,
        },
        "application": {
            "mode": settings.APPLICATION_MODE,
            "require_approval": settings.REQUIRE_APPROVAL,
            "max_per_day": settings.MAX_APPLICATIONS_PER_DAY,
        },
        "scraping": {
            "search_terms": settings.SEARCH_TERMS,
            "results_per_term": settings.RESULTS_PER_TERM,
            "interval_hours": settings.SCRAPE_INTERVAL_HOURS,
        },
        "candidate": {
            "name": settings.CANDIDATE_NAME,
            "location": settings.CANDIDATE_LOCATION,
            "remote_preference": settings.CANDIDATE_REMOTE_PREFERENCE,
        },
    }


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "JOBPILOT"}
