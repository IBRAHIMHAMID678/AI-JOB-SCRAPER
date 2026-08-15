"""Agent monitoring and control endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import AgentRun

router = APIRouter(tags=["agents"])


@router.get("/agents/runs")
def list_agent_runs(db: Session = Depends(get_db), limit: int = 50):
    runs = db.query(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "agent_name": r.agent_name,
            "status": r.status,
            "trigger": r.trigger,
            "items_processed": r.items_processed,
            "items_succeeded": r.items_succeeded,
            "items_failed": r.items_failed,
            "duration_seconds": r.duration_seconds,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in runs
    ]


@router.get("/agents/status")
def pipeline_status():
    from ...workers.pipeline import is_pipeline_running, get_source_stats
    return {
        "pipeline_running": is_pipeline_running(),
        "source_stats": get_source_stats(),
    }
