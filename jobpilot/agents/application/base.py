"""
Base Application Agent — Playwright Browser & Form Automation

Handles headless Playwright browser instantiation, DOM inspection, form input filling,
CV file attachment, safety checks (CAPTCHAs/2FA), and final QA validation.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from ...core.logging import get_logger
from ...core.fact_checker import fact_check_generated_content
from .router import classify_form_field

logger = get_logger("application.base")


class ApplicationSubmissionResult(BaseModel):
    success: bool = False
    status: str = "FAILED"  # SUBMITTED, WAITING_FOR_INPUT, FAILED, PAUSED
    pause_reason: Optional[str] = None
    confirmation_message: Optional[str] = None
    applied_at: Optional[str] = None
    screenshot_path: Optional[str] = None
    errors: List[str] = []


class BaseApplicationAgent(ABC):
    """
    Abstract Base Class for specialized form application agents.
    """
    agent_type: str = "base"

    def __init__(self) -> None:
        self.logger = get_logger(f"application.{self.agent_type}")

    @abstractmethod
    def apply(
        self,
        job_url: str,
        candidate_profile: Dict[str, Any],
        cv_path: str,
        cover_letter: Optional[str] = None,
        custom_answers: Optional[Dict[str, str]] = None,
    ) -> ApplicationSubmissionResult:
        """Execute form filling and submission."""

    def check_safety_triggers(self, page_content: str, page_obj=None) -> Optional[str]:
        """
        Scans rendered page for active security triggers requiring human intervention.
        Distinguishes between active user-facing challenges and passive script assets.
        """
        if page_obj is not None:
            try:
                body_text = (page_obj.inner_text("body") or "").lower()
                if any(k in body_text for k in ["verify you are human", "complete the captcha", "solve the challenge"]):
                    return "CAPTCHA_DETECTED"
                if any(k in body_text for k in ["two-factor authentication", "enter verification code", "enter your 2fa code"]):
                    return "2FA_REQUIRED"
                # Check for active iframe challenges
                for frame in page_obj.frames:
                    frame_url = (frame.url or "").lower()
                    if any(k in frame_url for k in ["turnstile", "hcaptcha", "recaptcha/api2/anchor"]):
                        return "CAPTCHA_DETECTED"
                return None
            except Exception:
                pass

        # Fallback to scanning HTML text if page object not provided
        import re
        clean_content = re.sub(r"<script.*?</script>", "", page_content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = re.sub(r"<style.*?</style>", "", clean_content, flags=re.DOTALL | re.IGNORECASE).lower()
        
        if any(k in clean_content for k in ["verify you are human", "cf-turnstile", "g-recaptcha-response", "h-captcha-response"]):
            return "CAPTCHA_DETECTED"
        if any(k in clean_content for k in ["two-factor", "verification code"]):
            return "2FA_REQUIRED"
        if any(k in clean_content for k in ["credit card number", "pay to apply", "application fee"]):
            return "SUSPICIOUS_PAYMENT_REQUEST"
        return None
