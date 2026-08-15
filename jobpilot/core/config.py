"""
Central configuration for JOBPILOT.
All settings come from environment variables; nothing is hard-coded.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "JOBPILOT"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALLOWED_HOSTS: List[str] = ["*"]

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./jobpilot.db"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_ECHO: bool = False

    # ── Redis / Queue ─────────────────────────────────────────────────────────
    REDIS_URL: Optional[str] = None          # None → in-memory fallback
    QUEUE_MAX_WORKERS: int = 10

    # ── MongoDB (legacy fallback) ─────────────────────────────────────────────
    MONGO_URI: Optional[str] = None
    MONGO_DB_NAME: str = "job_scraper_db"

    # ── LLM ──────────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "groq"               # groq | openrouter | openai
    LLM_MODEL: str = "llama3-8b-8192"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 2048
    LLM_TIMEOUT: int = 30
    LLM_MAX_RETRIES: int = 3

    GROQ_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "google/gemini-2.5-flash"

    # ── Scraping ──────────────────────────────────────────────────────────────
    SEARCH_TERMS: List[str] = [
        "AI Engineer",
        "AI Full Stack Developer",
        "Python AI Developer",
        "LLM Engineer",
        "Full Stack Developer",
        "Software Engineer",
        "React Developer",
        "FastAPI Developer",
    ]
    RESULTS_PER_TERM: int = 15
    SCRAPE_INTERVAL_HOURS: int = 6
    SCRAPER_RATE_LIMIT_DELAY: float = 1.0
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_TIMEOUT: int = 30

    # ── Job Scoring Thresholds ────────────────────────────────────────────────
    SCORE_HIGH_PRIORITY: int = 90
    SCORE_GOOD_MATCH: int = 75
    SCORE_POSSIBLE_MATCH: int = 60
    SCORE_AUTO_APPROVE: int = 40
    SCORE_MIN_THRESHOLD: int = 30

    # ── Application Settings ──────────────────────────────────────────────────
    APPLICATION_MODE: str = "manual"         # manual | approval | controlled
    AUTO_APPLICATION_ENABLED: bool = False
    REQUIRE_APPROVAL: bool = True
    MAX_APPLICATIONS_PER_DAY: int = 10
    MAX_APPLICATIONS_PER_SOURCE: int = 3

    # ── Email ─────────────────────────────────────────────────────────────────
    EMAIL_SCAN_INTERVAL_MINUTES: int = 15
    EMAIL_OAUTH_CLIENT_ID: Optional[str] = None
    EMAIL_OAUTH_CLIENT_SECRET: Optional[str] = None
    EMAIL_OAUTH_REDIRECT_URI: str = "http://localhost:8000/api/email/callback"
    EMAIL_PROVIDER: str = "gmail"            # gmail | outlook

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    WHATSAPP_API_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_TO_NUMBER: Optional[str] = None
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: Optional[str] = None

    # ── Notifications ─────────────────────────────────────────────────────────
    NOTIFY_HIGH_SCORE_JOBS: bool = True
    NOTIFY_APPLICATION_READY: bool = True
    NOTIFY_RECRUITER_RESPONSE: bool = True
    NOTIFY_INTERVIEW: bool = True
    NOTIFY_DAILY_SUMMARY: bool = True

    # ── Follow-up ─────────────────────────────────────────────────────────────
    FOLLOWUP_DELAY_DAYS: int = 7
    FOLLOWUP_MAX_PER_APPLICATION: int = 2

    # ── Candidate Profile ─────────────────────────────────────────────────────
    CANDIDATE_NAME: str = "Hamza Ahsin"
    CANDIDATE_EMAIL: str = "hamzaahsin786@gmail.com"
    CANDIDATE_LOCATION: str = "Islamabad, Pakistan"
    CANDIDATE_TIMEZONE: str = "Asia/Karachi"
    CANDIDATE_WORK_AUTHORIZATION: str = "Pakistan"
    CANDIDATE_REMOTE_PREFERENCE: str = "worldwide_remote"

    # ── Observability ─────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"                 # json | text
    EVAL_CACHE_FILE: str = "eval_cache.json"

    # ── Data Retention ───────────────────────────────────────────────────────
    AUDIT_LOG_RETENTION_DAYS: int = 90
    JOB_RETENTION_DAYS: int = 180

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @field_validator("APPLICATION_MODE")
    @classmethod
    def validate_app_mode(cls, v: str) -> str:
        allowed = {"manual", "approval", "controlled"}
        if v not in allowed:
            raise ValueError(f"APPLICATION_MODE must be one of {allowed}")
        return v

    def get_score_label(self, score: int) -> str:
        if score >= self.SCORE_HIGH_PRIORITY:
            return "HIGH_PRIORITY"
        if score >= self.SCORE_GOOD_MATCH:
            return "GOOD_MATCH"
        if score >= self.SCORE_POSSIBLE_MATCH:
            return "POSSIBLE_MATCH"
        return "LOW_PRIORITY"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
