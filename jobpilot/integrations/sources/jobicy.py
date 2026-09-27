"""Jobicy API adapter (free remote tech/developer jobs)."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_BASE = "https://jobicy.com/api/v2/remote-jobs?count=100&industry=dev"


def _to_float(value) -> float | None:
    """Robust number parse: accepts ints, floats, '$75,000', '75000.50'; rejects junk."""
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", "").strip().lstrip("$").rstrip("/yr/mo/hr")
        return float(cleaned)
    except (TypeError, ValueError):
        return None


class JobicyAdapter(JobSourceAdapter):
    source_name = "jobicy"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        resp = requests.get(_BASE, timeout=12, headers={"User-Agent": "Mozilla/5.0 JOBPILOT/1.0"})
        resp.raise_for_status()
        data = resp.json()
        for j in data.get("jobs", []):
            url = j.get("url", "").strip()
            if not url:
                continue
            # Real salary keys are salaryMin/salaryCurrency/salaryPeriod
            # (the old code read annualSalaryMin, which does not exist).
            # The current API version exposes no salary fields at all —
            # salary_min stays None rather than fabricated.
            salary_min = _to_float(j.get("salaryMin"))
            # jobType is a list like ["Full-Time"] — flatten to a string.
            job_type = j.get("jobType")
            employment_type = ", ".join(str(t) for t in job_type) if isinstance(job_type, list) else (str(job_type) if job_type else None)
            jobs.append(RawJob(
                title=j.get("jobTitle", "").strip(),
                company=j.get("companyName", "").strip(),
                location=j.get("jobGeo", "Worldwide Remote").strip(),
                description=j.get("jobDescription", "") or j.get("jobExcerpt", ""),
                application_url=url,
                source="Jobicy",
                remote_type="remote",
                posting_date=j.get("pubDate"),
                salary_raw=(f"{j.get('salaryMin')} {j.get('salaryCurrency', '')} {j.get('salaryPeriod', '')}".strip()
                            if j.get("salaryMin") else None),
                employment_type=employment_type,
                extra={"salary_min": salary_min} if salary_min is not None else {},
                skills_raw=j.get("jobIndustry") if isinstance(j.get("jobIndustry"), list) else (str(j.get("jobIndustry")).split(",") if j.get("jobIndustry") else []),
            ))
        return jobs
