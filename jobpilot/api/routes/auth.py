"""
Auth routes: register, login, logout, me, settings.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from ...services import auth_service

router = APIRouter(tags=["auth"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    username: str
    email: str
    password: str


class LoginBody(BaseModel):
    username_or_email: str
    password: str


class SettingsBody(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    linkedin_email: Optional[str] = None
    linkedin_password: Optional[str] = None
    indeed_email: Optional[str] = None
    indeed_password: Optional[str] = None
    rozee_email: Optional[str] = None
    rozee_password: Optional[str] = None
    groq_api_key: Optional[str] = None
    search_terms: Optional[list] = None
    remote_preference: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[float] = None
    notify_on_apply: Optional[bool] = None
    notify_daily_summary: Optional[bool] = None


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _token_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("session_token")


def get_current_user(request: Request):
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    return user


def get_current_user_optional(request: Request):
    token = _token_from_request(request)
    if not token:
        return None
    return auth_service.get_user_by_token(token)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/api/auth/register")
def register(body: RegisterBody):
    if len(body.username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    try:
        user = auth_service.register(body.username, body.email, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    token = auth_service.login(body.username, body.password)
    return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}


@router.post("/api/auth/login")
def login(body: LoginBody):
    token = auth_service.login(body.username_or_email, body.password)
    if not token:
        raise HTTPException(401, "Invalid credentials")
    user = auth_service.get_user_by_token(token)
    return {"token": token, "user": {"id": user.id, "username": user.username, "email": user.email}}


@router.post("/api/auth/logout")
def logout(request: Request):
    token = _token_from_request(request)
    if token:
        auth_service.logout(token)
    return {"ok": True}


@router.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "email": user.email}


# ── User settings ──────────────────────────────────────────────────────────────

@router.get("/api/user/settings")
def get_settings(user=Depends(get_current_user)):
    s = auth_service.get_settings(user.id)
    if not s:
        return {}
    return {
        "telegram_bot_token": s.telegram_bot_token or "",
        "telegram_chat_id": s.telegram_chat_id or "",
        "linkedin_email": s.linkedin_email or "",
        "linkedin_password": "••••••" if s.linkedin_password_enc else "",
        "indeed_email": s.indeed_email or "",
        "indeed_password": "••••••" if s.indeed_password_enc else "",
        "rozee_email": s.rozee_email or "",
        "rozee_password": "••••••" if s.rozee_password_enc else "",
        "groq_api_key": s.groq_api_key or "",
        "search_terms": s.search_terms or [],
        "remote_preference": s.remote_preference or "worldwide_remote",
        "location": s.location or "",
        "salary_min": s.salary_min,
        "notify_on_apply": s.notify_on_apply,
        "notify_daily_summary": s.notify_daily_summary,
    }


@router.put("/api/user/settings")
def update_settings(body: SettingsBody, user=Depends(get_current_user)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    # Don't overwrite encrypted password if placeholder sent
    for field in ("linkedin_password", "indeed_password", "rozee_password"):
        if data.get(field) == "••••••":
            del data[field]
    auth_service.update_settings(user.id, data)
    return {"ok": True}


@router.post("/api/user/test-telegram")
def test_telegram(user=Depends(get_current_user)):
    s = auth_service.get_settings(user.id)
    if not s or not s.telegram_bot_token or not s.telegram_chat_id:
        raise HTTPException(400, "Telegram credentials not configured in your settings")
    from ...services.telegram_service import send
    import httpx
    try:
        url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
        r = httpx.post(url, json={
            "chat_id": s.telegram_chat_id,
            "text": "✅ <b>JOBPILOT</b> — Telegram connected successfully!",
            "parse_mode": "HTML",
        }, timeout=10)
        r.raise_for_status()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"Telegram error: {e}")
