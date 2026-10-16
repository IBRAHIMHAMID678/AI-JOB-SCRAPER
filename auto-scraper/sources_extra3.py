"""Source plugins from the 2026-10-16 keyless-alternatives integration (user-authorized).

All endpoints verified live from this VM 2026-10-16: zero key, zero signup,
plain HTTPS GET (stdlib only). Every fetcher returns [] on any error.

Integrated lanes:
- workable_search   jobs.workable.com/api/v1/jobs (cross-employer, paginated)
- themuse           themuse.com/api/public/jobs (keyless, global tech)
- landing_jobs      landing.jobs/api/v1/jobs (EU tech board)
- getonbrd          getonbrd.com/api/v0/categories/programming/jobs (JSON:API)
- fourdayweek       4dayweek.io/api/jobs (worldwide remote)
- a16z_speedrun     speedrun-talent-network.com/api/v1/jobs (a16z startups)
- amazon_jobs       amazon.jobs/en/search.json (global, full JD in payload)
- getmanfred        getmanfred.com/api/v2/public/offers (EU tech, salaries)
- thehub            thehub.io/api/v2/jobsandfeatured (Nordic/EU; NO posted dates)
- rj_api            remote-jobs-api.tten.no (normalizer over WWR/RemoteOK/Remotive/HN)
- flowxtra          app.flowxtra.com/api/central/jobs (cross-tenant board)
- remotli           remotli.ch/api/jobs (Swiss remote)
- jobspresso_rss    jobspresso.co/?feed=job_feed (RSS)
- crypto_rss        cryptocurrencyjobs.co/index.xml (RSS)
- smartrecruiters   api.smartrecruiters.com/v1/companies/<slug>/postings
                    (per-company lane; currently deliveryhero verified live)
- justjoin          justjoin.it/api/candidate-api/offers (PL/EU tech)

Rejected after VM probe:
- nofluffjobs: 400 on search POST (payload shape unknown) -> unverified
- glints GraphQL: 400 -> unverified
- SEEK/Jobstreet chalice API: APAC-focused, complex auth -> skipped
- Per-tenant ATS batch (teamtailor/recruitee/pinpoint/breezy/comeet/gem/
  eightfold/rippling/bamboohr/icims/jobvite/workday/oracle-orc/phenom/sap-sf/
  avature): all need per-company tenant slugs; no tenant directory available.
  ats-scrapers 0.3.0 (already installed) covers the common ones.
- nodesk RSS: digest newsletter format, low per-job value -> skipped
- Wellfound / TheirStack / Otta / Glassdoor / Google Jobs / Cord / hackajob /
  CV-Library / Totaljobs / DWP / Jobserve / Simplify / Honeypot: dead, keyed,
  or bot-walled (see keyless-alternatives report).

Cadence note: getmanfred (2.3MB single pull) and amazon_jobs (heavy) are
candidates for a 6h lane; everything else is light enough for the 2h sweep.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

_ROLE_SUB = [
    "ai engineer", "artificial intelligence", "ml engineer", "machine learning",
    "llm", "rag", "genai", "generative ai", "prompt", "nlp", "ai developer",
    "ai/ml", "python", "backend", "back-end", "full stack", "full-stack",
    "fullstack", "software engineer", "software developer", "data engineer",
    "data scientist", "chatbot", "conversational", "voice ai", "automation",
    "platform engineer", "frontend", "front-end", "devops",
]

_KEYWORDS = [
    "AI engineer", "machine learning engineer", "python developer",
    "full stack developer", "chatbot developer",
]


def _stable_id(s) -> str:
    import hashlib
    return hashlib.md5(str(s or "").encode("utf-8")).hexdigest()[:16]


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _get_text(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _parse_dt(v):
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            ts = v / 1000 if v > 1e12 else v
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        s = str(v).strip()
        if not s:
            return None
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _role_ok(title) -> bool:
    return any(s in (title or "").lower() for s in _ROLE_SUB)


def _job(source, jid, title, company, url, location=None, remote=False,
         desc=None, posted=None, salary_min=None, salary_max=None,
         salary_unit=None):
    return {
        "source": source, "id": jid, "title": title or "",
        "company": company or "", "description": (desc or "")[:4000],
        "url": url or "", "apply_url": url or "", "apply_email": None,
        "location": location or "", "remote": bool(remote),
        "salary_min": salary_min, "salary_max": salary_max,
        "salary_unit": salary_unit, "posted_at": posted, "tags": [],
    }


def _remote_of(*texts) -> bool:
    blob = " ".join(t or "" for t in texts)
    return bool(re.search(r"\bremote\b", blob, re.I))


# ---------------------------------------------------------------------------
# 1. Workable cross-employer search
# ---------------------------------------------------------------------------
def fetch_workable_search() -> list[dict]:
    jobs = []
    try:
        for kw in _KEYWORDS:
            token, pages = None, 0
            while pages < 2:
                q = urllib.parse.quote(kw)
                url = f"https://jobs.workable.com/api/v1/jobs?query={q}&limit=20"
                if token:
                    url += "&nextPageToken=" + urllib.parse.quote(token)
                data = _get_json(url)
                for j in data.get("jobs") or []:
                    title = j.get("title") or ""
                    if not _role_ok(title):
                        continue
                    u = j.get("url") or ""
                    m = re.search(r"https?://([a-z0-9-]+)\.workable\.com", u)
                    company = (m.group(1) if m else "")
                    loc = j.get("location") or {}
                    locs = j.get("locations") or []
                    loc_txt = " / ".join(
                        (x.get("city") or x.get("region") or "") if isinstance(x, dict) else str(x)
                        for x in locs)
                    jobs.append(_job(
                        "workable_search", f"wb-{j.get('id')}", title, company, u,
                        location=loc_txt or (loc.get("city") if isinstance(loc, dict) else ""),
                        remote=_remote_of(loc_txt, str(loc)),
                        desc=j.get("description") or j.get("socialSharingDescription") or "",
                        posted=_parse_dt(j.get("created"))))
                token = data.get("nextPageToken")
                pages += 1
                if not token:
                    break
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 2. The Muse
# ---------------------------------------------------------------------------
def fetch_themuse() -> list[dict]:
    jobs = []
    try:
        for page in range(4):
            data = _get_json(f"https://www.themuse.com/api/public/jobs?page={page}")
            for j in data.get("results") or []:
                title = j.get("name") or ""
                if not _role_ok(title):
                    continue
                co = j.get("company") or {}
                locs = " / ".join(x.get("name", "") for x in (j.get("locations") or []))
                jobs.append(_job(
                    "themuse", f"muse-{j.get('id')}", title,
                    co.get("name") if isinstance(co, dict) else "",
                    (j.get("refs") or {}).get("landing_page", ""),
                    location=locs, remote=_remote_of(locs),
                    desc=(j.get("contents") or "")[:4000],
                    posted=_parse_dt(j.get("publication_date"))))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 3. Landing.jobs
# ---------------------------------------------------------------------------
def fetch_landing_jobs() -> list[dict]:
    jobs = []
    try:
        for j in _get_json("https://landing.jobs/api/v1/jobs") or []:
            title = j.get("title") or ""
            if not _role_ok(title):
                continue
            locs = j.get("locations") or []
            loc_txt = ", ".join(x if isinstance(x, str) else str(x.get("name", ""))
                                for x in locs)
            cm = re.search(r"landing\.jobs/at/([a-z0-9-]+)/", j.get("url") or "")
            jobs.append(_job(
                "landing_jobs", f"lj-{j.get('id')}", title,
                cm.group(1) if cm else "",
                j.get("url") or "", location=loc_txt,
                remote=bool(j.get("remote")) or _remote_of(loc_txt),
                desc=(j.get("role_description") or "")[:4000],
                posted=_parse_dt(j.get("published_at")),
                salary_min=j.get("gross_salary_low"), salary_max=j.get("gross_salary_high")))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 4. GetOnBoard
# ---------------------------------------------------------------------------
def fetch_getonbrd() -> list[dict]:
    jobs = []
    try:
        data = _get_json("https://www.getonbrd.com/api/v0/categories/programming/jobs")
        for item in data.get("data") or []:
            a = item.get("attributes") or {}
            title = a.get("title") or ""
            if not _role_ok(title):
                continue
            loc_txt = a.get("remote_zone") or ""
            jobs.append(_job(
                "getonbrd", f"gob-{item.get('id')}", title, "",
                (item.get("links") or {}).get("public_url", ""),
                location=loc_txt,
                remote=bool(a.get("remote")) or _remote_of(loc_txt),
                desc=re.sub(r"<[^>]+>", " ", a.get("description") or "")[:4000],
                posted=_parse_dt(a.get("published_at")),
                salary_min=a.get("min_salary"), salary_max=a.get("max_salary")))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 5. 4dayweek.io
# ---------------------------------------------------------------------------
def fetch_fourdayweek() -> list[dict]:
    jobs = []
    try:
        for page in range(1, 5):
            data = _get_json(f"https://4dayweek.io/api/jobs?page={page}")
            for j in data.get("jobs") or []:
                if j.get("is_expired"):
                    continue
                title = j.get("title") or ""
                if not _role_ok(title):
                    continue
                locs = j.get("locations") or []
                loc_txt = ", ".join(x.get("country", "") for x in locs if isinstance(x, dict))
                jobs.append(_job(
                    "fourdayweek", f"4dw-{j.get('id')}", title,
                    j.get("company_name") or "",
                    f"https://4dayweek.io/job/{j.get('slug')}" if j.get("slug") else "",
                    location=loc_txt, remote=(j.get("work_arrangement") == "remote"),
                    desc="", posted=_parse_dt(j.get("posted"))))
            if not data.get("has_more"):
                break
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 6. a16z speedrun talent network
# ---------------------------------------------------------------------------
def fetch_a16z_speedrun() -> list[dict]:
    jobs = []
    try:
        # server-side `q`/`ai` params do not filter (verified 2026-10-16);
        # page through and filter client-side instead.
        for page in range(4):
            data = _get_json(
                "https://speedrun-talent-network.com/api/v1/jobs"
                f"?page={page}&page_size=50&sort=recent")
            for j in data.get("jobs") or []:
                title = j.get("title") or ""
                if not _role_ok(title):
                    continue
                co = j.get("company")
                co = co if isinstance(co, str) else (co or {}).get("name", "")
                jobs.append(_job(
                    "a16z_speedrun", f"a16z-{j.get('id')}", title, co,
                    j.get("url") or "", location=j.get("location") or "",
                    remote=bool(j.get("remote")) or _remote_of(j.get("workplace_type") or ""),
                    desc="", posted=None,
                    salary_min=j.get("comp_min"), salary_max=j.get("comp_max")))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 7. Amazon jobs
# ---------------------------------------------------------------------------
def fetch_amazon_jobs() -> list[dict]:
    jobs = []
    try:
        for kw in ["software development engineer", "machine learning engineer",
                   "solutions architect"]:
            q = urllib.parse.quote(kw)
            data = _get_json(
                "https://www.amazon.jobs/en/search.json"
                f"?base_query={q}&result_limit=50&sort=recent")
            for j in data.get("jobs") or []:
                title = j.get("title") or ""
                if not _role_ok(title):
                    continue
                jobs.append(_job(
                    "amazon_jobs", f"amz-{j.get('id_icims') or j.get('id')}", title,
                    j.get("company_name") or "Amazon",
                    "https://www.amazon.jobs" + (j.get("job_path") or ""),
                    location=j.get("location") or "",
                    remote=_remote_of(j.get("location") or ""),
                    desc=(j.get("description") or "")[:4000],
                    posted=_parse_dt(j.get("posted_date"))))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 8. getManfred (heavy single pull)
# ---------------------------------------------------------------------------
def fetch_getmanfred() -> list[dict]:
    jobs = []
    try:
        for o in _get_json("https://www.getmanfred.com/api/v2/public/offers?lang=EN") or []:
            if (o.get("status") or "").upper() != "ACTIVE":
                continue
            title = o.get("position") or ""
            if not _role_ok(title):
                continue
            co = o.get("company") or {}
            locs = o.get("locations") or []
            loc_txt = ", ".join(x if isinstance(x, str) else x.get("city", "")
                                for x in locs)
            jobs.append(_job(
                "getmanfred", f"man-{o.get('id')}", title,
                co.get("name") if isinstance(co, dict) else "",
                f"https://www.getmanfred.com/offers/{o.get('slug')}" if o.get("slug") else "",
                location=loc_txt,
                remote=(o.get("remotePercentage") or 0) >= 80 or _remote_of(loc_txt),
                desc=(o.get("highlights") or "")[:4000],
                posted=_parse_dt(o.get("updatedAt")),
                salary_min=o.get("salaryFrom"), salary_max=o.get("salaryTo"),
                salary_unit=o.get("currency")))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 9. The Hub (no posted dates -> posted_at None)
# ---------------------------------------------------------------------------
def fetch_thehub() -> list[dict]:
    jobs = []
    try:
        for page in range(3):
            data = _get_json(f"https://thehub.io/api/v2/jobsandfeatured?page={page}")
            docs = (data.get("jobs") or {}).get("docs") or []
            for j in docs:
                title = j.get("title") or ""
                if not _role_ok(title):
                    continue
                co = j.get("company") or {}
                jobs.append(_job(
                    "thehub", f"hub-{j.get('id')}", title,
                    co.get("name") if isinstance(co, dict) else "",
                    f"https://thehub.io/jobs/{j.get('key')}" if j.get("key") else "",
                    location="", remote=bool(j.get("isRemote")),
                    desc="", posted=None))
            if page >= (data.get("jobs") or {}).get("pages", 1) - 1:
                break
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 10. remote-jobs-api.tten.no
# ---------------------------------------------------------------------------
def fetch_rj_api() -> list[dict]:
    jobs = []
    try:
        data = _get_json("https://remote-jobs-api.tten.no/v1/jobs?limit=200")
        for j in data.get("jobs") or []:
            title = j.get("title") or ""
            if not _role_ok(title):
                continue
            jobs.append(_job(
                "rj_api", f"rja-{j.get('id')}", title, j.get("company") or "",
                j.get("url") or "", location=j.get("location") or "",
                remote=True, desc=" ".join(j.get("tags") or [])[:500],
                posted=_parse_dt(j.get("published")),
                salary_min=j.get("salary_min"), salary_max=j.get("salary_max")))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 11. Flowxtra
# ---------------------------------------------------------------------------
def fetch_flowxtra() -> list[dict]:
    jobs = []
    try:
        for page in range(1, 4):
            data = _get_json(f"https://app.flowxtra.com/api/central/jobs?page={page}")
            inner = (data.get("data") or {}).get("data") or []
            for j in inner:
                title = j.get("title") or ""
                if not _role_ok(title):
                    continue
                jobs.append(_job(
                    "flowxtra", f"fx-{j.get('id')}", title,
                    j.get("name_company") or "",
                    f"https://app.flowxtra.com/jobs/{j.get('has_id')}" if j.get("has_id") else "",
                    location=" / ".join(filter(None, [j.get("city"), j.get("country")])),
                    remote=_remote_of(j.get("workplace") or ""),
                    desc="", posted=_parse_dt(j.get("date_share")),
                    salary_min=j.get("min_salary"), salary_max=j.get("max_salary"),
                    salary_unit=j.get("currency")))
            if page >= ((data.get("data") or {}).get("last_page") or 1):
                break
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 12. Remotli
# ---------------------------------------------------------------------------
def fetch_remotli() -> list[dict]:
    jobs = []
    try:
        data = _get_json("https://remotli.ch/api/jobs?limit=100&remote=all")
        for item in data.get("jobs") or []:
            j = item.get("jobs") if isinstance(item, dict) else None
            if not isinstance(j, dict):
                continue
            title = j.get("title") or ""
            if not _role_ok(title):
                continue
            jobs.append(_job(
                "remotli", f"rml-{j.get('id')}", title, j.get("company") or "",
                f"https://remotli.ch/jobs/{j.get('id')}",
                location=" / ".join(j.get("allLocations") or [j.get("location") or ""]),
                remote=True,
                desc=re.sub(r"<[^>]+>", " ", j.get("description") or "")[:4000],
                posted=None,
                salary_min=j.get("salaryMin"), salary_max=j.get("salaryMax"),
                salary_unit=j.get("salaryCurrency")))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 13/14. RSS lanes
# ---------------------------------------------------------------------------
def _fetch_rss(name, url, prefix) -> list[dict]:
    jobs = []
    try:
        xml = _get_text(url)
        root = ET.fromstring(xml)
        for item in root.iter("item"):
            def txt(tag):
                el = item.find(tag)
                return (el.text or "").strip() if el is not None and el.text else ""
            title = txt("title")
            if not _role_ok(title):
                continue
            link = txt("link")
            desc = ""
            for ns_tag in ("{http://purl.org/rss/1.0/modules/content/}encoded",
                           "description"):
                el = item.find(ns_tag)
                if el is not None and el.text:
                    desc = re.sub(r"<[^>]+>", " ", el.text)[:4000]
                    break
            jobs.append(_job(
                name, f"{prefix}-{_stable_id(link or title)}", title, "",
                link, location="", remote=True, desc=desc,
                posted=_parse_dt(txt("pubDate"))))
    except Exception:
        return jobs
    return jobs


def fetch_jobspresso_rss() -> list[dict]:
    return _fetch_rss("jobspresso_rss", "https://jobspresso.co/?feed=job_feed", "jp")


def fetch_crypto_rss() -> list[dict]:
    return _fetch_rss("crypto_rss", "https://cryptocurrencyjobs.co/index.xml", "cj")


# ---------------------------------------------------------------------------
# 15. SmartRecruiters (per-company; deliveryhero verified live 2026-10-16)
# ---------------------------------------------------------------------------
_SR_SLUGS = ["deliveryhero"]


def fetch_smartrecruiters() -> list[dict]:
    jobs = []
    try:
        for slug in _SR_SLUGS:
            for kw in _KEYWORDS:
                q = urllib.parse.quote(kw)
                data = _get_json(
                    f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
                    f"?q={q}&limit=100")
                for j in (data.get("content") or []):
                    title = j.get("name") or ""
                    if not _role_ok(title):
                        continue
                    loc = j.get("location") or {}
                    jobs.append(_job(
                        "smartrecruiters", f"sr-{slug}-{j.get('id')}", title,
                        slug, j.get("ref") or "",
                        location=", ".join(filter(None, [
                            loc.get("city"), loc.get("country")])),
                        remote=_remote_of(loc.get("city") or "", loc.get("country") or ""),
                        desc="", posted=_parse_dt(j.get("releasedDate"))))
    except Exception:
        return jobs
    return jobs


# ---------------------------------------------------------------------------
# 16. JustJoin.it
# ---------------------------------------------------------------------------
def fetch_justjoin() -> list[dict]:
    jobs = []
    try:
        data = _get_json("https://justjoin.it/api/candidate-api/offers")
        for j in data.get("data") or []:
            title = j.get("title") or ""
            if not _role_ok(title):
                continue
            slug = j.get("slug") or ""
            jobs.append(_job(
                "justjoin", f"jj-{j.get('guid') or slug}", title, "",
                f"https://justjoin.it/offers/{slug}" if slug else "",
                location=" / ".join(filter(None, [j.get("city"),
                                                   "Remote" if j.get("workplaceType") == "remote" else ""])),
                remote=(j.get("workplaceType") == "remote"),
                desc="", posted=None))
    except Exception:
        return jobs
    return jobs


FETCHERS = {
    "workable_search": fetch_workable_search,
    "themuse": fetch_themuse,
    "landing_jobs": fetch_landing_jobs,
    "getonbrd": fetch_getonbrd,
    "fourdayweek": fetch_fourdayweek,
    "a16z_speedrun": fetch_a16z_speedrun,
    "amazon_jobs": fetch_amazon_jobs,
    "getmanfred": fetch_getmanfred,
    "thehub": fetch_thehub,
    "rj_api": fetch_rj_api,
    "flowxtra": fetch_flowxtra,
    "remotli": fetch_remotli,
    "jobspresso_rss": fetch_jobspresso_rss,
    "crypto_rss": fetch_crypto_rss,
    "smartrecruiters": fetch_smartrecruiters,
    "justjoin": fetch_justjoin,
}


if __name__ == "__main__":
    import sys
    names = sys.argv[1:] or list(FETCHERS)
    for name in names:
        fn = FETCHERS[name]
        try:
            rows = fn()
            print(f"{name}: {len(rows)} jobs", flush=True)
            if rows:
                r = rows[0]
                print(f"  sample: {r['title']!r} @ {r['company']!r} | {r['location']!r} | {r['posted_at']}")
        except Exception as e:
            print(f"{name}: ERROR {type(e).__name__}: {e}")
