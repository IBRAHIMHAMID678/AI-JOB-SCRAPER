"""
Reliable Job Pipeline Scheduler.
Runs the discovery pipeline automatically on a configurable interval (1-2 hours).
Uses APScheduler if installed, and seamlessly falls back to a robust standard library
background worker thread so scheduling ALWAYS functions without external dependencies.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

_scheduler = None
_thread_stop_event = threading.Event()
_scheduler_thread = None
_next_run_time = None


def start_scheduler() -> None:
    """Start background scheduler with seamless thread fallback."""
    global _scheduler, _scheduler_thread, _thread_stop_event, _next_run_time

    interval_hours = getattr(settings, "SCRAPE_INTERVAL_HOURS", 2) or 2
    if interval_hours <= 0:
        logger.info("[SCHEDULER] SCRAPE_INTERVAL_HOURS=0 — automated scheduling disabled")
        return

    # Try APScheduler first
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.add_job(
            _run_pipeline_job,
            trigger=IntervalTrigger(hours=interval_hours),
            id="pipeline_auto",
            name="Scheduled pipeline run",
            replace_existing=True,
            max_instances=1,
        )
        _scheduler.start()
        logger.info("[SCHEDULER] APScheduler started — running every %d hour(s)", interval_hours)
        return
    except ImportError:
        logger.info("[SCHEDULER] APScheduler not installed. Using native daemon scheduler thread.")

    # Native Background Thread Scheduler
    _thread_stop_event.clear()

    def _daemon_loop():
        global _next_run_time
        interval_seconds = interval_hours * 3600
        logger.info("[SCHEDULER:THREAD] Autonomous scheduler loop active. Interval: %d seconds (%d hours)", interval_seconds, interval_hours)

        while not _thread_stop_event.is_set():
            _next_run_time = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
            # Sleep in small slices so shutdown is instant
            for _ in range(int(interval_seconds)):
                if _thread_stop_event.is_set():
                    return
                time.sleep(1)

            if not _thread_stop_event.is_set():
                logger.info("[SCHEDULER:THREAD] Scheduled wake-up trigger initiated.")
                _run_pipeline_job()

    _scheduler_thread = threading.Thread(target=_daemon_loop, daemon=True, name="JobHarvesterScheduler")
    _scheduler_thread.start()
    _next_run_time = datetime.now(timezone.utc) + timedelta(seconds=interval_hours * 3600)
    logger.info("[SCHEDULER] Native autonomous scheduler launched successfully.")


def stop_scheduler() -> None:
    global _scheduler, _scheduler_thread, _thread_stop_event
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] APScheduler stopped")
    _scheduler = None

    _thread_stop_event.set()
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("[SCHEDULER] Native scheduler thread stopped")
    _scheduler_thread = None


def _run_pipeline_job() -> None:
    """Runs the full multi-source harvesting pipeline."""
    from .pipeline import run_pipeline, is_pipeline_running
    if is_pipeline_running():
        logger.info("[SCHEDULER] Pipeline is already running — skipping redundant trigger.")
        return
    logger.info("[SCHEDULER] Scheduled autonomous pipeline starting now...")
    try:
        summary = run_pipeline(trigger="scheduled")
        logger.info("[SCHEDULER] Scheduled pipeline complete: %s", summary)
    except Exception as exc:
        logger.error("[SCHEDULER] Scheduled pipeline encountered an error: %s", exc)


def get_next_run_time() -> str | None:
    """Return ISO string of next scheduled run, or None."""
    global _scheduler, _next_run_time
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("pipeline_auto")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
    if _next_run_time:
        return _next_run_time.isoformat()
    return None
