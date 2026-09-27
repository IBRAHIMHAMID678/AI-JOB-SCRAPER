"""Himalayas.app API adapter."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List
import requests

from ...core.config import settings
from ...core.schemas import RawJob
from .base import JobSourceAdapter


def _posting_date(value) -> str | None:
    """Himalayas pubDate is a Unix timestamp (int); RawJob needs a string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return str(value) if value else None


class HimalayasAdapter(JobSourceAdapter):
    source_name = "himalayas"
    BASE_URL = "https://himalayas.app/jobs/api"
    # The API always returns a nextCursor (it never terminates on its own),
    # so cursor pagination MUST be page-capped or the run hangs forever.
    MAX_PAGES_PER_TERM = 4

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        failed_terms = 0
        terms = settings.SEARCH_TERMS[:4]  # limit to avoid hammering
        for term in terms:
            try:
                # Paginate via the API's nextCursor, bounded per term.
                cursor = None
                seen_cursors = set()
                for _page in range(self.MAX_PAGES_PER_TERM):
                    params = {"q": term, "limit": settings.RESULTS_PER_TERM}
                    if cursor:
                        params["cursor"] = cursor
                    resp = requests.get(
                        self.BASE_URL,
                        params=params,
                        timeout=self.timeout,
                        headers={"User-Agent": "JOBPILOT/1.0"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    page_jobs = data.get("jobs", [])
                    if not page_jobs:
                        break
                    for j in page_jobs:
                        url = j.get("applicationLink") or j.get("url") or ""
                        if not url:
                            continue
                        locs = j.get("locationRestrictions") or []
                        jobs.append(RawJob(
                            title=j.get("title", ""),
                            company=j.get("companyName", "") or "",
                            location=locs[0] if locs else "Remote",
                            description=j.get("description", ""),
                            application_url=url,
                            source="Himalayas",
                            remote_type="remote",
                            posting_date=_posting_date(j.get("pubDate")),
                        ))
                    cursor = data.get("nextCursor")
                    if not cursor or cursor in seen_cursors:
                        break
                    seen_cursors.add(cursor)
            except Exception as exc:
                # Loud per-term failure; keep other terms. If every term failed,
                # raise so get_jobs() retries the whole source with backoff.
                failed_terms += 1
                self.logger.error("Himalayas fetch error for '%s': %s", term, exc)
        if not jobs and failed_terms == len(terms):
            raise RuntimeError(f"Himalayas: all {len(terms)} term requests failed")
        return jobs
