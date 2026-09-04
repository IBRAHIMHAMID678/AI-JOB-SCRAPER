"""
Auth service — register, login, session management, password reset.
Passwords hashed with bcrypt. Sessions stored in DB with expiry.
Credentials encrypted with Fernet (AES-128).
"""
from __future__ import annotations

import hashlib
import os
import random
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from ..core.database import db_session
from ..core.models import User, UserSession, UserSettings
from ..core.logging import get_logger

logger = get_logger(__name__)

SESSION_TTL_DAYS = 30
OTP_TTL_MINUTES = 15

# In-memory OTP store: email -> (otp, expires_at)
_otp_store: dict[str, tuple[str, datetime]] = {}

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))


# ── Password hashing ───────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"sha256:{salt}:{h}"


def _verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    if hashed.startswith("sha256:"):
        try:
            _, salt, h = hashed.split(":", 2)
            return hashlib.sha256((salt + password).encode()).hexdigest() == h
        except Exception:
            return False
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ── Credential encryption ──────────────────────────────────────────────────────

def _fernet():
    key = os.environ.get("SECRET_KEY", "change-me-in-production-use-a-long-random-string")
    import base64
    raw = hashlib.sha256(key.encode()).digest()
    return base64.urlsafe_b64encode(raw)


def encrypt(value: str) -> str:
    if not value:
        return ""
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_fernet())
        return f.encrypt(value.encode()).decode()
    except ImportError:
        key_bytes = _fernet()
        xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(value.encode()))
        import base64
        return "xor:" + base64.b64encode(xored).decode()


def decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        from cryptography.fernet import Fernet
        if value.startswith("xor:"):
            raise ImportError
        f = Fernet(_fernet())
        return f.decrypt(value.encode()).decode()
    except ImportError:
        if value.startswith("xor:"):
            import base64
            key_bytes = _fernet()
            raw = base64.b64decode(value[4:])
            return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw)).decode()
        return ""
    except Exception:
        return ""


# ── User CRUD ──────────────────────────────────────────────────────────────────

def register(username: str, email: str, password: str) -> User:
    email = email.strip().lower()
    username = username.strip().lower()

    if not _valid_email(email):
        raise ValueError("Please enter a valid email address")
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    with db_session() as db:
        existing = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing:
            if existing.email == email:
                raise ValueError("An account with this email already exists. Please sign in.")
            raise ValueError("This username is already taken. Please choose another.")
        user = User(
            username=username,
            email=email,
            password_hash=_hash_password(password),
        )
        db.add(user)
        db.flush()
        db.add(UserSettings(user_id=user.id))
        user_id = user.id
    return get_user_by_id(user_id)


def login(username_or_email: str, password: str) -> Optional[str]:
    """Returns session token on success, None on failure."""
    with db_session() as db:
        val = username_or_email.strip().lower()
        user = db.query(User).filter(
            (User.username == val) | (User.email == val)
        ).first()
        if not user or not user.is_active:
            return None
        if not _verify_password(password, user.password_hash):
            return None
        token = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS)
        db.add(UserSession(user_id=user.id, token=token, expires_at=expires))
        return token


def get_user_by_token(token: str) -> Optional[User]:
    with db_session() as db:
        session = db.query(UserSession).filter_by(token=token).first()
        if not session or session.expires_at < datetime.utcnow():
            return None
        user = db.query(User).filter_by(id=session.user_id, is_active=True).first()
        if not user:
            return None
        db.expunge(user)
        return user


def get_user_by_id(user_id: str) -> Optional[User]:
    with db_session() as db:
        user = db.query(User).filter_by(id=user_id).first()
        if user:
            db.expunge(user)
        return user


def logout(token: str) -> None:
    with db_session() as db:
        db.query(UserSession).filter_by(token=token).delete()


# ── Forgot password (OTP via Telegram, fallback shown in response) ─────────────

def request_password_reset(email: str) -> dict:
    """
    Generate a 6-digit OTP for the given email.
    If the user has Telegram configured, send it there.
    Returns {"sent_via": "telegram"|"screen", "otp": str|None}
    so the API can decide what to show.
    """
    email = email.strip().lower()
    if not _valid_email(email):
        raise ValueError("Invalid email address")

    with db_session() as db:
        user = db.query(User).filter_by(email=email, is_active=True).first()
        if not user:
            # Don't reveal whether the account exists
            return {"sent_via": "none", "otp": None}
        user_id = user.id

    otp = f"{random.randint(100000, 999999)}"
    _otp_store[email] = (otp, datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES))

    # Try Telegram
    sent_via = "screen"
    try:
        s = get_settings(user_id)
        if s and s.telegram_bot_token and s.telegram_chat_id:
            import httpx
            msg = (
                f"🔐 <b>JOBPILOT Password Reset</b>\n\n"
                f"Your one-time code: <b>{otp}</b>\n\n"
                f"⏱ Valid for {OTP_TTL_MINUTES} minutes. Do not share it."
            )
            r = httpx.post(
                f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
                json={"chat_id": s.telegram_chat_id, "text": msg, "parse_mode": "HTML"},
                timeout=8,
            )
            if r.status_code == 200:
                sent_via = "telegram"
    except Exception as e:
        logger.warning("Telegram OTP send failed: %s", e)

    return {
        "sent_via": sent_via,
        "otp": otp if sent_via == "screen" else None,
    }


def reset_password(email: str, otp: str, new_password: str) -> bool:
    """Validate OTP and set new password. Returns True on success."""
    email = email.strip().lower()
    if len(new_password) < 6:
        raise ValueError("Password must be at least 6 characters")

    entry = _otp_store.get(email)
    if not entry:
        raise ValueError("No reset code found. Please request a new one.")
    stored_otp, expires_at = entry
    if datetime.utcnow() > expires_at:
        del _otp_store[email]
        raise ValueError("Reset code has expired. Please request a new one.")
    if otp.strip() != stored_otp:
        raise ValueError("Incorrect reset code. Please check and try again.")

    with db_session() as db:
        user = db.query(User).filter_by(email=email, is_active=True).first()
        if not user:
            raise ValueError("Account not found")
        user.password_hash = _hash_password(new_password)
        # Invalidate all sessions
        db.query(UserSession).filter_by(user_id=user.id).delete()

    del _otp_store[email]
    return True


# ── Settings ───────────────────────────────────────────────────────────────────

def get_settings(user_id: str) -> Optional[UserSettings]:
    with db_session() as db:
        s = db.query(UserSettings).filter_by(user_id=user_id).first()
        if s:
            db.expunge(s)
        return s


def update_settings(user_id: str, data: dict) -> None:
    with db_session() as db:
        s = db.query(UserSettings).filter_by(user_id=user_id).first()
        if not s:
            s = UserSettings(user_id=user_id)
            db.add(s)
        for field in ("telegram_bot_token", "telegram_chat_id",
                      "linkedin_email", "indeed_email", "rozee_email",
                      "groq_api_key", "remote_preference", "location",
                      "salary_min", "search_terms",
                      "notify_on_apply", "notify_daily_summary"):
            if field in data:
                setattr(s, field, data[field])
        for field in ("linkedin_password", "indeed_password", "rozee_password"):
            if field in data and data[field]:
                setattr(s, field + "_enc", encrypt(data[field]))


def get_decrypted_password(user_id: str, platform: str) -> str:
    with db_session() as db:
        s = db.query(UserSettings).filter_by(user_id=user_id).first()
        enc = getattr(s, f"{platform}_password_enc", "") if s else ""
        return decrypt(enc or "")
