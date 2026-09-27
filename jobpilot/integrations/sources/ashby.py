"""
Ashby ATS Source Ingestor

Retrieves structured public job listings directly from Ashby company boards.
This is where most of the AI companies moved after leaving Greenhouse/Lever
(OpenAI, Cursor, ElevenLabs, Runway, Replit, Supabase, Railway, ...).

API: https://api.ashbyhq.com/posting-api/job-board/{company}
"""
from __future__ import annotations

import requests
from typing import Any, Dict, List
from ...core.logging import get_logger
from ...core.schemas import RawJob
from .base import JobSourceAdapter

logger = get_logger("sources.ats_ashby")

# Live-verified 2026-09-27: HTTP 200 with jobs. Add new boards only after
# verifying `GET https://api.ashbyhq.com/posting-api/job-board/{token}` -> 200.
TARGET_COMPANIES = [
    "openai", "cursor", "elevenlabs", "runway", "replit",
    "supabase", "railway", "cohere", "perplexity", "modal",
    "resend", "clerk", "synthesia", "n8n",
]

# Keep Ashby yield relevant to the candidate's target roles instead of
# flooding the pipeline with every open req (OpenAI alone lists 800+).
_TECH_TITLE_KEYWORDS = [
    "ai", "ml", "llm", "rag", "genai", "nlp", "prompt",
    "python", "backend", "full stack", "full-stack", "fullstack",
    "software engineer", "developer", "data", "node", "react",
    "fastapi", "django", "mlops", "machine learning",
]


class AshbyATSAdapter(JobSourceAdapter):
    """
    Direct ATS Ingestor for Ashby company boards.
    API URL: https://api.ashbyhq.com/posting-api/job-board/{company}
    """
    source_name = "ats_ashby"
    rate_limit_delay = 1.0

    def fetch_company_jobs(self, company_board_token: str) -> List[RawJob]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company_board_token}"
        jobs: List[RawJob] = []

        try:
            res = requests.get(url, timeout=15)
            if res.status_code != 200:
                # Loud failure — a dead/renamed board must never fail silently.
                logger.error(
                    "[Ashby ATS] Board '%s' returned HTTP %d — "
                    "token may be dead; remove it from TARGET_COMPANIES",
                    company_board_token, res.status_code,
                )
                return []

            data = res.json()
            raw_list = data.get("jobs", []) if isinstance(data, dict) else []

            for item in raw_list:
                title = str(item.get("title", ""))
                if not any(kw in title.lower() for kw in _TECH_TITLE_KEYWORDS):
                    continue
                job_url = str(item.get("jobUrl", ""))
                if not job_url:
                    continue
                loc = str(item.get("locationName", "") or ("Remote" if item.get("isRemote") else ""))
                desc = str(item.get("descriptionPlain", ""))
                jobs.append(RawJob(
                    title=title,
                    company=data.get("name", company_board_token).title() if isinstance(data, dict) else company_board_token.title(),
                    location=loc or "Remote",
                    description=desc,
                    application_url=job_url,
                    source=f"Ashby ATS ({company_board_token})",
                    source_job_id=str(item.get("id", "")),
                    posting_date=item.get("publishedAt"),
                    salary_raw=str(item.get("compensationTierSummary", "") or "") or None,
                    remote_type="remote" if item.get("isRemote") else "unknown",
                ))
            logger.info("[Ashby ATS] Fetched %d tech jobs from '%s'", len(jobs), company_board_token)
        except Exception as exc:
            logger.error("[Ashby ATS] Error fetching board '%s': %s", company_board_token, exc)
            raise

        return jobs

    def fetch(self) -> List[RawJob]:
        import concurrent.futures
        all_jobs: List[RawJob] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(self.fetch_company_jobs, company) for company in TARGET_COMPANIES]
            for f in concurrent.futures.as_completed(futures):
                try:
                    all_jobs.extend(f.result())
                except Exception as exc:
                    logger.error("[Ashby ATS] Board fetch raised: %s", exc)
        return all_jobs
