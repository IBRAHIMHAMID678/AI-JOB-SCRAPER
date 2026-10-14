"""
Hacker News "Who is Hiring?" Live Algolia Sniper.
Taps the monthly Hacker News hiring thread where founders and engineering leads post directly.
Bypasses HR screeners, geofencing, and ATS filters to extract direct worldwide remote engineering leads.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


class HNSniper:
    """Live parser and sniper for Hacker News monthly hiring threads."""

    WORLDWIDE_PATTERNS = [
        re.compile(r"\b(remote\s*:\s*(?:yes|true|anywhere|worldwide|global))\b", re.IGNORECASE),
        re.compile(r"\b(remote\s*\((?:worldwide|anywhere|global|all\s+locations)\))\b", re.IGNORECASE),
        re.compile(r"\b(?:anywhere\s+in\s+the\s+world|work\s+from\s+anywhere|global\s+remote)\b", re.IGNORECASE),
        re.compile(r"\bremote\b", re.IGNORECASE),
    ]

    EXCLUSION_PATTERNS = [
        re.compile(r"\b(us\s+only|us\s+citizens?\s+only|americas\s+only|north\s+america\s+only)\b", re.IGNORECASE),
        re.compile(r"\b(eu\s+only|uk\s+only|no\s+sponsorship|must\s+reside\s+in)\b", re.IGNORECASE),
        re.compile(r"\b(w2\s+only|must\s+be\s+authorized\s+to\s+work\s+in\s+the\s+us)\b", re.IGNORECASE),
    ]

    EMAIL_PATTERN = re.compile(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    )

    TECH_KEYWORDS = [
        "python", "fastapi", "react", "next.js", "nextjs", "ai", "llm",
        "rag", "langchain", "fullstack", "full-stack", "backend", "typescript"
    ]

    @classmethod
    async def get_latest_hiring_story_id(cls, session: aiohttp.ClientSession) -> Optional[int]:
        """Find the story ID of the most recent 'Ask HN: Who is hiring?' thread."""
        params = {
            "query": "Ask HN: Who is hiring?",
            "tags": "story,author_whoishiring",
            "hitsPerPage": 3,
        }
        try:
            async with session.get(ALGOLIA_SEARCH_URL, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    hits = data.get("hits", [])
                    if hits:
                        return hits[0]["objectID"]
        except Exception as exc:
            logger.warning("Failed to locate latest Who is Hiring story: %s", exc)
        return None

    @classmethod
    def parse_hiring_comment(cls, comment_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parses an individual HN comment into a structured lead."""
        text = comment_data.get("comment_text", "")
        if not text:
            return None

        # Clean HTML entities/tags
        clean_text = re.sub(r"<[^>]+>", " ", text)
        clean_text = re.sub(r"&#x2F;", "/", clean_text)
        clean_text = re.sub(r"&amp;", "&", clean_text)
        clean_text = re.sub(r"&quot;", '"', clean_text)
        clean_text = re.sub(r"&#x27;", "'", clean_text)

        # Check for location disqualifiers
        for exc_pat in cls.EXCLUSION_PATTERNS:
            if exc_pat.search(clean_text):
                return None

        # Check for remote availability
        is_remote = any(pat.search(clean_text) for pat in cls.WORLDWIDE_PATTERNS)
        if not is_remote:
            return None

        # Check for technical stack match
        lower_text = clean_text.lower()
        matched_tags = [kw for kw in cls.TECH_KEYWORDS if kw in lower_text]
        if not matched_tags:
            return None

        # Extract contact emails
        emails = cls.EMAIL_PATTERN.findall(clean_text)
        # Filter out common false positives like email regexes or example.com
        filtered_emails = [e for e in emails if not e.endswith((".png", ".jpg", "example.com", "ycombinator.com"))]
        contact_email = filtered_emails[0] if filtered_emails else None

        # Extract company and role from first line
        first_line = clean_text.strip().split("\n")[0]
        parts = [p.strip() for p in first_line.split("|") if p.strip()]

        company = parts[0] if len(parts) > 0 else "Stealth Startup"
        role = parts[1] if len(parts) > 1 else "Software / AI Engineer"
        location_field = parts[2] if len(parts) > 2 else "Remote"

        return {
            "id": f"hn_{comment_data.get('objectID')}",
            "source": "hacker_news_who_is_hiring",
            "company": company,
            "role": role,
            "location": location_field,
            "is_worldwide": True,
            "contact_email": contact_email,
            "matched_skills": matched_tags,
            "author": comment_data.get("author"),
            "created_at": comment_data.get("created_at"),
            "url": f"https://news.ycombinator.com/item?id={comment_data.get('objectID')}",
            "snippet": clean_text[:300] + "..." if len(clean_text) > 300 else clean_text,
            "full_text": clean_text
        }

    @classmethod
    async def fetch_worldwide_leads(cls, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetches and parses the latest worldwide remote engineering leads from HN."""
        leads = []
        async with aiohttp.ClientSession() as session:
            story_id = await cls.get_latest_hiring_story_id(session)
            if not story_id:
                # Fallback to general comment search if story ID not resolved
                params = {
                    "query": "remote python OR fastapi OR react",
                    "tags": "comment",
                    "hitsPerPage": 50,
                }
            else:
                params = {
                    "tags": f"comment,story_{story_id}",
                    "hitsPerPage": 150,
                }

            try:
                async with session.get(ALGOLIA_SEARCH_URL, params=params, timeout=12) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        hits = data.get("hits", [])
                        for hit in hits:
                            parsed = cls.parse_hiring_comment(hit)
                            if parsed:
                                leads.append(parsed)
                                if len(leads) >= limit:
                                    break
            except Exception as exc:
                logger.error("Error fetching Hacker News hiring feed: %s", exc)

        return leads
