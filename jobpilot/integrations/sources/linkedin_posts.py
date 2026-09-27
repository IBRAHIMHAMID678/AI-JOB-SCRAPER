"""
LinkedIn Posts & Social Job Lead Ingestion Module

Scrapes and extracts hidden job leads from LinkedIn recruiter posts, DMs, and social media text.
Classifies leads into UNVERIFIED_LEAD and extracts contact emails, Google Form links, and ATS URLs.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from ...core.logging import get_logger
from ...core.schemas import RawJob
from .base import JobSourceAdapter
from .scrapfly_adapter import ScrapflyAdapter

logger = get_logger("sources.linkedin_posts")


class LinkedInPostLead(RawJob):
    """Extends RawJob to include extracted lead metadata."""
    is_social_lead: bool = True
    extracted_email: Optional[str] = None
    extracted_form_url: Optional[str] = None
    extracted_author: Optional[str] = None


def extract_social_lead_metadata(post_text: str) -> Dict[str, Any]:
    """
    Parses raw text of a social media post to extract emails, Google Forms, and career links.
    """
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', post_text)
    google_forms = re.findall(r'https?://(?:forms\.gle|docs\.google\.com/forms)/[^\s]+', post_text)
    ats_links = re.findall(r'https?://(?:boards\.greenhouse\.io|jobs\.lever\.co|myworkdayjobs\.com)/[^\s]+', post_text)
    urls = re.findall(r'https?://[^\s]+', post_text)

    primary_email = emails[0] if emails else None
    primary_form = google_forms[0] if google_forms else (ats_links[0] if ats_links else (urls[0] if urls else None))

    return {
        "emails": emails,
        "primary_email": primary_email,
        "google_forms": google_forms,
        "primary_form": primary_form,
        "all_urls": urls,
    }


class LinkedInPostsAdapter(JobSourceAdapter):
    """
    Adapter for discovering hidden job leads from social post content.
    """
    source_name = "linkedin_posts"
    rate_limit_delay = 2.0

    def __init__(self) -> None:
        super().__init__()
        self.scrapfly = ScrapflyAdapter()

    def parse_post_to_raw_job(self, post_text: str, post_url: str, author_name: str = "Recruiter") -> Optional[RawJob]:
        """
        Converts social post text into a RawJob schema item.
        """
        if not post_text or len(post_text) < 30:
            return None

        lead_meta = extract_social_lead_metadata(post_text)
        app_url = lead_meta["primary_form"] or lead_meta["primary_email"] or post_url

        # Infer basic title/company
        first_line = post_text.split('\n')[0][:80]
        title = first_line if "hiring" in first_line.lower() or "looking" in first_line.lower() else f"Opportunity via {author_name}"

        return RawJob(
            title=title,
            company=author_name,
            location="Remote",
            description=post_text,
            application_url=app_url if app_url.startswith("http") else post_url,
            source="LinkedIn Post Lead",
            extra={
                "is_social_lead": True,
                "author": author_name,
                "extracted_email": lead_meta["primary_email"],
                "extracted_form_url": lead_meta["primary_form"],
                "raw_urls": lead_meta["all_urls"],
            }
        )

    def fetch(self) -> List[RawJob]:
        """
        Fetch social job leads using Scrapfly when available.

        STUB (2026-09-27): there are no configured post targets, so a real
        fetch is not feasible yet. This intentionally returns [] and the
        adapter is NOT registered in workers/pipeline._fetch_all_sources()
        or production_batch_run.discover_raw_jobs() — counting it as an
        active source would mislead source stats. Use
        parse_post_to_raw_job() to convert already-harvested post text.
        """
        # Social post discovery runs on configured targets or periodic lead searches
        logger.info("[LinkedInPosts] Social lead ingestion engine ready.")
        return []
