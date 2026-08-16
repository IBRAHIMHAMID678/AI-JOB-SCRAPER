"""
CV upload and management routes.
POST /api/cvs/upload  — upload a CV file (PDF/DOCX)
GET  /api/cvs         — list all uploaded CVs
GET  /api/cvs/{id}    — CV detail + parsed data
DELETE /api/cvs/{id}  — delete a CV
PATCH /api/cvs/{id}/default — set as default CV
POST /api/cvs/test-telegram — test Telegram connection
"""
from __future__ import annotations

import os
import pathlib
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ...core.config import settings
from ...core.database import db_session
from ...core.logging import get_logger
from ...core.models import UploadedCV
from ...services.cv_parser import parse_cv
from ...services.telegram_service import test_connection

logger = get_logger(__name__)
router = APIRouter(prefix="/cvs", tags=["CVs"])

ALLOWED_TYPES = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
ALLOWED_EXT = {".pdf", ".doc", ".docx", ".txt"}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB


def _upload_dir() -> pathlib.Path:
    d = pathlib.Path(settings.CV_UPLOAD_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/upload")
async def upload_cv(
    file: UploadFile = File(...),
    name: str = Form(""),
    target_roles: str = Form(""),
):
    ext = pathlib.Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type: {ext}. Use PDF, DOCX, or TXT.")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "File too large (max 10 MB).")

    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = str(_upload_dir() / filename)
    with open(file_path, "wb") as f:
        f.write(content)

    label = name.strip() or file.filename or "My CV"
    roles = [r.strip() for r in target_roles.split(",") if r.strip()]

    try:
        parsed = parse_cv(file_path, file.content_type or "")
    except Exception as exc:
        logger.error("CV parse error: %s", exc)
        parsed = {"skills": [], "keywords": [], "roles": roles, "experience_years": 0,
                  "education": [], "summary": "", "raw_text": ""}

    with db_session() as db:
        is_first = db.query(UploadedCV).count() == 0
        cv = UploadedCV(
            name=label,
            filename=file.filename or filename,
            file_path=file_path,
            file_size=len(content),
            mime_type=file.content_type,
            raw_text=parsed.get("raw_text", "")[:50000],
            skills=parsed.get("skills", []),
            keywords=parsed.get("keywords", []),
            roles=parsed.get("roles", []),
            experience_years=parsed.get("experience_years"),
            education=parsed.get("education", []),
            summary=parsed.get("summary", ""),
            target_roles=roles or parsed.get("roles", []),
            is_default=is_first,
            parsed_at=datetime.utcnow(),
        )
        db.add(cv)
        db.flush()
        cv_id = cv.id

    return JSONResponse({
        "id": cv_id,
        "name": label,
        "skills": parsed.get("skills", []),
        "keywords": parsed.get("keywords", []),
        "roles": parsed.get("roles", []),
        "experience_years": parsed.get("experience_years"),
        "summary": parsed.get("summary", ""),
        "is_default": is_first,
        "message": "CV uploaded and parsed successfully",
    })


@router.get("")
def list_cvs():
    with db_session() as db:
        cvs = db.query(UploadedCV).filter_by(is_active=True).order_by(UploadedCV.created_at.desc()).all()
        return [
            {
                "id": cv.id,
                "name": cv.name,
                "filename": cv.filename,
                "skills": cv.skills or [],
                "keywords": cv.keywords or [],
                "roles": cv.roles or [],
                "target_roles": cv.target_roles or [],
                "experience_years": cv.experience_years,
                "summary": cv.summary,
                "is_default": cv.is_default,
                "file_size": cv.file_size,
                "created_at": cv.created_at.isoformat() if cv.created_at else None,
            }
            for cv in cvs
        ]


@router.get("/{cv_id}")
def get_cv(cv_id: str):
    with db_session() as db:
        cv = db.query(UploadedCV).filter_by(id=cv_id).first()
        if not cv:
            raise HTTPException(404, "CV not found")
        return {
            "id": cv.id,
            "name": cv.name,
            "filename": cv.filename,
            "skills": cv.skills or [],
            "keywords": cv.keywords or [],
            "roles": cv.roles or [],
            "target_roles": cv.target_roles or [],
            "experience_years": cv.experience_years,
            "education": cv.education or [],
            "summary": cv.summary,
            "is_default": cv.is_default,
            "file_size": cv.file_size,
            "parsed_at": cv.parsed_at.isoformat() if cv.parsed_at else None,
            "created_at": cv.created_at.isoformat() if cv.created_at else None,
        }


@router.patch("/{cv_id}/default")
def set_default_cv(cv_id: str):
    with db_session() as db:
        cv = db.query(UploadedCV).filter_by(id=cv_id).first()
        if not cv:
            raise HTTPException(404, "CV not found")
        db.query(UploadedCV).update({"is_default": False})
        cv.is_default = True
    return {"message": "Default CV updated"}


@router.delete("/{cv_id}")
def delete_cv(cv_id: str):
    with db_session() as db:
        cv = db.query(UploadedCV).filter_by(id=cv_id).first()
        if not cv:
            raise HTTPException(404, "CV not found")
        try:
            if cv.file_path and pathlib.Path(cv.file_path).exists():
                os.remove(cv.file_path)
        except Exception:
            pass
        cv.is_active = False
    return {"message": "CV deleted"}


@router.post("/test-telegram")
def test_telegram():
    ok = test_connection()
    if ok:
        return {"message": "Telegram notification sent successfully!"}
    return JSONResponse(
        status_code=400,
        content={"message": "Telegram not configured or failed. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"}
    )
