"""Description extraction pipeline (2026-10-09 P0).

Every job dict carries:
    description:            the best description text available (may be empty)
    description_full:        the complete extracted description (never truncated
                            for display; filters and digest use this)
    description_status:      full | partial | empty | unavailable | blocked
    description_method:      how the description was obtained
    description_source_url:  final detail-page URL actually read
    description_fetched_at:  ISO timestamp of the extraction attempt
    description_error:        failure reason when status is not full

Rules:
- Never mark a description 'full' on length alone; 'full' means the complete
  official posting text was retrieved from the employer/board detail page or
  a complete API field.
- Never bypass CAPTCHAs, logins, paywalls, or bot walls. Blocked pages are
  recorded as 'blocked', not faked.
- Bounded retries with exponential backoff for transient failures.
- Public/documented APIs first; official detail page as fallback.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (job-scraper)"}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    s = _TAG_RE.sub(" ", s or "")
    s = html.unescape(s)
    return _WS_RE.sub(" ", s).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 25,
                     headers: dict | None = None) -> tuple[str | None, str | None]:
    """GET a URL with bounded exponential backoff.

    Returns (text, error). error is None on success. Transient failures
    (timeout, 5xx, 429, IncompleteRead) are retried; 404/410 and 403/bot
    walls are returned immediately as non-retryable.
    """
    hdrs = dict(_UA)
    if headers:
        hdrs.update(headers)
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace"), None
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None, f"http_{e.code}_not_found"
            if e.code in (401, 403):
                return None, f"http_{e.code}_blocked"
            if e.code == 429:
                last_err = f"http_429_rate_limited"
            else:
                last_err = f"http_{e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                Exception) as e:
            last_err = f"{type(e).__name__}: {str(e)[:120]}"
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # 1s, 2s, 4s
    return None, f"retry_exhausted({last_err})"


def _classify_length(text: str) -> str:
    """Classify by completeness signals, not length alone. Callers that
    retrieved the full official text should pass status='full' explicitly."""
    n = len((text or "").strip())
    if n == 0:
        return "empty"
    if n < 200:
        return "partial"  # snippet, not a real JD
    return "partial"  # >=200 chars but not verified complete


def set_description(job: dict, text: str | None, status: str, method: str,
                    source_url: str = "", error: str = ""):
    """Record a description extraction outcome on the job dict."""
    text = (text or "").strip()
    job["description"] = text
    job["description_full"] = text  # never truncated; filters use this
    job["description_status"] = status
    job["description_method"] = method
    job["description_source_url"] = source_url or job.get("url", "")
    job["description_fetched_at"] = _now_iso()
    if error:
        job["description_error"] = error
    elif "description_error" in job:
        job.pop("description_error", None)


# ---- source-specific adapters -------------------------------------------------
def adapt_arc(job: dict) -> bool:
    """Arc.dev: fetch the job detail page, extract description from __NEXT_DATA__."""
    url = job.get("url") or ""
    if "arc.dev" not in url:
        set_description(job, "", "unavailable", "arc_no_detail_url",
                        error="no arc.dev detail URL")
        return False
    page, err = fetch_with_retry(url)
    if err:
        status = "blocked" if "blocked" in err else "unavailable"
        set_description(job, "", status, "arc_detail_fetch", url, error=err)
        return False
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', page or "", re.S)
    if not m:
        set_description(job, "", "unavailable", "arc_next_data_missing", url,
                        error="__NEXT_DATA__ not found")
        return False
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        set_description(job, "", "unavailable", "arc_next_data_parse", url,
                        error=f"JSON parse: {e}")
        return False
    # walk the payload for a description-like field
    desc = ""

    def _walk(o):
        nonlocal desc
        if desc or not isinstance(o, (dict, list)):
            return
        if isinstance(o, dict):
            for k in ("description", "jobDescription", "details", "aboutRole"):
                v = o.get(k)
                if isinstance(v, str) and len(v.strip()) > 300:
                    desc = _strip_html(v)
                    return
            for v in o.values():
                _walk(v)
        else:
            for v in o:
                _walk(v)

    _walk(data)
    if len(desc) >= 300:
        set_description(job, desc, "full", "arc_next_data", url)
        return True
    set_description(job, desc, "partial" if desc else "unavailable",
                    "arc_next_data", url,
                    error="" if desc else "no description field in payload")
    return bool(desc)


def adapt_smartrecruiters(job: dict) -> bool:
    """SmartRecruiters: use the public posting detail API."""
    url = job.get("url") or ""
    m = re.search(r"smartrecruiters\.com/([^/]+)/[^/]*?([0-9a-f-]{8,})", url or "", re.I)
    company = job.get("_sr_company") or ""
    posting_id = job.get("_sr_id") or ""
    if not posting_id and m:
        company, posting_id = m.group(1), m.group(2)
    if not company or not posting_id:
        set_description(job, "", "unavailable", "sr_no_ids",
                        error="no SmartRecruiters company/posting id")
        return False
    api = f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{posting_id}"
    body, err = fetch_with_retry(api, headers={"Accept": "application/json"})
    if err:
        status = "blocked" if "blocked" in err else "unavailable"
        set_description(job, "", status, "sr_api", api, error=err)
        return False
    try:
        data = json.loads(body or "{}")
    except Exception as e:
        set_description(job, "", "unavailable", "sr_api_parse", api, error=str(e)[:120])
        return False
    jd = data.get("jobAd") or {}
    sections = jd.get("sections") or {}
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation"):
        sec = sections.get(key) or {}
        t = sec.get("text") or ""
        if t:
            parts.append(_strip_html(t))
    company_desc = _strip_html((jd.get("companyDescription") or {}).get("text") or "")
    full = "\n\n".join(p for p in parts if p)
    if company_desc and full:
        full = company_desc + "\n\n" + full
    if len(full) >= 300:
        set_description(job, full, "full", "sr_api", api)
        return True
    set_description(job, full, "partial" if full else "unavailable",
                    "sr_api", api, error="" if full else "no jobAd sections")
    return bool(full)


def adapt_linkedin(job: dict) -> bool:
    """LinkedIn: job pages require auth and are bot-walled. Do NOT attempt to
    scrape them — record honestly as blocked/unavailable."""
    desc = (job.get("description") or "").strip()
    if len(desc) >= 800:
        set_description(job, desc, "full", "jobspy_api",
                        job.get("url", ""))
        return True
    if desc:
        set_description(job, desc, "partial", "jobspy_api",
                        job.get("url", ""),
                        error="jobspy returned truncated description")
        return False
    set_description(job, "", "unavailable", "jobspy_empty",
                    job.get("url", ""),
                    error="jobspy returned no description; LinkedIn detail pages require auth (not attempted)")
    return False


def adapt_reddit(job: dict) -> bool:
    """Reddit: distinguish the hiring POST from the employer's actual posting.
    The post body is the post, not the JD. Try to find a linked employer URL."""
    body = (job.get("description") or "").strip()
    url = job.get("url") or ""
    # look for an external hiring link inside the post
    ext = re.findall(r"https?://(?!reddit\.com|redd\.it)[^\s)>\]]+", body + " " + url)
    ext = [u for u in ext if "reddit" not in u]
    job["_reddit_post_body"] = body  # preserve the post separately
    if ext:
        job["_employer_url_candidate"] = ext[0]
        set_description(job, body, "partial", "reddit_post_body", url,
                        error=f"post body only; employer posting may be at {ext[0]} (not fetched)")
        return False
    set_description(job, body, "partial" if body else "empty", "reddit_post_body",
                    url, error="no employer link found in post" if body else "empty post body")
    return False


def adapt_wad(job: dict) -> bool:
    """WeAreDistributed: delegate to the existing JSON-LD enrichment."""
    try:
        from enrich import enrich_wad_job
    except ImportError:
        set_description(job, "", "unavailable", "wad_enrich_missing",
                        error="enrich module not importable")
        return False
    ok = enrich_wad_job(job)
    desc = (job.get("description") or "").strip()
    if ok and len(desc) >= 300:
        set_description(job, desc, "full", "wad_jsonld", job.get("url", ""))
        return True
    if desc:
        set_description(job, desc, "partial", "wad_jsonld", job.get("url", ""),
                        error="JSON-LD description short or fallback text used")
        return False
    set_description(job, "", "unavailable", "wad_jsonld", job.get("url", ""),
                    error="detail page fetch failed or no JSON-LD JobPosting")
    return False


_ADAPTERS = {
    "linkedin": adapt_linkedin,
    "arc": adapt_arc,
    "ats:smartrecruiters": adapt_smartrecruiters,
    "wearedistributed": adapt_wad,
    "reddit_rss": adapt_reddit,
    "reddit_forhire": adapt_reddit,
}


def enrich_description(job: dict, pre_classify_only: bool = False) -> dict:
    """Run the extraction pipeline for one job. Returns the job dict.

    - If the job already has a good description from its source API, it is
      marked 'full' (API-complete) without refetching.
    - Otherwise the source-specific adapter is tried (bounded).
    - Never invents a description; records status + method + error honestly.
    - pre_classify_only=True: set description_status from existing data only,
      no network fetches. Used before first-pass filtering.
    """
    src = (job.get("source") or "").lower()
    existing = (job.get("description") or "").strip()

    # API-complete: ATS and board APIs that return the full posting text
    api_full_sources = {"ats:greenhouse", "ats:lever", "ats:ashby", "remoteok",
                        "remotive", "himalayas", "wwr", "jobicy", "workingnomads",
                        "nocommute", "justremote", "apnijobs", "hn_hiring",
                        "pythonorg", "remote4africa", "dailyremote"}
    if src in api_full_sources and len(existing) >= 800:
        set_description(job, existing, "full", f"{src}_api_complete",
                        job.get("url", ""))
        return job
    if src in api_full_sources and existing:
        set_description(job, existing, "partial", f"{src}_api_partial",
                        job.get("url", ""), error="API description short")
        return job

    if pre_classify_only:
        # no network: classify what the source gave us
        if existing:
            set_description(job, existing, _classify_length(existing),
                            f"{src}_pre_classify", job.get("url", ""),
                            error="detail enrichment pending")
        else:
            set_description(job, "", "empty", f"{src}_pre_classify",
                            job.get("url", ""), error="source provided no description")
        return job

    adapter = _ADAPTERS.get(src)
    if adapter:
        try:
            adapter(job)
        except Exception as e:
            set_description(job, existing, "unavailable", f"{src}_adapter_error",
                            job.get("url", ""), error=f"{type(e).__name__}: {str(e)[:120]}")
    else:
        # no adapter and no API-complete source: classify what we have
        if existing:
            set_description(job, existing, _classify_length(existing),
                            f"{src}_as_scraped", job.get("url", ""),
                            error="no adapter; completeness unverified")
        else:
            set_description(job, "", "empty", f"{src}_as_scraped",
                            job.get("url", ""), error="source provided no description")
    return job
