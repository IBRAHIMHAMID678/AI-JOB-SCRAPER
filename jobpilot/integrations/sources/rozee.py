"""
Rozee.pk job source adapter.
Uses Rozee's public job listing API/RSS to fetch fresh jobs.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from .base import JobSourceAdapter
from ...core.logging import get_logger

logger = get_logger(__name__)

ROZEE_API = "https://www.rozee.pk/api/jobs/search"
ROZEE_SEARCH = "https://www.rozee.pk/job/jsearch/q/{query}/ft/1"


from ...core.schemas import RawJob


class RozeeAdapter(JobSourceAdapter):
    source_name = "rozee"

    def fetch(self, search_terms: Optional[List[str]] = None, max_results: int = 15) -> List[RawJob]:
        from ...core.config import settings
        if not search_terms:
            search_terms = settings.SEARCH_TERMS
        jobs = []
        failed_terms = 0
        for term in search_terms[:4]:  # limit to 4 terms to avoid rate limits
            try:
                results = self._search(term, max_results)
                jobs.extend(results)
                if len(jobs) >= max_results * 2:
                    break
            except Exception as exc:
                failed_terms += 1
                logger.error("Rozee fetch failed for '%s': %s", term, exc)
        if not jobs and failed_terms == min(4, len(search_terms[:4])):
            raise RuntimeError("Rozee: all term searches failed")
        return jobs[:max_results * 2]

    def _search(self, query: str, limit: int) -> List[RawJob]:
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
            # Loud: any non-200 (verified 403 Cloudflare "Just a moment...")
            logger.error(
                "Rozee API returned HTTP %d for '%s' — direct access blocked; "
                "trying Scrapfly ASP fallback",
                resp.status_code, query,
            )
        except requests.RequestException as exc:
            logger.error("Rozee API request failed for '%s': %s — trying Scrapfly ASP fallback", query, exc)

        # Cloudflare-blocked fallback: route through Scrapfly anti-bot bypass.
        return self._scrape_via_scrapfly(query, limit, headers)

    def _scrape_via_scrapfly(self, query: str, limit: int, headers: dict) -> List[RawJob]:
        """Scrape the Rozee listing page via Scrapfly (ASP/Cloudflare bypass)."""
        from .scrapfly_adapter import ScrapflyAdapter
        scraper = ScrapflyAdapter()
        if not scraper.api_key:
            # Deterministic failure — no point burning get_jobs() retries.
            logger.error(
                "Rozee is Cloudflare-blocked (HTTP 403) and SCRAPFLY_API_KEY is "
                "not configured — Rozee yields 0 jobs this run"
            )
            return []
        url = f"https://www.rozee.pk/job/jsearch/q/{requests.utils.quote(query)}"
        data = scraper.scrape_url(url, asp=True, render_js=True, country="pk")
        if not data:
            raise RuntimeError(f"Rozee Scrapfly fallback failed for '{query}'")
        html = (data.get("result") or {}).get("content") or ""
        if not html:
            raise RuntimeError(f"Rozee Scrapfly returned no content for '{query}'")
        return self._parse_listing_html(html, limit)

    def _scrape_listing(self, query: str, limit: int, headers: dict) -> List[RawJob]:
        # Direct listing scrape is Cloudflare-blocked (403); kept for
        # reference, but _search now routes blocked traffic via Scrapfly.
        url = f"https://www.rozee.pk/job/jsearch/q/{requests.utils.quote(query)}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.error("Rozee direct listing scrape HTTP %d for '%s'", resp.status_code, query)
            return []
        return self._parse_listing_html(resp.text, limit)

    def _parse_listing_html(self, html: str, limit: int) -> List[RawJob]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        jobs = []
        for card in soup.select(".job-listing, .jlisting, [data-job-id]")[:limit]:
            try:
                title_el = card.select_one(".job-title, h2, h3, .title")
                company_el = card.select_one(".company-name, .company, .org")
                link_el = card.select_one("a[href*='/job/'], a[href*='rozee']")
                title = title_el.get_text(strip=True) if title_el else ""
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                href = link_el["href"] if link_el and link_el.has_attr("href") else ""
                if not href.startswith("http"):
                    href = "https://www.rozee.pk" + href
                if not title:
                    continue
                jobs.append(self._build_job(title, company, href, "Pakistan"))
            except Exception:
                continue
        return jobs

    def _normalize(self, raw: dict) -> RawJob:
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
                   location: str = "Pakistan", description: str = "", salary: str = "") -> RawJob:
        return RawJob(
            title=title,
            company=company,
            location=location,
            remote_type="remote" if "remote" in (location + title).lower() else "unknown",
            employment_type="full_time",
            description=description,
            application_url=url,
            salary_raw=salary,
            source="rozee",
        )
