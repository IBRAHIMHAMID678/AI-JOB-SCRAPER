"""
Greenhouse ATS Source Ingestor

Retrieves structured public job listings directly from Greenhouse company boards
without scraping raw HTML.
"""
from __future__ import annotations

import requests
from typing import Any, Dict, List, Optional
from ...core.logging import get_logger
from ...core.schemas import RawJob
from .base import JobSourceAdapter

logger = get_logger("sources.ats_greenhouse")


class GreenhouseATSAdapter(JobSourceAdapter):
    """
    Direct ATS Ingestor for Greenhouse company boards.
    Target companies: Vercel, Zapier, Automattic, Canonical, GitLab, OpenAI, Anthropic, Stripe, Figma.
    """
    source_name = "ats_greenhouse"
    rate_limit_delay = 1.0

    TARGET_COMPANIES = [
        # Live-verified 2026-09-27 (HTTP 200 with jobs). Dead boards were
        # removed: openai, cursor, mistral, elevenlabs, runway, deepgram,
        # baseten, octoai, qdrant, huggingface, groq, cohere, pinecone,
        # weaviate, scale, perplexity, postman, hashicorp, automattic,
        # zapier, sourcegraph, writer, retool, together (all 404; the AI
        # companies moved to Ashby — see integrations/sources/ashby.py).
        "vercel", "canonical", "gitlab", "stripe", "figma",
        "datadog", "brex", "gusto", "reddit",
        "discord", "instacart", "affirm", "elastic", "cockroachlabs",
        "remote", "anthropic",
    ]

    def fetch_company_jobs(self, company_board_token: str) -> List[RawJob]:
        """
        Fetches structured jobs JSON from Greenhouse public API endpoint.
        API URL: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
        """
        url = f"https://boards-api.greenhouse.io/v1/boards/{company_board_token}/jobs?content=true"
        jobs: List[RawJob] = []

        try:
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                # Loud failure — a dead/renamed board must never fail silently.
                logger.error(
                    "[Greenhouse ATS] Board '%s' returned HTTP %d — "
                    "token may be dead; remove it from TARGET_COMPANIES",
                    company_board_token, res.status_code,
                )
                return []

            data = res.json()
            raw_list = data.get("jobs", [])

            for item in raw_list:
                title = str(item.get("title", ""))
                job_url = str(item.get("absolute_url", ""))
                loc = str(item.get("location", {}).get("name", "Remote"))
                desc = str(item.get("content", ""))

                if job_url:
                    jobs.append(RawJob(
                        title=title,
                        company=company_board_token.capitalize(),
                        location=loc,
                        description=desc,
                        application_url=job_url,
                        source=f"Greenhouse ATS ({company_board_token})",
                        source_job_id=str(item.get("id", "")),
                        posting_date=item.get("updated_at"),
                    ))
            logger.info("[Greenhouse ATS] Fetched %d structured jobs from '%s'", len(jobs), company_board_token)
        except Exception as exc:
            logger.error("[Greenhouse ATS] Error fetching board '%s': %s", company_board_token, exc)
            raise

        return jobs

    def fetch(self) -> List[RawJob]:
        import concurrent.futures
        all_jobs: List[RawJob] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            futures = [ex.submit(self.fetch_company_jobs, company) for company in self.TARGET_COMPANIES]
            for f in concurrent.futures.as_completed(futures):
                try:
                    all_jobs.extend(f.result())
                except Exception as exc:
                    logger.error("[Greenhouse ATS] Board fetch raised: %s", exc)
        return all_jobs
