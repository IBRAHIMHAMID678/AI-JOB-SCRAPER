"""
JOBPILOT FastAPI application entry point.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..core.config import settings
from ..core.database import init_db
from ..core.events import bus
from ..core.logging import (
    get_logger,
    _sse_log_queue,
    _sse_job_queue,
    _sse_pending_queue,
)
from .routes import jobs, applications, agents, analytics, notifications, system, profile, email, whatsapp

logger = get_logger(__name__)

_start_time = time.time()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.environ.get("JOBPILOT_STATIC_DIR", os.path.join(BASE_DIR, "static"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("JOBPILOT starting up...")
    init_db()
    bus.start()
    _seed_default_data()
    from ..workers.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    logger.info("JOBPILOT ready — database initialized, event bus started")
    yield
    stop_scheduler()
    bus.stop()
    logger.info("JOBPILOT shutdown complete")


def _seed_default_data():
    """Create default candidate profile and master resume if not present."""
    try:
        from ..core.database import db_session
        from ..core.models import CandidateProfile, SystemSetting
        with db_session() as db:
            if not db.query(CandidateProfile).first():
                db.add(CandidateProfile(
                    name=settings.CANDIDATE_NAME,
                    email=settings.CANDIDATE_EMAIL,
                    location=settings.CANDIDATE_LOCATION,
                    timezone=settings.CANDIDATE_TIMEZONE,
                    remote_preference=settings.CANDIDATE_REMOTE_PREFERENCE,
                    work_authorization=settings.CANDIDATE_WORK_AUTHORIZATION,
                    skills=["Python", "FastAPI", "React", "Next.js", "Node.js", "LangChain", "RAG", "MongoDB", "LLM", "TypeScript"],
                    preferred_roles=["AI Engineer", "Full Stack Developer", "LLM Engineer", "Python Developer"],
                    salary_min_usd_hourly=15.0,
                    salary_max_usd_hourly=60.0,
                    years_experience=0,
                ))
                logger.info("Default candidate profile created")
    except Exception as exc:
        logger.warning("Could not seed default data: %s", exc)


app = FastAPI(
    title="JOBPILOT",
    description="AI-powered career automation platform",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ──────────────────────────────────────────────────────────────
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(jobs.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(email.router, prefix="/api")
app.include_router(whatsapp.router, prefix="/api")


# ── SSE stream ────────────────────────────────────────────────────────────────
@app.get("/api/stream")
async def sse_stream():
    """Real-time event stream for the dashboard."""
    from ..workers.pipeline import is_pipeline_running, get_source_stats

    async def event_generator():
        while True:
            # Flush log queue
            while not _sse_log_queue.empty():
                try:
                    msg = _sse_log_queue.get_nowait()
                    yield {"event": "log", "data": json.dumps({
                        "message": msg,
                        "sources": get_source_stats(),
                        "timestamp": datetime.utcnow().isoformat(),
                    })}
                except Exception:
                    break

            # Flush matched job queue
            while not _sse_job_queue.empty():
                try:
                    job = _sse_job_queue.get_nowait()
                    yield {"event": "job", "data": json.dumps(job, default=str)}
                except Exception:
                    break

            # Flush pending job queue
            while not _sse_pending_queue.empty():
                try:
                    job = _sse_pending_queue.get_nowait()
                    yield {"event": "pending_job", "data": json.dumps(job, default=str)}
                except Exception:
                    break

            if not is_pipeline_running() and _sse_log_queue.empty():
                yield {"event": "heartbeat", "data": json.dumps({"ts": datetime.utcnow().isoformat()})}

            await asyncio.sleep(0.4)

    return EventSourceResponse(event_generator())


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_dashboard():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>JOBPILOT</h1><p>Dashboard not found. Place index.html in /static/</p>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("jobpilot.api.main:app", host="0.0.0.0", port=8000, reload=True)
