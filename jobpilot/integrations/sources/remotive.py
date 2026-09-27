"""Remotive API adapter."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_CATEGORIES = ["software-dev", "data", "devops-sysadmin"]
_BASE = "https://remotive.com/api/remote-jobs"


class RemotiveAdapter(JobSourceAdapter):
    source_name = "remotive"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        failed_cats = 0
        for cat in _CATEGORIES:
            try:
                # The API ignores limit/offset beyond what it has (~18 per
                # category); request a generous cap so we never slice results.
                resp = requests.get(_BASE, params={"category": cat, "limit": 100}, timeout=self.timeout)
                resp.raise_for_status()
                for j in resp.json().get("jobs", []):
                    url = j.get("url", "")
                    if not url:
                        continue
                    jobs.append(RawJob(
                        title=j.get("title", ""),
                        company=j.get("company_name", ""),
                        location=j.get("candidate_required_location", "Worldwide"),
                        description=j.get("description", ""),
                        application_url=url,
                        source="Remotive",
                        posting_date=j.get("publication_date"),
                        salary_raw=j.get("salary", None),
                        remote_type="remote",
                        skills_raw=j.get("tags", []) or [],
                    ))
            except Exception as exc:
                # Loud per-category failure; keep other categories. If every
                # category failed, raise so get_jobs() retries with backoff.
                failed_cats += 1
                self.logger.error("Remotive error for category '%s': %s", cat, exc)
        if not jobs and failed_cats == len(_CATEGORIES):
            raise RuntimeError(f"Remotive: all {len(_CATEGORIES)} category requests failed")
        return jobs
