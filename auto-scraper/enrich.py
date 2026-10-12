"""Detail-page enrichment for We Are Distributed leads.

The WAD feed (feed.json) carries no descriptions or employer apply URLs —
just title/company/regions. The disqualifiers (US-only, Colombia-only,
3+ years, on-site abroad) live on the /job/{slug} detail page, which embeds
a JSON-LD JobPosting block with the full description and jobLocation.

enrich_wad_job() fetches that page for one job dict, fills in description
+ location, and returns True when it got usable text. run.py calls this for
WAD jobs that reach pass/review, then re-runs filter_job on the enriched
record so region/experience gates are caught before a lead reaches Ibrahim.
"""
import html
import json
import re
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
       "Referer": "https://wearedistributed.org/remote-jobs/pakistan"}

_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    s = _TAG_RE.sub(" ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def enrich_wad_job(job: dict) -> bool:
    """Fetch the WAD detail page and backfill description/location. In-place."""
    url = job.get("url") or ""
    if "/job/" not in url:
        return False
    try:
        page = _fetch(url)
    except Exception:
        return False

    desc_text, country = "", ""
    loc_requirements: list[str] = []
    for m in _JSONLD_RE.finditer(page):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        blocks = data if isinstance(data, list) else [data]
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("@type") == "JobPosting":
                raw_desc = b.get("description") or ""
                if raw_desc and len(str(raw_desc)) > len(desc_text):
                    desc_text = _strip_html(str(raw_desc))
                loc = b.get("jobLocation")
                locs = loc if isinstance(loc, list) else [loc]
                countries = []
                for l in locs:
                    addr = (l or {}).get("address") if isinstance(l, dict) else None
                    c = (addr or {}).get("addressCountry") if isinstance(addr, dict) else None
                    if c:
                        countries.append(str(c))
                if countries:
                    country = ", ".join(sorted(set(countries)))
                # structured hiring-region gate, e.g. [{"@type":"Country","name":"United States"}]
                alr = b.get("applicantLocationRequirements") or []
                alr = alr if isinstance(alr, list) else [alr]
                for r in alr:
                    name = (r or {}).get("name") if isinstance(r, dict) else None
                    if name:
                        loc_requirements.append(str(name))
                break
        if desc_text or loc_requirements:
            break

    # page-level fallback signals (meta/title often carry "Remote (USA)" etc.)
    if not loc_requirements:
        mt = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
        if mt:
            title_txt = _strip_html(mt.group(1))
            mm = re.search(r"\(([^)]*(?:USA|U\.S\.|United States|Europe|EMEA|APAC|Canada|UK)[^)]*)\)",
                           title_txt, re.I)
            if mm:
                loc_requirements.append(mm.group(1).strip())

    if loc_requirements:
        job["_loc_requirements"] = sorted(set(loc_requirements))
        req_txt = ", ".join(sorted(set(loc_requirements)))
        if req_txt.lower() not in (job.get("location") or "").lower():
            job["location"] = f"{job.get('location') or 'Remote'} [hiring: {req_txt}]"

    if not desc_text:
        # fallback: visible page text is better than nothing
        body = re.search(r"<main[^>]*>(.*?)</main>", page, re.S | re.I)
        txt = _strip_html(body.group(1) if body else page)
        if len(txt) > 500:
            desc_text = txt[:8000]

    if len(desc_text) < 200 and not loc_requirements:
        return False

    job["description"] = desc_text
    if country and country.lower() not in (job.get("location") or "").lower():
        # keep the feed's region label, append the employer's country signal
        job["location"] = f"{job.get('location') or 'Remote'} [{country}]"
    job["_enriched"] = True
    return True
