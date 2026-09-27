"""The Muse API adapter."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_BASE = "https://www.themuse.com/api/public/jobs"
# Verified 2026-09-27: these exact params return results. Notes:
# - category must be "Software Engineering" (not "Software Engineer")
# - location="Flexible / Remote" is what unlocks the result set
# - pages are 0-indexed; NO "api_key" param (an empty api_key throttles
#   results to ~12) and NO "level" filter ("Entry Level" yields total=0).
_WORKING_CATEGORIES = ["Software Engineering", "Data Science"]
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class TheMuseAdapter(JobSourceAdapter):
    source_name = "themuse"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        failed = 0
        total_pages = 3  # TheMuse paginates via ?page=N (0-indexed)
        requests_made = 0
        for cat in _WORKING_CATEGORIES:
            for page in range(0, total_pages):
                requests_made += 1
                try:
                    resp = requests.get(
                        _BASE,
                        params={
                            "category": cat,
                            "location": "Flexible / Remote",
                            "page": page,
                            "descending": "true",
                        },
                        timeout=self.timeout,
                        headers={"User-Agent": _BROWSER_UA},
                    )
                    resp.raise_for_status()
                    results = resp.json().get("results", [])
                    if not results:
                        break  # no more pages for this category
                    for j in results:
                        refs = j.get("refs", {})
                        url = refs.get("landing_page", "")
                        if not url:
                            continue
                        locs = j.get("locations", [])
                        location = locs[0].get("name", "Remote") if locs else "Remote"
                        jobs.append(RawJob(
                            title=j.get("name", ""),
                            company=j.get("company", {}).get("name", "") if isinstance(j.get("company"), dict) else "",
                            location=location,
                            application_url=url,
                            source="TheMuse",
                            remote_type="remote" if "remote" in location.lower() else "unknown",
                        ))
                except Exception as exc:
                    # Loud per-page failure; keep other pages. If every request
                    # failed, raise so get_jobs() retries with backoff.
                    failed += 1
                    self.logger.error("TheMuse error for '%s' page %d: %s", cat, page, exc)
        if not jobs and failed == requests_made and requests_made:
            raise RuntimeError("TheMuse: all page requests failed")
        return jobs
