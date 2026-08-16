"""
Rozee.pk job source adapter.
Uses Rozee's public job listing API/RSS to fetch fresh jobs.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List

import requests

from .base import JobSourceAdapter
from ...core.logging import get_logger

logger = get_logger(__name__)

ROZEE_API = "https://www.rozee.pk/api/jobs/search"
ROZEE_SEARCH = "https://www.rozee.pk/job/jsearch/q/{query}/ft/1"


class RozeeAdapter(JobSourceAdapter):
    source_name = "rozee"

    def fetch(self, search_terms: List[str], max_results: int = 15) -> List[Dict[str, Any]]:
        jobs = []
        for term in search_terms[:4]:  # limit to 4 terms to avoid rate limits
            try:
                results = self._search(term, max_results)
                jobs.extend(results)
                if len(jobs) >= max_results * 2:
                    break
            except Exception as exc:
                logger.warning("Rozee fetch failed for '%s': %s", term, exc)
        return jobs[:max_results * 2]

    def _search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html, */*",
            "Referer": "https://www.rozee.pk/",
        }
        try:
            resp = requests.get(
                ROZEE_API,
                params={"q": query, "limit": limit, "page": 1, "remote": 1},
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "jobs" in data:
                    return [self._normalize(j) for j in data["jobs"] if j]
        except Exception:
            pass

        # fallback: scrape HTML listing page
        return self._scrape_listing(query, limit, headers)

    def _scrape_listing(self, query: str, limit: int, headers: dict) -> List[Dict[str, Any]]:
        from bs4 import BeautifulSoup
        url = f"https://www.rozee.pk/job/jsearch/q/{requests.utils.quote(query)}"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            jobs = []
            for card in soup.select(".job-listing, .jlisting, [data-job-id]")[:limit]:
                try:
                    title_el = card.select_one(".job-title, h2, h3, .title")
                    company_el = card.select_one(".company-name, .company, .org")
                    link_el = card.select_one("a[href*='/job/'], a[href*='rozee']")
                    title = title_el.get_text(strip=True) if title_el else query
                    company = company_el.get_text(strip=True) if company_el else "Unknown"
                    href = link_el["href"] if link_el else ""
                    if not href.startswith("http"):
                        href = "https://www.rozee.pk" + href
                    jobs.append(self._build_job(title, company, href, "Pakistan"))
                except Exception:
                    continue
            return jobs
        except Exception as exc:
            logger.warning("Rozee scrape failed: %s", exc)
            return []

    def _normalize(self, raw: dict) -> Dict[str, Any]:
        url = raw.get("url") or raw.get("job_url") or f"https://www.rozee.pk/job/{raw.get('id', '')}"
        if not url.startswith("http"):
            url = "https://www.rozee.pk" + url
        return self._build_job(
            title=raw.get("title") or raw.get("job_title", "Unknown"),
            company=raw.get("company") or raw.get("company_name", "Unknown"),
            url=url,
            location=raw.get("location") or raw.get("city", "Pakistan"),
            description=raw.get("description") or raw.get("job_description", ""),
            salary=raw.get("salary") or raw.get("salary_range", ""),
        )

    def _build_job(self, title: str, company: str, url: str,
                   location: str = "Pakistan", description: str = "", salary: str = "") -> Dict[str, Any]:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return {
            "title": title,
            "company": company,
            "location": location,
            "remote_type": "remote" if "remote" in (location + title).lower() else "unknown",
            "employment_type": "full_time",
            "description": description,
            "application_url": url,
            "salary_raw": salary,
            "source_name": "rozee",
            "url_hash": url_hash,
            "posting_date": datetime.utcnow().isoformat(),
            "discovered_at": datetime.utcnow().isoformat(),
        }
