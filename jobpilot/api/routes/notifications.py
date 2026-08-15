"""Notification management endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.models import Notification

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db), limit: int = 50, unread_only: bool = False):
    query = db.query(Notification)
    if unread_only:
        query = query.filter(Notification.sent == False)
    notifs = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return [
        {
            "id": n.id,
            "event_type": n.event_type,
            "channel": n.channel,
            "title": n.title,
            "body": n.body,
            "sent": n.sent,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifs
    ]
