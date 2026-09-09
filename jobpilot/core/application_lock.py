"""
Atomic Application Lock Engine for JOBPILOT.
Prevents concurrent workers or multiple process runs from applying to the same job.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Optional
from contextlib import contextmanager

from .config import settings
from .database import db_session, engine
from .models import ApplicationLock, Base
from .logging import get_logger

logger = get_logger("core.application_lock")


def init_lock_tables() -> None:
    """Ensure ApplicationLock table exists."""
    Base.metadata.create_all(bind=engine, tables=[ApplicationLock.__table__])


def acquire_application_lock(
    canonical_job_id: str,
    candidate_id: str = "3e614c95-b3a4-43d6-805d-3ffed73f64ba",
    worker_id: Optional[str] = None,
    timeout_seconds: int = 180,
) -> bool:
    """
    Tries to atomically acquire an application lock in the database.
    Returns True if acquired, False if already locked or previously applied.
    """
    if not canonical_job_id:
        return False

    init_lock_tables()
    worker_id = worker_id or f"worker_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=timeout_seconds)

    try:
        with db_session() as db:
            existing = db.query(ApplicationLock).filter_by(canonical_job_id=canonical_job_id).first()
            if existing:
                if existing.expires_at > now and existing.worker_id != worker_id:
                    logger.warning(
                        "[LOCK BLOCKED] Canonical Job %s is currently locked by %s until %s",
                        canonical_job_id,
                        existing.worker_id,
                        existing.expires_at,
                    )
                    return False
                else:
                    # Lock expired or re-entrant lock from the same worker
                    if existing.worker_id == worker_id:
                        logger.debug("[LOCK RE-ENTRANT] Re-entrant lock for %s held by %s extended", canonical_job_id, worker_id)
                    else:
                        logger.info("[LOCK RECLAIM] Expired lock for %s reclaimed by %s", canonical_job_id, worker_id)
                    existing.candidate_id = candidate_id
                    existing.worker_id = worker_id
                    existing.locked_at = now
                    existing.expires_at = expires_at
                    db.commit()
                    return True

            # Insert new lock
            lock = ApplicationLock(
                canonical_job_id=canonical_job_id,
                candidate_id=candidate_id,
                worker_id=worker_id,
                locked_at=now,
                expires_at=expires_at,
            )
            db.add(lock)
            db.commit()
            logger.info("[LOCK ACQUIRED] Canonical Job %s acquired by %s", canonical_job_id, worker_id)
            return True
    except Exception as exc:
        logger.warning("[LOCK ERROR] Failed to acquire lock for %s: %s", canonical_job_id, exc)
        return False


def release_application_lock(canonical_job_id: str, worker_id: Optional[str] = None) -> None:
    """Releases an acquired application lock."""
    if not canonical_job_id:
        return
    try:
        with db_session() as db:
            q = db.query(ApplicationLock).filter_by(canonical_job_id=canonical_job_id)
            if worker_id:
                q = q.filter_by(worker_id=worker_id)
            q.delete()
            db.commit()
            logger.info("[LOCK RELEASED] Lock released for canonical job %s", canonical_job_id)
    except Exception as exc:
        logger.warning("[LOCK RELEASE ERROR] Failed to release lock for %s: %s", canonical_job_id, exc)


@contextmanager
def application_lock_context(
    canonical_job_id: str,
    candidate_id: str = "3e614c95-b3a4-43d6-805d-3ffed73f64ba",
    worker_id: Optional[str] = None,
    timeout_seconds: int = 180,
):
    """Context manager for acquiring and releasing an application lock."""
    worker_id = worker_id or f"worker_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    acquired = acquire_application_lock(canonical_job_id, candidate_id, worker_id, timeout_seconds)
    if not acquired:
        yield False
    else:
        try:
            yield True
        finally:
            release_application_lock(canonical_job_id, worker_id)
