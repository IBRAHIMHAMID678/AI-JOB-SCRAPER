"""
APScheduler-based job pipeline scheduler.
Runs the discovery pipeline automatically on a configurable interval.
Falls back to no-op if APScheduler is not installed.
"""
from __future__ import annotations

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

_scheduler = None


def start_scheduler() -> None:
    """Start background scheduler if APScheduler is available."""
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.info("APScheduler not installed — automated scheduling disabled")
        return

    if settings.SCRAPE_INTERVAL_HOURS <= 0:
        logger.info("SCRAPE_INTERVAL_HOURS=0 — automated scheduling disabled")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_pipeline_job,
        trigger=IntervalTrigger(hours=settings.SCRAPE_INTERVAL_HOURS),
        id="pipeline_auto",
        name="Scheduled pipeline run",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(
        "Auto-scheduler started — pipeline will run every %d hour(s)",
        settings.SCRAPE_INTERVAL_HOURS,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Auto-scheduler stopped")
    _scheduler = None


def _run_pipeline_job() -> None:
    """Called by APScheduler — runs the full pipeline."""
    from .pipeline import run_pipeline, is_pipeline_running
    if is_pipeline_running():
        logger.info("Scheduled pipeline skipped — already running")
        return
    logger.info("Scheduled pipeline starting...")
    try:
        summary = run_pipeline(trigger="scheduled")
        logger.info("Scheduled pipeline complete: %s", summary)
    except Exception as exc:
        logger.error("Scheduled pipeline error: %s", exc)


def get_next_run_time() -> str | None:
    """Return ISO string of next scheduled run, or None."""
    if not _scheduler or not _scheduler.running:
        return None
    job = _scheduler.get_job("pipeline_auto")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
