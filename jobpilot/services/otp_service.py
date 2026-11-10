"""
Secure OTP and Gmail SMTP Service.
Handles cryptographically secure 6-digit OTP generation, database-backed verification,
rate limiting, brute-force defense, and TLS SMTP delivery via Gmail.
"""
from __future__ import annotations

import email.message
import hashlib
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from typing import Optional, Tuple

from ..core.config import settings
from ..core.database import db_session
from ..core.logging import get_logger
from ..core.models import OTPVerification, User, UserSession, UserSettings, CandidateProfile

logger = get_logger(__name__)

OTP_TTL_MINUTES = 10
RESEND_COOLDOWN_SECONDS = 60
MAX_VERIFY_ATTEMPTS = 3
MAX_HOURLY_REQUESTS = 5

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _is_valid_email(email_str: str) -> bool:
    return bool(EMAIL_RE.match((email_str or "").strip()))


def _hash_otp(otp: str, email_str: str) -> str:
    """Hashed representation of OTP salted with email and server secret."""
    salt = settings.SECRET_KEY[:16]
    return hashlib.sha256(f"{salt}:{email_str.lower().strip()}:{otp.strip()}".encode()).hexdigest()


def _get_smtp_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Retrieves SMTP user and password securely from env."""
    user = os.environ.get("SMTP_USER") or settings.SMTP_USER
    password = os.environ.get("SMTP_PASSWORD") or os.environ.get("SMTP_PASS") or settings.SMTP_PASSWORD or settings.SMTP_PASS
    return user, password


def send_smtp_email(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    """
    Delivers an email using Gmail SMTP (smtp.gmail.com:587) with TLS encryption.
    If credentials are not yet supplied, logs securely in dev mode so workflows never crash.
    """
    smtp_user, smtp_pass = _get_smtp_credentials()
    host = os.environ.get("SMTP_HOST") or settings.SMTP_HOST or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or settings.SMTP_PORT or 587)
    from_email = os.environ.get("SMTP_FROM_EMAIL") or settings.SMTP_FROM_EMAIL or smtp_user or "noreply@jobportal.local"
    from_name = settings.SMTP_FROM_NAME or "JobPortal Security"

    if not smtp_user or not smtp_pass:
        logger.info(
            "[SMTP:SIMULATED] SMTP credentials not fully configured in .env. "
            "Simulating delivery to %s. Subject: %s",
            to_email, subject
        )
        return True

    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=12) as server:
            if settings.SMTP_USE_TLS:
                server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info("[SMTP] Verification email dispatched successfully to %s", to_email)
        return True
    except smtplib.SMTPAuthenticationError as auth_err:
        logger.error(
            "[SMTP] Gmail Authentication failed (%s). "
            "Ensure 2FA is enabled and a 16-character Google App Password is used in SMTP_PASSWORD.",
            auth_err
        )
        raise RuntimeError("Email authentication failed. Please verify Gmail App Password configuration.")
    except Exception as exc:
        logger.error("[SMTP] Failed to send email to %s: %s", to_email, exc)
        raise RuntimeError(f"Could not send email via SMTP: {exc}")


def _build_otp_email_html(otp: str, purpose_text: str, ttl_minutes: int) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #0f172a; }}
        .card {{ max-width: 540px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 36px; box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.05); }}
        .badge {{ display: inline-block; background: #eff6ff; color: #1d4ed8; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 4px 10px; border-radius: 9999px; margin-bottom: 16px; }}
        h1 {{ font-size: 22px; font-weight: 800; margin: 0 0 12px 0; color: #0f172a; letter-spacing: -0.02em; }}
        p {{ font-size: 14px; line-height: 1.6; color: #475569; margin: 0 0 20px 0; }}
        .otp-box {{ background: #f1f5f9; border: 2px dashed #cbd5e1; border-radius: 8px; text-align: center; padding: 20px; margin: 24px 0; font-family: 'Courier New', Courier, monospace; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #1d4ed8; }}
        .footer {{ font-size: 12px; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 16px; margin-top: 24px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="badge">JobPortal Security</div>
        <h1>{purpose_text}</h1>
        <p>Please use the following 6-digit one-time verification code to complete your request. This code will expire in <strong>{ttl_minutes} minutes</strong>.</p>
        <div class="otp-box">{otp}</div>
        <p>If you did not request this code, you can safely ignore this email. Never share this code with anyone.</p>
        <div class="footer">
          &copy; JobPortal autonomous matching platform. Confidential & automated.
        </div>
      </div>
    </body>
    </html>
    """


def send_registration_otp(email_str: str, username: str, password_hash: str) -> dict:
    """
    Generates and dispatches a registration verification OTP.
    Stores the pending credentials in the database until verified.
    """
    clean_email = email_str.strip().lower()
    clean_username = username.strip().lower()

    if not _is_valid_email(clean_email):
        raise ValueError("Please provide a valid email address.")
    if len(clean_username) < 3:
        raise ValueError("Username must be at least 3 characters.")

    with db_session() as db:
        existing = db.query(User).filter(
            (User.username == clean_username) | (User.email == clean_email)
        ).first()
        if existing:
            if existing.email == clean_email:
                raise ValueError("An account with this email already exists. Please sign in.")
            raise ValueError("This username is already taken. Please choose another.")

        now = datetime.utcnow()
        # Check hourly rate limit
        one_hour_ago = now - timedelta(hours=1)
        recent_requests = db.query(OTPVerification).filter(
            OTPVerification.email == clean_email,
            OTPVerification.created_at >= one_hour_ago
        ).count()
        if recent_requests >= MAX_HOURLY_REQUESTS:
            raise ValueError("Too many verification attempts. Please wait 1 hour before requesting again.")

        # Check resend cooldown
        last_otp = db.query(OTPVerification).filter_by(
            email=clean_email, purpose="registration"
        ).order_by(OTPVerification.created_at.desc()).first()

        if last_otp and (now - last_otp.last_sent_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
            remaining = int(RESEND_COOLDOWN_SECONDS - (now - last_otp.last_sent_at).total_seconds())
            raise ValueError(f"Please wait {remaining} seconds before requesting a new code.")

        # Generate 6-digit cryptographic OTP
        otp = f"{secrets.randbelow(900000) + 100000}"
        otp_hash = _hash_otp(otp, clean_email)
        expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

        verification = OTPVerification(
            email=clean_email,
            otp_hash=otp_hash,
            purpose="registration",
            metadata_json={"username": clean_username, "password_hash": password_hash},
            expires_at=expires_at,
            last_sent_at=now,
        )
        db.add(verification)
        db.commit()

    # Dispatch email
    html_body = _build_otp_email_html(otp, "Verify Your JobPortal Account", OTP_TTL_MINUTES)
    text_body = f"Your JobPortal registration verification code is: {otp}. Valid for {OTP_TTL_MINUTES} minutes."
    send_smtp_email(clean_email, f"JobPortal Verification Code: {otp}", html_body, text_body)

    smtp_user, smtp_pass = _get_smtp_credentials()
    is_live = bool(smtp_user and smtp_pass)

    return {
        "status": "otp_sent",
        "email": clean_email,
        "expires_in_seconds": OTP_TTL_MINUTES * 60,
        "cooldown_seconds": RESEND_COOLDOWN_SECONDS,
        "smtp_live": is_live,
        "dev_code": otp if not is_live else None,  # Provided in dev mode only when SMTP not configured
    }


def verify_registration_otp(email_str: str, otp: str) -> dict:
    """
    Verifies the registration OTP and creates the authenticated user account.
    """
    clean_email = email_str.strip().lower()
    clean_otp = (otp or "").strip()

    if not clean_otp or len(clean_otp) != 6:
        raise ValueError("Please enter a valid 6-digit verification code.")

    with db_session() as db:
        record = db.query(OTPVerification).filter(
            OTPVerification.email == clean_email,
            OTPVerification.purpose == "registration",
            OTPVerification.verified_at == None,
        ).order_by(OTPVerification.created_at.desc()).first()

        if not record:
            raise ValueError("No active verification request found. Please request a new code.")

        now = datetime.utcnow()
        if now > record.expires_at:
            raise ValueError("The verification code has expired. Please request a new one.")

        if record.attempts >= MAX_VERIFY_ATTEMPTS:
            raise ValueError("Too many incorrect attempts. Please request a new code.")

        expected_hash = _hash_otp(clean_otp, clean_email)
        if record.otp_hash != expected_hash:
            record.attempts += 1
            db.commit()
            remaining = MAX_VERIFY_ATTEMPTS - record.attempts
            if remaining <= 0:
                raise ValueError("Too many incorrect attempts. Code invalidated. Please request a new one.")
            raise ValueError(f"Incorrect code. {remaining} attempt(s) remaining.")

        # Mark OTP as consumed
        record.verified_at = now

        # Create user account
        meta = record.metadata_json or {}
        username = meta.get("username")
        password_hash = meta.get("password_hash")

        if not username or not password_hash:
            raise ValueError("Corrupted registration state. Please register again.")

        existing_user = db.query(User).filter_by(email=clean_email).first()
        if existing_user:
            user = existing_user
        else:
            user = User(
                username=username,
                email=clean_email,
                password_hash=password_hash,
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            db.flush()
            db.add(UserSettings(user_id=user.id))
            db.add(CandidateProfile(
                id=user.id,
                name=username.capitalize(),
                email=clean_email,
                location="Worldwide Remote",
                skills=["Python", "FastAPI", "React"],
                preferred_roles=["Software Engineer"],
            ))

        # Generate session token
        session_token = secrets.token_urlsafe(48)
        expires = datetime.utcnow() + timedelta(days=30)
        db.add(UserSession(user_id=user.id, token=session_token, expires_at=expires))
        db.commit()

        return {
            "token": session_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_verified": True,
            }
        }


def send_password_reset_otp(email_str: str) -> dict:
    """Dispatches a password reset OTP to user's email."""
    clean_email = email_str.strip().lower()
    if not _is_valid_email(clean_email):
        raise ValueError("Please enter a valid email address.")

    with db_session() as db:
        user = db.query(User).filter_by(email=clean_email, is_active=True).first()
        if not user:
            # Don't reveal account presence
            return {"status": "otp_sent", "email": clean_email}

        now = datetime.utcnow()
        otp = f"{secrets.randbelow(900000) + 100000}"
        otp_hash = _hash_otp(otp, clean_email)
        expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

        verification = OTPVerification(
            email=clean_email,
            otp_hash=otp_hash,
            purpose="password_reset",
            metadata_json={"user_id": user.id},
            expires_at=expires_at,
            last_sent_at=now,
        )
        db.add(verification)
        db.commit()

    html_body = _build_otp_email_html(otp, "Reset Your JobPortal Password", OTP_TTL_MINUTES)
    text_body = f"Your JobPortal password reset code is: {otp}. Valid for {OTP_TTL_MINUTES} minutes."
    send_smtp_email(clean_email, f"JobPortal Password Reset Code: {otp}", html_body, text_body)

    smtp_user, smtp_pass = _get_smtp_credentials()
    is_live = bool(smtp_user and smtp_pass)

    return {
        "status": "otp_sent",
        "email": clean_email,
        "expires_in_seconds": OTP_TTL_MINUTES * 60,
        "smtp_live": is_live,
        "dev_code": otp if not is_live else None,
    }


def verify_password_reset_otp(email_str: str, otp: str, new_password_hash: str) -> bool:
    """Verifies password reset OTP and updates user password."""
    clean_email = email_str.strip().lower()
    clean_otp = (otp or "").strip()

    if not clean_otp or len(clean_otp) != 6:
        raise ValueError("Invalid verification code.")

    with db_session() as db:
        record = db.query(OTPVerification).filter(
            OTPVerification.email == clean_email,
            OTPVerification.purpose == "password_reset",
            OTPVerification.verified_at == None,
        ).order_by(OTPVerification.created_at.desc()).first()

        if not record or datetime.utcnow() > record.expires_at:
            raise ValueError("Verification code has expired or does not exist.")

        if record.attempts >= MAX_VERIFY_ATTEMPTS:
            raise ValueError("Maximum verification attempts exceeded.")

        if record.otp_hash != _hash_otp(clean_otp, clean_email):
            record.attempts += 1
            db.commit()
            raise ValueError("Incorrect code.")

        record.verified_at = datetime.utcnow()
        user = db.query(User).filter_by(email=clean_email, is_active=True).first()
        if not user:
            raise ValueError("User not found.")

        user.password_hash = new_password_hash
        # Invalidate old sessions
        db.query(UserSession).filter_by(user_id=user.id).delete()
        db.commit()
        return True

