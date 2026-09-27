"""
Lever ATS Source Ingestor

Retrieves structured public job listings directly from Lever API board endpoints.
"""
from __future__ import annotations

import requests
from typing import Any, Dict, List, Optional
from ...core.logging import get_logger
from ...core.schemas import RawJob
from .base import JobSourceAdapter

logger = get_logger("sources.ats_lever")


class LeverATSAdapter(JobSourceAdapter):
    """
    Direct ATS Ingestor for Lever company boards.
    API URL: https://api.lever.co/v0/postings/{company}?mode=json
    """
    source_name = "ats_lever"
    rate_limit_delay = 1.0

    TARGET_COMPANIES = [
        # Live-verified 2026-09-27 (HTTP 200 with jobs). Dead boards removed:
        # netflix, shopify, coursera, docker, airtable, dbtlabs, n8n, replit,
        # supabase, postman, synthesia, modal, resend, railway, convex,
        # prisma, cal, clerk (all 404; most moved to Ashby — see
        # integrations/sources/ashby.py).
        "palantir", "fly",
    ]

    def fetch_company_jobs(self, company_name: str) -> List[RawJob]:
        url = f"https://api.lever.co/v0/postings/{company_name}?mode=json"
        jobs: List[RawJob] = []

        try:
            res = requests.get(url, timeout=15)
            if res.status_code != 200:
                # Loud failure — a dead/renamed board must never fail silently.
                logger.error(
                    "[Lever ATS] Board '%s' returned HTTP %d — "
                    "token may be dead; remove it from TARGET_COMPANIES",
                    company_name, res.status_code,
                )
                return []

            data = res.json()
            if not isinstance(data, list):
                return []

            for item in data:
                title = str(item.get("text", ""))
                hosted_url = str(item.get("hostedUrl", ""))
                loc = str(item.get("categories", {}).get("location", "Remote"))
                desc = str(item.get("descriptionPlain", ""))

                if hosted_url:
                    created_ms = item.get("createdAt")
                    created_iso = None
                    if created_ms:
                        from datetime import datetime, timezone
                        created_iso = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc).isoformat()

                    jobs.append(RawJob(
                        title=title,
                        company=company_name.capitalize(),
                        location=loc,
                        description=desc,
                        application_url=hosted_url,
                        source=f"Lever ATS ({company_name})",
                        source_job_id=str(item.get("id", "")),
                        posting_date=created_iso,
                    ))
            logger.info("[Lever ATS] Fetched %d structured jobs from '%s'", len(jobs), company_name)
        except Exception as exc:
            logger.error("[Lever ATS] Error fetching board '%s': %s", company_name, exc)
            raise

        return jobs

    def fetch(self) -> List[RawJob]:
        import concurrent.futures
        all_jobs: List[RawJob] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(self.fetch_company_jobs, company) for company in self.TARGET_COMPANIES]
            for f in concurrent.futures.as_completed(futures):
                try:
                    all_jobs.extend(f.result())
                except Exception as exc:
                    logger.error("[Lever ATS] Board fetch raised: %s", exc)
        return all_jobs
