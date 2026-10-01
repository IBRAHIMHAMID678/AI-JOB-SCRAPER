"""Universal job-page engine: scrape jobs from ANY website or portal.

Two strategies, tried in order:
1. ATS auto-detection — most company career pages run on Greenhouse, Lever,
   Ashby, SmartRecruiters or Recruitee, each with a free public JSON API.
2. Generic page scrape — extract schema.org JobPosting JSON-LD blocks plus
   mailto: links from any HTML page (works on many job boards and portals).

Usage: fetch_targets([url, ...]) -> list[normalized job dict]
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from sources import _emails, _get, _parse_dt, _strip_html


# ---------------------------------------------------------------- ATS

def _slug_from_url(url: str) -> str:
    parts = [p for p in urlparse(url).path.strip("/").split("/") if p]
    return parts[-1] if parts else ""


def detect_ats(url: str):
    """Return (ats_name, board_slug) or None."""
    host = urlparse(url).netloc.lower()
    if "greenhouse.io" in host:
        return "greenhouse", _slug_from_url(url)
    if "lever.co" in host:
        return "lever", _slug_from_url(url)
    if "ashbyhq.com" in host:
        return "ashby", _slug_from_url(url)
    if "smartrecruiters.com" in host:
        return "smartrecruiters", _slug_from_url(url)
    if host.endswith(".recruitee.com"):
        return "recruitee", host.split(".")[0]
    return None


def _company_from_slug(slug: str) -> str:
    return re.sub(r"[-_]+", " ", slug).strip().title()


def fetch_greenhouse(slug: str) -> list[dict]:
    raw = json.loads(_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"))
    comp = _company_from_slug(slug)
    jobs = []
    for j in raw.get("jobs", []):
        desc = _strip_html(j.get("content") or "")
        loc = (j.get("location") or {}).get("name", "") if isinstance(j.get("location"), dict) else ""
        emails = _emails(desc)
        jobs.append({
            "source": "ats:greenhouse", "id": f"gh-{slug}-{j.get('id')}",
            "title": j.get("title") or "", "company": comp,
            "description": desc, "url": j.get("absolute_url") or "",
            "apply_url": j.get("absolute_url") or "",
            "apply_email": emails[0] if emails else None,
            "location": loc, "remote": bool(re.search(r"\bremote\b", loc, re.I)),
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(j.get("updated_at") or j.get("created_at")),
            "tags": [t.get("name", "") for t in (j.get("metadata") or []) if isinstance(t, dict)][:6],
        })
    return jobs


def fetch_lever(slug: str) -> list[dict]:
    raw = json.loads(_get(f"https://api.lever.co/v0/postings/{slug}?mode=json"))
    comp = _company_from_slug(slug)
    jobs = []
    for j in raw if isinstance(raw, list) else []:
        desc = _strip_html(j.get("description") or "")
        cats = j.get("categories") or {}
        loc = cats.get("location") or ""
        emails = _emails(desc)
        jobs.append({
            "source": "ats:lever", "id": f"lv-{slug}-{j.get('id')}",
            "title": j.get("text") or "", "company": comp,
            "description": desc, "url": j.get("hostedUrl") or "",
            "apply_url": j.get("applyUrl") or j.get("hostedUrl") or "",
            "apply_email": emails[0] if emails else None,
            "location": loc, "remote": bool(re.search(r"\bremote\b", loc, re.I)),
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(j.get("createdAt")),
            "tags": [cats.get("team") or "", cats.get("commitment") or ""],
        })
    return jobs


def fetch_ashby(slug: str) -> list[dict]:
    raw = json.loads(_get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}"))
    comp = (raw.get("organizationName") or _company_from_slug(slug)).strip()
    jobs = []
    for j in raw.get("jobs", []):
        desc = _strip_html(j.get("descriptionHtml") or j.get("descriptionPlain") or "")
        loc = j.get("locationName") or ""
        emails = _emails(desc)
        jobs.append({
            "source": "ats:ashby", "id": f"as-{slug}-{j.get('id')}",
            "title": j.get("title") or "", "company": comp,
            "description": desc, "url": j.get("jobUrl") or "",
            "apply_url": j.get("jobUrl") or "",
            "apply_email": emails[0] if emails else None,
            "location": loc, "remote": bool(j.get("isRemote") or re.search(r"\bremote\b", loc, re.I)),
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(j.get("publishedAt")),
            "tags": [j.get("departmentName") or ""],
        })
    return jobs


def fetch_smartrecruiters(slug: str) -> list[dict]:
    raw = json.loads(_get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"))
    comp = (raw.get("name") or _company_from_slug(slug)).strip() if isinstance(raw, dict) else _company_from_slug(slug)
    jobs = []
    for j in (raw.get("content") if isinstance(raw, dict) else []) or []:
        loc = j.get("location") or {}
        loc_s = ", ".join(x for x in [loc.get("city"), loc.get("country")] if x)
        jobs.append({
            "source": "ats:smartrecruiters", "id": f"sr-{slug}-{j.get('id')}",
            "title": j.get("name") or "", "company": comp,
            "description": "", "url": (j.get("ref") or ""),
            "apply_url": (j.get("applyUrl") or j.get("ref") or ""),
            "apply_email": None, "location": loc_s,
            "remote": bool(re.search(r"\bremote\b", loc_s, re.I)),
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(j.get("releasedDate")),
            "tags": [],
        })
    return jobs


def fetch_recruitee(slug: str) -> list[dict]:
    raw = json.loads(_get(f"https://{slug}.recruitee.com/api/offers/"))
    comp = _company_from_slug(slug)
    offers = raw.get("offers") if isinstance(raw, dict) else raw
    jobs = []
    for j in offers or []:
        loc = ", ".join(x for x in [j.get("city"), j.get("country_code")] if x)
        url = j.get("careers_url") or j.get("url") or ""
        jobs.append({
            "source": "ats:recruitee", "id": f"rc-{slug}-{j.get('id')}",
            "title": j.get("title") or "", "company": comp,
            "description": _strip_html(j.get("description") or ""),
            "url": url, "apply_url": url, "apply_email": None,
            "location": loc, "remote": bool(j.get("remote") or re.search(r"\bremote\b", loc, re.I)),
            "salary_min": None, "salary_max": None, "salary_unit": None,
            "posted_at": _parse_dt(j.get("created_at")),
            "tags": [j.get("category") or ""],
        })
    return jobs


_ATS_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "recruitee": fetch_recruitee,
}


# ------------------------------------------------------- generic page

_LDJSON_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                        re.I | re.S)
_MAILTO_RE = re.compile(r'href=["\']mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', re.I)


def _iter_jobpostings(data):
    if isinstance(data, dict):
        if "@graph" in data:
            yield from _iter_jobpostings(data["@graph"])
        elif data.get("@type") == "JobPosting":
            yield data
        return
    if isinstance(data, list):
        for item in data:
            yield from _iter_jobpostings(item)


def _loc_to_str(loc) -> str:
    if not loc:
        return ""
    if isinstance(loc, str):
        return loc
    if isinstance(loc, dict):
        addr = loc.get("address") or {}
        if isinstance(addr, dict):
            return ", ".join(x for x in [addr.get("addressLocality"), addr.get("addressRegion"),
                                         addr.get("addressCountry")] if x)
        return str(addr)
    if isinstance(loc, list):
        return ", ".join(_loc_to_str(x) for x in loc)
    return ""


def fetch_generic_page(url: str) -> list[dict]:
    """Extract schema.org JobPosting JSON-LD from any page."""
    html = _get(url)
    host = urlparse(url).netloc
    mailtos = _MAILTO_RE.findall(html)
    jobs = []
    for m in _LDJSON_RE.finditer(html):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        for jp in _iter_jobpostings(data):
            title = jp.get("title") or jp.get("name") or ""
            if not title:
                continue
            org = jp.get("hiringOrganization") or {}
            comp = org.get("name") if isinstance(org, dict) else str(org)
            desc = _strip_html(jp.get("description") or "")
            loc = _loc_to_str(jp.get("jobLocation"))
            emails = _emails(desc) or ([mailtos[0]] if mailtos else [])
            jobs.append({
                "source": "generic", "id": f"gen-{abs(hash(str(jp.get('url') or title + comp)))}",
                "title": title, "company": (comp or host).strip(),
                "description": desc, "url": jp.get("url") or url,
                "apply_url": jp.get("url") or url,
                "apply_email": emails[0] if emails else None,
                "location": loc, "remote": bool(re.search(r"\bremote\b", f"{title} {loc} {desc[:500]}", re.I)),
                "salary_min": None, "salary_max": None, "salary_unit": None,
                "posted_at": _parse_dt(jp.get("datePosted")),
                "tags": [],
            })
    return jobs


# ------------------------------------------------------------ dispatch

def fetch_list_page(list_url: str, link_re: str, max_items: int = 25) -> list[dict]:
    """Scrape a listing page: harvest detail links, then JSON-LD each one."""
    html = _get(list_url)
    links = []
    for m in re.finditer(r'href=["\'](' + link_re + r')["\']', html):
        u = m.group(1)
        if u.startswith("/"):
            u = f"{urlparse(list_url).scheme}://{urlparse(list_url).netloc}{u}"
        if u not in links:
            links.append(u)
    jobs = []
    for u in links[:max_items]:
        try:
            jobs.extend(fetch_generic_page(u))
        except Exception:
            continue
    return jobs


def fetch_target(url: str) -> tuple[str, list[dict]]:
    """Scrape one arbitrary URL. Returns (method, jobs)."""
    hit = detect_ats(url)
    if hit:
        ats, slug = hit
        try:
            return f"ats:{ats}", _ATS_FETCHERS[ats](slug)
        except Exception:
            pass  # fall through to generic page scrape
    try:
        jobs = fetch_generic_page(url)
        return "generic", jobs
    except Exception as e:
        return "error", []


def fetch_targets(urls: list[str]) -> list[dict]:
    jobs = []
    for url in urls:
        method, batch = fetch_target(url.strip())
        print(f"  target [{method}] {url.strip()[:70]}: {len(batch)} raw", flush=True)
        jobs.extend(batch)
    return jobs
