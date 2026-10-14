"""Additional job-board source plugins (added 2026-10-14).

Each exposes fetch_<name>() -> list[normalized job dict], matching the shape in
~/workspace/job_hunt/auto-scraper/sources.py:

  {"source","id","title","company","description","url","apply_url","apply_email",
   "location","remote","salary_min","salary_max","salary_unit","posted_at","tags"}

Self-contained (does not import sources.py). Every fetcher handles failures
gracefully and returns [] on error — never crashes the run.

DROPPED CANDIDATES (probed 2026-10-14, VM-tested, stdlib-only):
- rozee.pk / mustakbil.com: Angular SPAs, no public RSS/feed/API discovered.
- brightspyre: no public API; application requires an account.
- paperpk.com: 403 bot wall on feed endpoints.
- jang.com.pk: homepage only, no structured job feed.
- trulyremote.co RSS: blog feed only (no job items).
- curaiz.com: 403 on API/RSS (JS-rendered cards, needs live browser).
- authenticjobs.com: /rss and /jobs/feed are blog feeds; no public jobs API.
- jobspresso.co/feed: valid RSS, 0 job items.
- career_vault.io/api/jobs: works but all listings stale (latest 2026-07-30).
- indiehackers.com: 403. betalist.com: 403. web3.career: 403. cryptocurrencyjobs.co: 403.
- simplify.jobs / underdog.io / stillhiring.today / remote_rocketship.com: no public API.
- jobgether.com: no public API. skipthedrive.com: no feed. nodesk.co: 403.
- remotehub.com: connection refused. remote.co: timeouts. flexjobs.com: paywall/timeout.
- virtualvocations.com: paywall. dynamitejobs.com: no API/RSS (React SPA).
- startup.jobs: no RSS. cord / otta: auth or JS-only. producthunt: OAuth required.
- role_rasta: signup + paid pass (per job-boards.md notes).
- glassdoor via jobspy: "Glassdoor is not available for PAKISTAN".
- euremotejobs / gun.io / smashingmagazine RSS: blog feeds, no job items.
- wwr category RSS / himalayas RSS: subsets of already-covered sources (wwr, himalayas).
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone

_UA = "Mozilla/5.0 (job-scraper)"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_GENERIC_DOMAINS = {"example.com", "email.com", "domain.com"}


def _emails(text):
    out = []
    for e in EMAIL_RE.findall(text or ""):
        dom = e.split("@")[-1].lower()
        if dom not in _GENERIC_DOMAINS and e not in out:
            out.append(e)
    return out


def _stable_id(s) -> str:
    import hashlib
    return hashlib.md5(str(s or "").encode("utf-8")).hexdigest()[:16]


def _get(url: str, timeout: int = 25, headers: dict | None = None) -> str:
    hdrs = {"User-Agent": _UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
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
        if v > 10_000_000_000:
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
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(str(s))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


_PK_CITIES = ("islamabad", "rawalpindi", "lahore", "karachi", "peshawar",
              "faisalabad", "multan", "hyderabad", "quetta", "sialkot",
              "gujranwala", "abbottabad")


def _pk_location(text: str) -> tuple[str, bool]:
    """(location, remote) for Pakistan-portal job text."""
    tl = (text or "").lower()
    remote = bool(re.search(r"\bremote\b|work from home|\bwfh\b", tl))
    for city in _PK_CITIES:
        if city in tl:
            loc = city.capitalize() + ", Pakistan"
            return (loc + " (Remote)" if remote else loc), remote
    return ("Pakistan (Remote)" if remote else "Pakistan"), remote


def _company_from_title(title: str) -> tuple[str, str]:
    """Split 'Role required at Company' -> (role, company)."""
    t = (title or "").strip()
    m = re.search(r"\s+(?:required\s+)?at\s+([A-Z0-9][\w&.'\-() ]{1,60})\s*$", t)
    if m:
        return t[:m.start()].strip(), m.group(1).strip()
    m = re.search(r"\s+@\s+([A-Z0-9][\w&.'\-() ]{1,60})\s*$", t)
    if m:
        return t[:m.start()].strip(), m.group(1).strip()
    return t, ""


def _pkr_salary(text: str):
    """Parse 'salary/package upto 80K' or 'PKR 100,000' -> (min, max, 'monthly')."""
    tl = (text or "").lower()
    m = re.search(r"(?:salary|package|pay|stipend)[^\d₹$]{0,40}(\d[\d,]*)\s*k\b", tl)
    if m:
        try:
            v = int(m.group(1).replace(",", "")) * 1000
            return v, v, "monthly"
        except ValueError:
            pass
    m = re.search(r"(?:pkr|rs\.?|₨)[^\d]{0,10}(\d[\d,]{4,})", tl)
    if m:
        try:
            v = int(m.group(1).replace(",", ""))
            return v, v, "monthly"
        except ValueError:
            pass
    return None, None, None


def fetch_talenthubsol() -> list[dict]:
    """TalentHubSol (talenthubsol.com) — Pakistan job portal on WordPress.
    Jobs live in the `noo_job` post type exposed via WP REST (no auth).
    Mostly Lahore/Islamabad onsite + some remote. ~100 freshest postings."""
    jobs = []
    try:
        raw = json.loads(_get(
            "https://talenthubsol.com/wp-json/wp/v2/noo_job?per_page=100"))
    except Exception:
        return jobs
    for p in raw:
        try:
            title_raw = _strip_html((p.get("title") or {}).get("rendered") or "")
            if not title_raw:
                continue
            role, company = _company_from_title(title_raw)
            desc = _strip_html((p.get("content") or {}).get("rendered") or "")
            link = p.get("link") or ""
            location, remote = _pk_location(title_raw + " " + desc)
            smin, smax, sunit = _pkr_salary(desc)
            emails = _emails(desc)
            jobs.append({
                "source": "talenthubsol",
                "id": f"ths-{p.get('id')}",
                "title": role,
                "company": company,
                "description": desc[:4000],
                "url": link,
                "apply_url": link,
                "apply_email": emails[0] if emails else None,
                "location": location,
                "remote": remote,
                "salary_min": smin,
                "salary_max": smax,
                "salary_unit": sunit,
                "posted_at": _parse_dt(p.get("date")),
                "tags": ["talenthubsol", "pakistan"],
            })
        except Exception:
            continue
    return jobs


def fetch_indeed_pk() -> list[dict]:
    """Indeed Pakistan via jobspy (same pattern as the linkedin source).
    Flaky upstream (apis.indeed.com timeouts) — per-term try/except, [] on error."""
    jobs = []
    try:
        from jobspy import scrape_jobs
    except Exception:
        return jobs
    terms = ["AI Engineer", "Python Developer", "Full Stack Developer",
             "Machine Learning Engineer", "LLM Engineer"]
    for term in terms:
        try:
            df = scrape_jobs(site_name=["indeed"], search_term=term,
                             location="Pakistan", results_wanted=20,
                             hours_old=168, country_indeed="Pakistan")
        except Exception as e:
            print(f"  indeed_pk/{term}: {type(e).__name__}", flush=True)
            continue
        for _, r in df.iterrows():
            try:
                desc = str(r.get("description") or "")
                emails = _emails(desc)
                posted = r.get("date_posted")
                jobs.append({
                    "source": "indeed_pk",
                    "id": f"ipk-{r.get('id') or _stable_id(str(r.get('job_url')))}",
                    "title": str(r.get("title") or ""),
                    "company": str(r.get("company") or ""),
                    "description": desc,
                    "url": str(r.get("job_url") or ""),
                    "apply_url": str(r.get("job_url") or ""),
                    "apply_email": emails[0] if emails else None,
                    "location": str(r.get("location") or ""),
                    "remote": bool(re.search(r"\bremote\b",
                                            str(r.get("location") or "") + desc, re.I)),
                    "salary_min": None, "salary_max": None, "salary_unit": None,
                    "posted_at": _parse_dt(posted) if posted else None,
                    "tags": ["indeed", "pakistan"],
                })
            except Exception:
                continue
    return jobs


FETCHERS = {
    "talenthubsol": fetch_talenthubsol,
    "indeed_pk": fetch_indeed_pk,
}


if __name__ == "__main__":
    import sys
    names = sys.argv[1:] or list(FETCHERS)
    for name in names:
        fn = FETCHERS[name]
        try:
            rows = fn()
            print(f"{name}: {len(rows)} jobs")
            if rows:
                r = rows[0]
                print(f"  sample: {r['title']!r} @ {r['company']!r} | {r['location']!r} | {r['posted_at']}")
        except Exception as e:
            print(f"{name}: ERROR {type(e).__name__}: {e}")
