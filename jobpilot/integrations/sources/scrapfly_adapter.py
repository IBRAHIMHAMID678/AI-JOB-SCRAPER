"""
Scrapfly Adapter — High-Resilience Web Scraping & Anti-Scraping Protection (ASP) Engine

Integrates Scrapfly API (via scrapfly-sdk or HTTP API) to bypass Cloudflare,
Datadome, and rate limits for protected targets (LinkedIn, Indeed, Glassdoor).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import requests

from ...core.config import settings
from ...core.logging import get_logger
from ...core.schemas import RawJob
from .base import JobSourceAdapter

logger = get_logger("sources.scrapfly")

SCRAPFLY_API_URL = "https://api.scrapfly.io/scrape"


class ScrapflyAdapter(JobSourceAdapter):
    """
    Scrapfly API adapter with Anti-Scraping Protection (ASP) and JS rendering capabilities.
    Acts as Tier-4/Tier-5 fallback for protected job boards and social post scraping.
    """
    source_name = "scrapfly"
    rate_limit_delay = 1.0

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__()
        self.api_key = api_key or os.getenv("SCRAPFLY_API_KEY")

    def scrape_url(
        self,
        url: str,
        asp: bool = True,
        render_js: bool = True,
        country: str = "us",
        session: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches a web page using Scrapfly API with anti-bot bypass and optional JS rendering.
        """
        if not self.api_key:
            logger.warning("[Scrapfly] SCRAPFLY_API_KEY not configured — skipping Scrapfly request")
            return None

        params = {
            "key": self.api_key,
            "url": url,
            "asp": "true" if asp else "false",
            "render_js": "true" if render_js else "false",
            "country": country,
        }
        if session:
            params["session"] = session

        try:
            response = requests.get(SCRAPFLY_API_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            logger.info("[Scrapfly] Successfully scraped '%s' (Status: %s)", url, data.get("result", {}).get("status"))
            return data
        except Exception as exc:
            logger.error("[Scrapfly] Failed to scrape '%s': %s", url, exc)
            return None

    def fetch(self) -> List[RawJob]:
        """
        Default fetch routine for Scrapfly adapter.
        Used to ingest protected search endpoints when direct HTTP/JobSpy is blocked.
        """
        if not self.api_key:
            logger.info("[Scrapfly] Adapter active but awaiting SCRAPFLY_API_KEY.")
            return []
        
        # Scrapfly is used primarily on demand by specific target crawlers (LinkedIn post, Indeed ASP)
        return []
