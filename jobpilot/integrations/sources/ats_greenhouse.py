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
        "vercel", "canonical", "gitlab", "stripe", "figma",
        "datadog", "postman", "brex", "gusto", "reddit",
        "discord", "instacart", "affirm", "elastic", "cockroachlabs",
        "hashicorp", "automattic", "zapier", "remote", "sourcegraph",
        "scale", "perplexity", "writer", "retool", "huggingface",
        "cursor", "elevenlabs", "mistral", "together", "runway",
        "deepgram", "baseten", "octoai", "cohere", "pinecone",
        "weaviate", "qdrant", "anthropic", "openai", "groq"
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
            logger.warning("[Greenhouse ATS] Error fetching board '%s': %s", company_board_token, exc)

        return jobs

    def fetch(self) -> List[RawJob]:
        import concurrent.futures
        all_jobs: List[RawJob] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            futures = [ex.submit(self.fetch_company_jobs, company) for company in self.TARGET_COMPANIES]
            for f in concurrent.futures.as_completed(futures):
                try:
                    all_jobs.extend(f.result())
                except Exception:
                    pass
        return all_jobs
