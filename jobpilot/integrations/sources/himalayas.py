"""Himalayas.app API adapter."""
from __future__ import annotations

from typing import List
import requests

from ...core.config import settings
from ...core.schemas import RawJob
from .base import JobSourceAdapter


class HimalayasAdapter(JobSourceAdapter):
    source_name = "himalayas"
    BASE_URL = "https://himalayas.app/jobs/api"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        for term in settings.SEARCH_TERMS[:4]:  # limit to avoid hammering
            try:
                resp = requests.get(
                    self.BASE_URL,
                    params={"q": term, "limit": settings.RESULTS_PER_TERM},
                    timeout=self.timeout,
                    headers={"User-Agent": "JOBPILOT/1.0"},
                )
                resp.raise_for_status()
                data = resp.json()
                for j in data.get("jobs", []):
                    url = j.get("applicationLink") or j.get("url") or ""
                    if not url:
                        continue
                    try:
                        jobs.append(RawJob(
                            title=j.get("title", ""),
                            company=j.get("company", {}).get("name", "") if isinstance(j.get("company"), dict) else str(j.get("company", "")),
                            location=j.get("locationRestrictions", ["Remote"])[0] if j.get("locationRestrictions") else "Remote",
                            description=j.get("description", ""),
                            application_url=url,
                            source="Himalayas",
                            remote_type="remote",
                            skills_raw=j.get("requiredSkills", []) or [],
                        ))
                    except Exception:
                        pass
            except Exception as exc:
                self.logger.warning("Himalayas fetch error for '%s': %s", term, exc)
        return jobs
