"""
Telegram notification service.
Sends messages to the configured chat ID via Bot API (no webhook needed).
"""
from __future__ import annotations

import httpx

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def _enabled() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def send(message: str, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message. Returns True on success."""
    if not _enabled():
        logger.debug("Telegram not configured — skipping notification")
        return False
    try:
        url = _BASE.format(token=settings.TELEGRAM_BOT_TOKEN)
        resp = httpx.post(
            url,
            json={
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("Telegram notification sent")
            return True
        logger.warning("Telegram API error: %s", resp.text)
        return False
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


def notify_applied(job_title: str, company: str, source: str, score: int, url: str) -> None:
    msg = (
        f"✅ <b>Applied!</b>\n\n"
        f"🏢 <b>{company}</b>\n"
        f"💼 {job_title}\n"
        f"🎯 Match: <b>{score}%</b>\n"
        f"🌐 Source: {source}\n"
        f"🔗 <a href='{url}'>View Job</a>"
    )
    send(msg)


def notify_pipeline_done(total: int, applied: int, high: int) -> None:
    msg = (
        f"🤖 <b>Daily Job Search Complete</b>\n\n"
        f"📊 Jobs found: <b>{total}</b>\n"
        f"✅ Applications sent: <b>{applied}</b>\n"
        f"⭐ High matches (90%+): <b>{high}</b>"
    )
    send(msg)


def notify_error(context: str, error: str) -> None:
    msg = f"⚠️ <b>JOBPILOT Error</b>\n\n<code>{context}</code>\n{error[:300]}"
    send(msg)


def test_connection() -> bool:
    """Send a test message to verify bot token and chat ID are correct."""
    return send("🤖 <b>JOBPILOT connected!</b> Notifications are working.")
