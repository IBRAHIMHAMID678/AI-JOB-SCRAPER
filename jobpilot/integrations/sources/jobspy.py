"""
JobSpy adapter — scrapes LinkedIn, Indeed, Glassdoor, ZipRecruiter.
"""
from __future__ import annotations

import concurrent.futures
from typing import List

import pandas as pd

from ...core.config import settings
from ...core.schemas import RawJob
from .base import JobSourceAdapter


class JobSpyAdapter(JobSourceAdapter):
    source_name = "jobspy"
    rate_limit_delay = 0.5

    def fetch(self) -> List[RawJob]:
        from jobspy import scrape_jobs  # lazy import

        jobs: List[RawJob] = []

        def scrape_term(term: str) -> List[RawJob]:
            term_jobs: List[RawJob] = []

            # Global remote
            try:
                df = scrape_jobs(
                    site_name=["linkedin", "indeed"],
                    search_term=term,
                    location="Remote",
                    results_wanted=settings.RESULTS_PER_TERM,
                    hours_old=72,
                    is_remote=True,
                )
                term_jobs.extend(self._df_to_raw(df, "JobSpy-Remote"))
            except Exception as exc:
                self.logger.warning("JobSpy remote scrape failed for '%s': %s", term, exc)

            # Local Pakistan
            try:
                df = scrape_jobs(
                    site_name=["linkedin"],
                    search_term=term,
                    location="Islamabad, Pakistan",
                    results_wanted=settings.RESULTS_PER_TERM,
                    hours_old=72,
                )
                term_jobs.extend(self._df_to_raw(df, "JobSpy-LinkedIn-Local"))
            except Exception as exc:
                self.logger.warning("JobSpy local scrape failed for '%s': %s", term, exc)

            return term_jobs

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(scrape_term, t) for t in settings.SEARCH_TERMS]
            for f in concurrent.futures.as_completed(futures):
                try:
                    jobs.extend(f.result())
                except Exception as exc:
                    self.logger.warning("JobSpy thread error: %s", exc)

        # De-dup within this source
        seen: set = set()
        unique: List[RawJob] = []
        for j in jobs:
            if j.application_url not in seen:
                seen.add(j.application_url)
                unique.append(j)
        return unique

    def _df_to_raw(self, df, source_label: str) -> List[RawJob]:
        results: List[RawJob] = []
        if df is None or df.empty:
            return results
        for _, row in df.iterrows():
            url = str(row.get("job_url", "")).strip()
            if not url or url in ("nan", ""):
                continue
            try:
                salary_raw = None
                if pd.notna(row.get("min_amount")):
                    salary_raw = f"{row.get('min_amount')} - {row.get('max_amount')} {row.get('currency', 'USD')}"
                results.append(RawJob(
                    title=str(row.get("title", "")),
                    company=str(row.get("company", "")),
                    location=str(row.get("location", "Remote")),
                    description=str(row.get("description", "")) if pd.notna(row.get("description")) else None,
                    application_url=url,
                    source=source_label,
                    salary_raw=salary_raw,
                    employment_type=str(row.get("job_type", "")) if pd.notna(row.get("job_type")) else None,
                ))
            except Exception as exc:
                self.logger.debug("Skipping malformed row: %s", exc)
        return results
