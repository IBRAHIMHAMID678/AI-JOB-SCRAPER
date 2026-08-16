"""
Auth service — register, login, session management.
Passwords hashed with bcrypt. Sessions stored in DB with expiry.
Credentials encrypted with Fernet (AES-128).
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from ..core.database import db_session
from ..core.models import User, UserSession, UserSettings
from ..core.logging import get_logger

logger = get_logger(__name__)

SESSION_TTL_DAYS = 30


# ── Password hashing (bcrypt via hashlib fallback) ─────────────────────────────

def _hash_password(password: str) -> str:
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"sha256:{salt}:{h}"


def _verify_password(password: str, hashed: str) -> bool:
    try:
        import bcrypt
        if hashed.startswith("sha256:"):
            raise ImportError
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ImportError:
        if hashed.startswith("sha256:"):
            _, salt, h = hashed.split(":", 2)
            return hashlib.sha256((salt + password).encode()).hexdigest() == h
        return False


# ── Credential encryption ──────────────────────────────────────────────────────

def _fernet():
    key = os.environ.get("SECRET_KEY", "change-me-in-production-use-a-long-random-string")
    # Derive a 32-byte Fernet key from SECRET_KEY
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
        # fallback: simple XOR obfuscation (not secure, but better than plaintext)
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
    with db_session() as db:
        if db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first():
            raise ValueError("Username or email already taken")
        user = User(
            username=username.strip().lower(),
            email=email.strip().lower(),
            password_hash=_hash_password(password),
        )
        db.add(user)
        db.flush()
        # Create default empty settings
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
        # detach from session to return
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
        # Plain fields
        for field in ("telegram_bot_token", "telegram_chat_id",
                      "linkedin_email", "indeed_email", "rozee_email",
                      "groq_api_key", "remote_preference", "location",
                      "salary_min", "search_terms",
                      "notify_on_apply", "notify_daily_summary"):
            if field in data:
                setattr(s, field, data[field])
        # Encrypted password fields
        for field in ("linkedin_password", "indeed_password", "rozee_password"):
            if field in data and data[field]:
                setattr(s, field + "_enc", encrypt(data[field]))


def get_decrypted_password(user_id: str, platform: str) -> str:
    with db_session() as db:
        s = db.query(UserSettings).filter_by(user_id=user_id).first()
        enc = getattr(s, f"{platform}_password_enc", "") if s else ""
        return decrypt(enc or "")
