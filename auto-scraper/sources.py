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


# ---------------------------------------------------------------- YC Jobs
# Technique (via github.com/thomascouto/crosscheck): YC's PUBLIC Algolia
# company index (search-only key shipped in ycombinator.com — public, not a
# secret) lists every hiring company with region facets -> workatastartup.com
# company pages embed open jobs as Inertia.js JSON -> job detail pages embed
# description + visa info. No login, no API key.
_YC_ALGOLIA = {
    "url": "https://45BWZJ1SGC-dsn.algolia.net/1/indexes/*/queries",
    "appId": "45BWZJ1SGC",
    "key": "NzJmMWExZWYxYzY5OGYwN2VkYWM5YzRiM2VlNDFlM2I0ODU2YjQ2Yjg0MTFiNWE5NzY0NTMyZGI1OWEwMzVjY2FuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE",
    "index": "YCCompany_production",
}
_YC_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
# title pre-filter (cheap, before fetching detail pages); filter.py does the precise pass
_YC_TITLE_RE = re.compile(
    r"\b(ai|ml|llm|rag|genai|python|full[\s-]?stack|backend|software|data|platform|devops|"
    r"site reliability|automation|agent|engineer|developer|programmer)\b", re.I)
# company pre-filter: AI/dev-tool signals in name / one-liner / tags / industries
_YC_CO_RE = re.compile(
    r"artificial intelligence|machine learning|generative ai|\bllm\b|developer tools|"
    r"devtools|\bapi\b|data infrastructure|mlops|ai agent|natural language|computer vision", re.I)
_YC_MAX_COMPANIES = 80


def _yc_algolia(params: dict) -> dict:
    import urllib.parse
    payload = {"requests": [{"indexName": _YC_ALGOLIA["index"],
                             "params": urllib.parse.urlencode(params)}]}
    req = urllib.request.Request(
        _YC_ALGOLIA["url"], data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "X-Algolia-Application-Id": _YC_ALGOLIA["appId"],
                 "X-Algolia-API-Key": _YC_ALGOLIA["key"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))["results"][0]


def _yc_data_page(url: str):
    # /jobs/<id> answers 406 unless the request explicitly accepts HTML
    req = urllib.request.Request(url, headers={**_YC_UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html_text = r.read().decode("utf-8", "ignore")
    m = re.search(r'data-page="([^"]+)"', html_text)
    if not m:
        return None
    import html as _html
    return json.loads(_html.unescape(m.group(1)))


def _yc_salary(s: str):
    # "$185K - $218K" -> yearly; "$90 - $110 /hr" -> hourly*2080; "$5,000 /mo" -> monthly*12.
    # Bare small numbers with no period marker are ambiguous -> (None, None), don't fabricate.
    if not s:
        return None, None
    slow = s.lower()
    if re.search(r"/\s*(hr|hour)|per hour", slow):
        mult = 2080
    elif re.search(r"/\s*(mo|month)|per month", slow):
        mult = 12
    elif "k" in slow:
        mult = 1000
    else:
        mult = None
    nums = re.findall(r"\$([\d.,]+)", s)
    vals = []
    for n in nums:
        try:
            v = float(n.replace(",", ""))
        except ValueError:
            continue
        if mult == 1000 and v < 1000:
            v *= 1000
        elif mult in (2080, 12):
            v *= mult
        vals.append(v)
    if not vals:
        return None, None
    if mult is None and max(vals) < 10000:
        return None, None  # ambiguous (hourly? monthly?) — don't guess
    return (min(vals), max(vals)) if len(vals) > 1 else (vals[0], vals[0])


def fetch_yc_jobs() -> list[dict]:
    """YC jobs via the public Algolia company index + workatastartup pages. No auth."""
    import time
    jobs = []
    try:
        res = _yc_algolia({
            "query": "", "hitsPerPage": "1000", "attributesToHighlight": "[]",
            "attributesToRetrieve": json.dumps(
                ["name", "slug", "one_liner", "tags", "industries", "regions"]),
            "facetFilters": json.dumps(["isHiring:true", "regions:Remote"]),
        })
    except Exception:
        return []
    companies = []
    for h in res.get("hits", []):
        blob = " ".join([h.get("name") or "", h.get("one_liner") or "",
                         " ".join(h.get("tags") or []),
                         " ".join(h.get("industries") or [])])
        if _YC_CO_RE.search(blob):
            companies.append(h)
    companies.sort(key=lambda h: h.get("name") or "")
    for h in companies[:_YC_MAX_COMPANIES]:
        slug = h.get("slug")
        if not slug:
            continue
        try:
            page = _yc_data_page(f"https://www.workatastartup.com/companies/{slug}")
            co = ((page or {}).get("props") or {}).get("company") or {}
        except Exception:
            time.sleep(0.3)
            continue
        time.sleep(0.3)
        for j in co.get("jobs") or []:
            title = (j.get("title") or "").strip()
            if not title or not _YC_TITLE_RE.search(title):
                continue
            loc = j.get("location") or ""
            is_remote = bool(re.search(r"\bremote\b", loc, re.I))
            desc_parts, visa = [], (j.get("sponsorsVisa") or "")
            exp = j.get("minExperience") or ""
            job_url = f"https://www.workatastartup.com/jobs/{j.get('id')}"
            apply_url, detail = job_url, None
            try:
                detail = _yc_data_page(job_url)
            except Exception:
                detail = None
            time.sleep(0.3)
            if detail:
                props = detail.get("props") or {}
                dj = props.get("job") or {}
                desc_parts.append(_strip_html(dj.get("descriptionHtml") or ""))
                visa = dj.get("sponsorsVisa") or visa
                skills = dj.get("skills") or []
                if skills:
                    desc_parts.append("Skills: " + ", ".join(skills))
                apply_url = props.get("applyUrl") or job_url
            if visa:
                desc_parts.append(f"Visa/sponsorship: {visa}")
            if exp:
                desc_parts.append(f"Experience: {exp}")
            smin, smax = _yc_salary(j.get("salaryRange") or "")
            jobs.append({
                "source": "yc_jobs",
                "id": f"yc-{j.get('id')}",
                "title": title,
                "company": (h.get("name") or "").strip(),
                "description": "\n".join(p for p in desc_parts if p)[:6000],
                "url": job_url,
                "apply_url": apply_url,
                "apply_email": None,
                "location": "Remote" if is_remote else loc,
                "remote": is_remote,
                "salary_min": smin, "salary_max": smax,
                "salary_unit": "yearly",
                "posted_at": None,
                "tags": [t for t in [h.get("batch")] + (h.get("industries") or []) if t],
            })
    return jobs


# ---------------------------------------------------------------- Reddit r/forhire
# reddit.com/.json is 403-blocked from datacenter networks, so this uses the
# Arctic Shift API (free Pushshift successor, no key): [HIRING] posts only.
def fetch_reddit_forhire() -> list[dict]:
    """r/forhire [HIRING] posts via the Arctic Shift API. No key."""
    from datetime import timedelta
    jobs = []
    try:
        url = ("https://arctic-shift.photon-reddit.com/api/posts/search"
               "?subreddit=forhire&limit=100&sort=desc")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (job-scraper)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    for p in data.get("data", []):
        title = p.get("title") or ""
        if not re.search(r"\[hiring\]", title, re.I):
            continue
        body = p.get("selftext") or ""
        text = f"{title}\n{body}"
        if not _YC_TITLE_RE.search(text):
            continue
        if not re.search(r"\bremote\b|\bworldwide\b", text, re.I):
            continue
        created = _parse_dt(p.get("created_utc"))
        if created and created < cutoff:
            continue
        m = re.search(r"(?:@|at|for)\s+([A-Z][\w&.'-]{1,40}(?:\s+[A-Z][\w&.'-]{1,40}){0,3})", title)
        company = m.group(1).strip() if m else "r/forhire"
        emails = _emails(body)
        jobs.append({
            "source": "reddit_forhire",
            "id": f"rd-{p.get('id')}",
            "title": re.sub(r"^\[hiring\]\s*", "", title, flags=re.I).strip()[:200],
            "company": company,
            "description": (body or title)[:6000],
            "url": "https://www.reddit.com" + (p.get("permalink") or ""),
            "apply_url": "https://www.reddit.com" + (p.get("permalink") or ""),
            "apply_email": emails[0] if emails else None,
            "location": "Remote",
            "remote": True,
            "salary_min": None, "salary_max": None,
            "salary_unit": "yearly",
            "posted_at": created,
            "tags": ["reddit", "forhire"],
        })
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
    "yc_jobs": fetch_yc_jobs,
    "reddit_forhire": fetch_reddit_forhire,
}
