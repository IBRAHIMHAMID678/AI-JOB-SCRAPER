"""Source plugins. Each exposes fetch() -> list[normalized job dict]."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
GENERIC_EMAILS = {"example.com", "email.com", "domain.com", "remoteok.com", "remotive.com"}


def _emails(text: str) -> list[str]:
    out = []
    for e in EMAIL_RE.findall(text or ""):
        dom = e.split("@")[-1].lower()
        if dom not in GENERIC_EMAILS and e not in out:
            out.append(e)
    return out


def _get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (job-scraper)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _strip_html(html: str) -> str:
    txt = re.sub(r"<br\s*/?>", "\n", html or "")
    txt = re.sub(r"</p\s*>", "\n", txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def _parse_dt(s):
    if not s:
        return None
    if isinstance(s, (int, float)) or (isinstance(s, str) and s.strip().isdigit()):
        v = int(float(s))
        if v > 10_000_000_000:  # ms
            v //= 1000
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except Exception:
            return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:  # RFC 2822 (RSS pubDate)
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(str(s))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _salary_unit(job: dict) -> str:
    return "yearly"


def fetch_remoteok() -> list[dict]:
    """RemoteOK public JSON API. Remote-only board; Pakistan eligibility checked per-post."""
    raw = json.loads(_get("https://remoteok.com/api"))
    jobs = []
    for j in raw:
        if not isinstance(j, dict) or "position" not in j:
            continue
        desc = j.get("description") or ""
        emails = _emails(desc)
        smin, smax = j.get("salary_min") or 0, j.get("salary_max") or 0
        jobs.append({
            "source": "remoteok",
            "id": f"rok-{j.get('id')}",
            "title": j.get("position") or "",
            "company": (j.get("company") or "").strip(),
            "description": desc,
            "url": j.get("url") or "",
            "apply_url": j.get("apply_url") or j.get("url") or "",
            "apply_email": emails[0] if emails else None,
            "location": j.get("location") or "Remote",
            "remote": True,
            "salary_min": smin if smin else None,
            "salary_max": smax if smax else None,
            "salary_unit": "yearly" if (smin or smax) else None,
            "posted_at": _parse_dt(j.get("date")),
            "tags": j.get("tags") or [],
        })
    return jobs


def fetch_remotive() -> list[dict]:
    """Remotive public API. Remote-only board."""
    jobs = []
    url = "https://remotive.com/api/remote-jobs?limit=100"
    raw = json.loads(_get(url))
    for j in raw.get("jobs", []):
        desc = j.get("description") or ""
        emails = _emails(desc)
        jobs.append({
            "source": "remotive",
            "id": f"rmt-{j.get('id')}",
            "title": j.get("title") or "",
            "company": j.get("company_name") or "",
            "description": desc,
            "url": j.get("url") or "",
            "apply_url": j.get("url") or "",
            "apply_email": emails[0] if emails else None,
            "location": j.get("candidate_required_location") or "Remote",
            "remote": True,
            "salary_min": None,
            "salary_max": None,
            "salary_unit": None,
            "posted_at": _parse_dt(j.get("publication_date")),
            "tags": (j.get("tags") or []),
        })
    return jobs


def fetch_hn_hiring() -> list[dict]:
    """HN 'Who is hiring' — current month's thread, via Algolia search."""
    # Find the latest "Who is hiring" thread
    search = json.loads(_get(
        "https://hn.algolia.com/api/v1/search?query=who%20is%20hiring&tags=story"
    ))
    thread_id = None
    for hit in search.get("hits", []):
        if "who is hiring" in (hit.get("title") or "").lower():
            thread_id = hit["objectID"]
            break
    if not thread_id:
        return []
    thread = json.loads(_get(f"https://hn.algolia.com/api/v1/items/{thread_id}"))
    jobs = []
    for c in thread.get("children", []):
        text = c.get("text") or ""
        if len(text) < 80:
            continue
        # First line is usually "Company | Role | Location"
        first = text.split("\n")[0]
        parts = [p.strip() for p in re.split(r"\s*\|\s*", re.sub(r"<[^>]+>", "", first))]
        company = parts[0] if parts else ""
        title = parts[1] if len(parts) > 1 else first[:80]
        location = parts[2] if len(parts) > 2 else ""
        emails = _emails(text)
        urls = re.findall(r"https?://[^\s)<>\"']+", text)
        jobs.append({
            "source": "hn_hiring",
            "id": f"hn-{c.get('id')}",
            "title": title,
            "company": company,
            "description": re.sub(r"<[^>]+>", " ", text),
            "url": f"https://news.ycombinator.com/item?id={c.get('id')}",
            "apply_url": urls[0] if urls else "",
            "apply_email": emails[0] if emails else None,
            "location": location,
            "remote": bool(re.search(r"\bremote\b", text, re.I)),
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(c.get("created_at")),
            "tags": [],
        })
    return jobs


def fetch_linkedin() -> list[dict]:
    """LinkedIn Jobs via jobspy (runs in the scraper venv). 5-day freshness."""
    from jobspy import scrape_jobs
    terms = ["AI Engineer", "Python Developer", "Full Stack Developer",
             "Machine Learning Engineer", "LLM Engineer"]
    jobs = []
    for term in terms:
        try:
            df = scrape_jobs(site_name=["linkedin"], search_term=term,
                             location="Pakistan", results_wanted=25,
                             hours_old=120, country_indeed="Pakistan")
        except Exception as e:
            print(f"  linkedin/{term}: {type(e).__name__}", flush=True)
            continue
        for _, r in df.iterrows():
            desc = str(r.get("description") or "")
            emails = _emails(desc)
            posted = r.get("date_posted")
            jobs.append({
                "source": "linkedin",
                "id": f"li-{r.get('id') or abs(hash(str(r.get('job_url'))))}",
                "title": str(r.get("title") or ""),
                "company": str(r.get("company") or ""),
                "description": desc,
                "url": str(r.get("job_url") or ""),
                "apply_url": str(r.get("job_url") or ""),
                "apply_email": emails[0] if emails else None,
                "location": str(r.get("location") or ""),
                "remote": bool(re.search(r"\bremote\b", str(r.get("location") or "") + desc, re.I)),
                "salary_min": None, "salary_max": None, "salary_unit": None,
                "posted_at": _parse_dt(posted) if posted else None,
                "tags": [],
            })
    return jobs


def fetch_workingnomads() -> list[dict]:
    """Working Nomads public JSON API. Mixed categories; client-side dev filter."""
    raw = json.loads(_get("https://www.workingnomads.com/api/exposed_jobs/"))
    jobs = []
    for j in raw:
        if not isinstance(j, dict):
            continue
        desc = _strip_html(j.get("description") or "")
        emails = _emails(desc)
        tags = j.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        jobs.append({
            "source": "workingnomads",
            "id": f"wn-{j.get('url', '').rstrip('/').split('/')[-1] or abs(hash(j.get('title') or ''))}",
            "title": j.get("title") or "",
            "company": (j.get("company_name") or "").strip(),
            "description": desc,
            "url": j.get("url") or "",
            "apply_url": j.get("url") or "",
            "apply_email": emails[0] if emails else None,
            "location": j.get("location") or "",
            "remote": bool(re.search(r"\bremote\b", str(j.get("location") or ""), re.I)),
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(j.get("pub_date")),
            "tags": [j.get("category_name") or ""] + tags,
        })
    return jobs


def fetch_jobicy() -> list[dict]:
    """Jobicy documented public feed (200 latest remote jobs)."""
    raw = json.loads(_get("https://jobicy.com/api/v2/remote-jobs"))
    jobs = []
    for j in (raw.get("jobs") or []):
        desc = _strip_html(j.get("jobDescription") or j.get("jobExcerpt") or "")
        emails = _emails(desc)
        jobs.append({
            "source": "jobicy",
            "id": f"jc-{j.get('id')}",
            "title": j.get("jobTitle") or "",
            "company": (j.get("companyName") or "").strip(),
            "description": desc,
            "url": j.get("url") or "",
            "apply_url": j.get("url") or "",
            "apply_email": emails[0] if emails else None,
            "location": j.get("jobGeo") or "",
            "remote": True,
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(j.get("pubDate")),
            "tags": (j.get("jobIndustry") or []) + [j.get("jobLevel") or ""],
        })
    return jobs


def fetch_himalayas() -> list[dict]:
    """Himalayas public jobs API, cursor-paginated (2 pages x 20)."""
    jobs, cursor, pages = [], None, 0
    while pages < 2:
        url = "https://himalayas.app/jobs/api?limit=20" + (f"&cursor={cursor}" if cursor else "")
        raw = json.loads(_get(url))
        for j in (raw.get("jobs") or []):
            desc = (j.get("description") or "") + "\n" + (j.get("excerpt") or "")
            emails = _emails(desc)
            loc = j.get("locationRestrictions") or ""
            if isinstance(loc, list):
                loc = ", ".join(str(x) for x in loc)
            jobs.append({
                "source": "himalayas",
                "id": f"hi-{j.get('guid') or j.get('applicationLink') or abs(hash(j.get('title') or ''))}",
                "title": j.get("title") or "",
                "company": (j.get("companyName") or "").strip(),
                "description": desc,
                "url": j.get("applicationLink") or "",
                "apply_url": j.get("applicationLink") or "",
                "apply_email": emails[0] if emails else None,
                "location": loc,
                "remote": True,
                "salary_min": j.get("minSalary"), "salary_max": j.get("maxSalary"),
                "salary_unit": "yearly" if (j.get("salaryPeriod") or "").lower() != "monthly" else "monthly",
                "posted_at": _parse_dt(j.get("pubDate")),
                "tags": (j.get("categories") or []) + [j.get("seniority") or ""],
            })
        cursor = raw.get("nextCursor")
        pages += 1
        if not cursor:
            break
    return jobs


def fetch_wwr() -> list[dict]:
    """We Work Remotely RSS feed (job-seeker application is paywalled; RSS is free)."""
    import xml.etree.ElementTree as ET
    xml_text = _get("https://weworkremotely.com/remote-jobs.rss")
    jobs = []
    for item in ET.fromstring(xml_text).iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = _strip_html(item.findtext("description") or "")
        pub = item.findtext("pubDate")
        emails = _emails(desc)
        m = re.match(r"^(.*?):\s*(.*)$", title)
        company, role = (m.group(1).strip(), m.group(2).strip()) if m else ("", title)
        jobs.append({
            "source": "wwr",
            "id": f"wwr-{abs(hash(link))}",
            "title": role,
            "company": company,
            "description": desc,
            "url": link,
            "apply_url": link,
            "apply_email": emails[0] if emails else None,
            "location": "Remote",
            "remote": True,
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(pub) if pub else None,
            "tags": [],
        })
    return jobs


SOURCES = {
    "remoteok": fetch_remoteok,
    "remotive": fetch_remotive,
    "hn_hiring": fetch_hn_hiring,
    "linkedin": fetch_linkedin,
    "workingnomads": fetch_workingnomads,
    "jobicy": fetch_jobicy,
    "himalayas": fetch_himalayas,
    "wwr": fetch_wwr,
}
