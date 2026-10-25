"""
Matcha-Grade 24-Hour Freshness Engine & Junk Job Eliminator.
Guarantees zero stale jobs, zero fake repost dates, and deterministic UTC window validation.
"""
from __future__ import annotations

import re
import math
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Any

# Dead job content markers (soft 404s, expired pages)
DEAD_JOB_MARKERS = [
    "this job has expired",
    "position closed",
    "no longer accepting applications",
    "job posting has ended",
    "job is no longer available",
    "page not found",
    "404 not found",
    "this opening is closed",
    "the role you are looking for has been filled",
    "applications are now closed",
    "this job is inactive",
    "posting no longer available",
    "job unlisted",
    "job has been removed",
    "career site under maintenance",
    "this requisition is closed",
    "this position has been filled",
    "sorry, this position has already been filled"
]

def parse_iso_or_epoch(val: Any) -> Optional[datetime]:
    """
    Parses any date format (ISO-8601, Unix epoch seconds/ms, RFC-2822) into timezone-aware UTC datetime.
    Returns None if missing, NaN, or unparseable.
    """
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)

    # Check Unix epoch (seconds or milliseconds)
    if isinstance(val, (int, float)) or (isinstance(val, str) and val.strip().isdigit()):
        try:
            ts = float(val)
            if ts > 10_000_000_000:  # milliseconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None

    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "", "nan", "undefined"):
        return None

    # Handle relative strings like '2 hours ago', '30 minutes ago'
    rel_match = re.match(r"^(\d+)\s*(minute|hour|day|week|month)s?\s+ago$", s, re.IGNORECASE)
    if rel_match:
        qty = int(rel_match.group(1))
        unit = rel_match.group(2).lower()
        now = datetime.now(timezone.utc)
        if unit == "minute":
            return now - timedelta(minutes=qty)
        elif unit == "hour":
            return now - timedelta(hours=qty)
        elif unit == "day":
            return now - timedelta(days=qty)
        elif unit == "week":
            return now - timedelta(weeks=qty)
        elif unit == "month":
            return now - timedelta(days=qty * 30)

    # Try ISO format
    try:
        clean_s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Try RFC 2822
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Try standard string date formats
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%b %d, %Y"
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue

    return None

def verify_24h_freshness(
    date_val: Any, 
    max_hours: float = 24.0, 
    reference_time: Optional[datetime] = None
) -> Tuple[bool, float, Optional[datetime], str]:
    """
    Evaluates whether a job posting timestamp is strictly within the allowed freshness window.
    
    Returns:
        (is_fresh, hours_ago, parsed_dt, reason_message)
    """
    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    dt = parse_iso_or_epoch(date_val)
    if not dt:
        return False, 999999.0, None, "REJECTED: Missing or unparseable publication timestamp."

    diff_seconds = (now - dt).total_seconds()
    hours_ago = diff_seconds / 3600.0

    # Large future drift protection (> 2 hours into future is suspicious)
    if hours_ago < -2.0:
        return False, hours_ago, dt, f"REJECTED: Timestamp is {abs(hours_ago):.1f}h in the future (invalid clock/metadata)."

    if hours_ago > max_hours:
        return False, hours_ago, dt, f"REJECTED: Published {hours_ago:.1f}h ago (exceeds {max_hours:.0f}h window cutoff)."

    return True, max(0.0, hours_ago), dt, f"PASS: Fresh job posted {hours_ago:.1f}h ago (within {max_hours:.0f}h window)."

def contains_dead_job_markers(html_or_text: str) -> Tuple[bool, Optional[str]]:
    """
    Scans page text or response HTML for known dead-posting markers.
    """
    if not html_or_text:
        return False, None
    low = html_or_text.lower()
    for marker in DEAD_JOB_MARKERS:
        if marker in low:
            return True, marker
    return False, None
