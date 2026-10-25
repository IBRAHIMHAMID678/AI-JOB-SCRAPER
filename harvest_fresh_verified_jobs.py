import sys
sys.stdout.reconfigure(line_buffering=True)
import os
import json
import re
import time
import urllib.request
import urllib.error
import sqlite3
import concurrent.futures
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "auto-scraper"))

import sources
from matcha_ats_harvester import MatchaATSHarvester
from matcha_freshness import verify_24h_freshness, contains_dead_job_markers
from company_enricher import CompanyEnricher
from matcha_structurer import structure_job_object
from database import save_job_to_db

# 1. Build Exclusion Sets from DB and PDF
db_path = os.path.join(BASE_DIR, "jobpilot.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT title, company, application_url FROM jobs")
existing_jobs = c.fetchall()

c.execute("""
    SELECT j.title, j.company, j.application_url 
    FROM applications a 
    JOIN jobs j ON a.job_id = j.id
""")
applied_jobs = c.fetchall()
conn.close()

excluded_urls = set()
excluded_fingerprints = set()
excluded_companies = set()

for row in existing_jobs + applied_jobs:
    t = (row["title"] or "").lower().strip()
    co = (row["company"] or "").lower().strip()
    u = (row["application_url"] or "").strip().rstrip("/")
    if u:
        excluded_urls.add(u)
    if co:
        excluded_companies.add(co)
    if t and co:
        excluded_fingerprints.add(f"{co}:::{t}")

# Add the 40 leads from PDF Section 1 and key applied companies from Section 3
pdf_leads_companies = [
    "kwick high tech", "s&p global", "roblox", "nebius", "brandigo", "langchain",
    "arc client", "optum", "nedo pakistan", "deepgram", "lumaai", "sierra",
    "askable", "dpl", "hsbc", "concord ai", "geungjeong-isangsa", "nexterse",
    "h.h tech solutions", "sofnix", "python technologies", "contentstudio",
    "bls solutions", "skilldockhq", "sales technologies", "azky tech labs",
    "ccrupt", "insideout", "turing", "dissolve labs", "truetannage", "entropik",
    "serpapi", "canonical", "mistral", "roboflow", "cohere", "elevenlabs",
    "posthog", "vercel", "gitlab", "crossover", "binance", "remotebase", "devsinc",
    "10pearls", "tkxel", "creative chaos", "volga partners", "folo", "carecloud"
]
for comp in pdf_leads_companies:
    excluded_companies.add(comp)

# Target Role Regex
TARGET_ROLE_PATTERNS = [
    r"\bai\b", r"\bml\b", r"\bmachine learning\b", r"\bartificial intelligence\b",
    r"\bllm\b", r"\brag\b", r"\bgenai\b", r"\bgenerative ai\b", r"\bprompt\b",
    r"\bpython\b", r"\bfull[- ]?stack\b", r"\bbackend\b", r"\bsoftware engineer\b",
    r"\bsoftware developer\b", r"\bdeveloper\b", r"\bengineer\b", r"\bdata engineer\b",
    r"\bvibe coder\b", r"\bagent\b"
]

# Strict Senior Hard Exclusions
SENIOR_BLOCK_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bstaff\b", r"\bprincipal\b",
    r"\bdirector\b", r"\bvp\b", r"\bvice president\b", r"\bhead of\b",
    r"\barchitect\b", r"\bmanager\b", r"\bdistinguished\b", r"\bfellow\b",
    r"\biii\b", r"\biv\b", r"\bv\b"
]

# Excluded non-dev/stack mismatch patterns
NON_TARGET_BLOCKS = [
    r"\bqa\b", r"\bquality assurance\b", r"\bsdet\b", r"\btest automation\b",
    r"\bmanual tester\b", r"\.net\b", r"\bc#\b", r"\bwordpress\b", r"\bphp\b",
    r"\bsales\b", r"\bmarketing\b", r"\brecruiter\b", r"\baccount executive\b",
    r"\bbusiness develop\w*\b", r"\bcustomer success\b", r"\bcustomer support\b",
    r"\bsupport engineer\b", r"\btechnical support\b", r"\bhelpdesk\b",
    r"\brater\b", r"\bmodel rater\b", r"\bevaluator\b", r"\bvideo editor\b",
    r"\belearning\b", r"\bdistribution engineer\b", r"\bservice engineer\b",
    r"\bit support\b", r"\bdesarrollador\b", r"\bingeniero\b", r"\blíder técnico\b",
    r"\bcounsel\b", r"\blegal\b", r"\blawyer\b", r"\bcompliance\b"
]

# Experience: block >= 3 years
HIGH_EXP_PATTERNS = [
    r"(\d+)\s*\+\s*(?:years?|yrs?)",
    r"(?:minimum|at\s+least|requires?)\s*(\d+)\s*(?:years?|yrs?)",
    r"(\d+)\s*[-–]\s*\d+\s*(?:years?|yrs?)"
]

# Location patterns
TWIN_CITIES_PATTERNS = [
    r"\bislamabad\b", r"\brawalpindi\b", r"\bisb\b", r"\brwp\b"
]

RESTRICTED_LOCATIONS = [
    r"\b(us|usa|united states|u\.s\.|u\.s\.a\.)\b",
    r"remote\s*[\(\-\,\:\/]\s*(us|usa|united states)",
    r"(us|usa|united states)\s*[\(\-\,\:\/]\s*remote",
    r"\b(us|usa)\s+remote\b",
    r"\bremote\s+(us|usa)\b",
    r"\b(san\s+francisco|california|new\s+york|seattle|austin|chicago|los\s+angeles|boston|denver|atlanta|miami)\b",
    r"\b(ca|ny|tx|wa|il|ma|co|fl|va|ga|nc|pa|oh)\s*[,;]\s*(united states|usa|us)\b",
    r"[,;]\s*(california|new york|texas|washington)\b",
    r"\bunited states\s*-\s*\w+\b",
    r"\b(us|usa)\s+(citizens?|citizenship|residents?|residency)\b",
    r"\b(must\s+reside\s+in\s+the\s+us|must\s+be\s+located\s+in\s+the\s+us|located\s+in\s+the\s+us)\b",
    r"\b(us\s+work\s+authorization|authorized\s+to\s+work\s+in\s+the\s+us|w2\s+only)\b",
    r"\b(north\s+america\s+only|us/canada\s+only|eu\s+only|uk\s+only)\b",
    r"\b(germany|france|canada|australia|india)\s+only\b"
]

WORLDWIDE_PATTERNS = [
    r"\bworldwide\b", r"\banywhere\b", r"\bglobal remote\b",
    r"\bwork from anywhere\b", r"\bany country\b", r"\beverywhere\b",
    r"\bremote worldwide\b", r"\bfully distributed\b", r"\bhire anywhere\b",
    r"\ball countries\b", r"\bopen to anyone\b"
]

def is_target_role(title: str) -> bool:
    t = title.lower()
    for block in NON_TARGET_BLOCKS:
        if re.search(block, t):
            return False
    for sen in SENIOR_BLOCK_PATTERNS:
        if re.search(sen, t):
            return False
    return any(re.search(pat, t) for pat in TARGET_ROLE_PATTERNS)

def check_experience_is_junior(text: str) -> tuple[bool, str]:
    t = text.lower()
    for pat in HIGH_EXP_PATTERNS:
        matches = re.findall(pat, t)
        for m in matches:
            try:
                years = int(m) if isinstance(m, str) else int(m[0])
                if years >= 3:
                    return False, f"Requires {years}+ yrs experience"
            except Exception:
                pass
    return True, "Junior / Intermediate Friendly"

def classify_target_location(loc: str, desc: str) -> tuple[str, bool]:
    loc_clean = (loc or "Remote").lower()
    desc_clean = (desc or "").lower()

    # Twin cities check
    if any(re.search(pat, loc_clean) for pat in TWIN_CITIES_PATTERNS):
        return "Twin Cities (Islamabad/Rawalpindi)", True

    # Pakistan Remote check
    if "pakistan" in loc_clean:
        return "Pakistan Remote", True

    # Hard restrictions (US, single countries, non-worldwide)
    for r in RESTRICTED_LOCATIONS:
        if re.search(r, loc_clean) or re.search(r, desc_clean[:300]):
            return "US / Geographically Restricted", False

    # Explicit worldwide remote
    if any(re.search(w, loc_clean) or re.search(w, desc_clean) for w in WORLDWIDE_PATTERNS):
        return "Worldwide Remote (Global)", True

    # General Remote only if from pure remote feed without geofencing
    if loc_clean.strip() in ["remote", "work from home", "telecommute"]:
        return "Worldwide Remote (General)", True

    return "Non-Target Location", False

def verify_url_live(url: str, timeout: int = 10) -> tuple[bool, str]:
    if not url or not url.startswith("http"):
        return False, "Invalid URL"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if code in (200, 301, 302, 307, 308):
                body = resp.read(8192).decode("utf-8", errors="ignore").lower()
                dead_markers = [
                    "this job has expired", "position closed", "no longer accepting applications",
                    "job posting has ended", "job is no longer available", "page not found",
                    "404 not found", "this opening is closed"
                ]
                for dm in dead_markers:
                    if dm in body:
                        return False, f"Expired ({dm})"
                return True, "HTTP 200 Live"
            return False, f"HTTP {code}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # Cloudflare or Auth-gate (e.g. LinkedIn / Ashby direct page)
            return True, f"Live (HTTP {e.code} Protected)"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)[:50]

def main():
    print("=" * 60)
    print("Starting Fresh Job Discovery & Verification Sweep")
    print("=" * 60)

    # 1. Query Sources (Matcha Direct ATS 1st-party + Existing Target Sources)
    print("Harvesting real-time 1st-party ATS jobs (Greenhouse, Ashby, Lever, Rippling, Workable)...")
    ats_harvester = MatchaATSHarvester()
    enricher = CompanyEnricher()
    
    raw_candidates = []
    try:
        ats_jobs = ats_harvester.harvest_all(max_hours=24.0, only_fresh=True)
        print(f"  [Matcha ATS Harvester] Collected {len(ats_jobs)} live fresh ATS jobs!")
        for aj in ats_jobs:
            raw_candidates.append({
                "title": aj.get("title", "").strip(),
                "company": aj.get("company", "").strip(),
                "company_slug": aj.get("company_slug", ""),
                "url": aj.get("url") or aj.get("direct_career_url", "").strip(),
                "direct_career_url": aj.get("direct_career_url") or aj.get("url", "").strip(),
                "description": aj.get("description", "") or "",
                "location": aj.get("location", "Remote") or "Remote",
                "estimated_pay": aj.get("salary_raw") or "Not Disclosed",
                "source": aj.get("source", "ats_direct"),
                "posted_at": aj.get("date_posted") or "",
                "hours_old": aj.get("hours_old", 0.0),
                "is_24h_fresh": True
            })
    except Exception as e:
        print(f"  [Matcha ATS Harvester] Warning: {e}")

    target_sources = [
        "apnijobs", "talenthubsol", "indeed_pk",
        "remoteok", "remotive", "jobicy", "himalayas", "wwr", "yc_jobs",
        "workingnomads", "workable_search", "smartrecruiters", "justremote", "getonbrd"
    ]

    print(f"Querying {len(target_sources)} fallback and aggregator sources...")

    for src_name in target_sources:
        func = sources.SOURCES.get(src_name)
        if not func:
            continue
        try:
            batch = func()
            if batch:
                print(f"  [{src_name}] fetched {len(batch)} jobs")
                for j in batch:
                    raw_candidates.append({
                        "title": j.get("title", "").strip(),
                        "company": j.get("company", "").strip(),
                        "company_slug": j.get("company", "").lower().replace(" ", ""),
                        "url": j.get("url") or j.get("apply_url", "").strip(),
                        "direct_career_url": j.get("url") or j.get("apply_url", "").strip(),
                        "description": j.get("description", "") or "",
                        "location": j.get("location", "Remote") or "Remote",
                        "estimated_pay": f"{j.get('salary_min', '')} - {j.get('salary_max', '')}" if j.get("salary_min") else "Not Disclosed",
                        "source": src_name,
                        "posted_at": str(j.get("posted_at") or "")
                    })
        except Exception as e:
            print(f"  [{src_name}] failed: {e}")

    print(f"Total raw candidates gathered: {len(raw_candidates)}")

    # 2. Strict Filtering and Deduplication
    eligible_candidates = []
    seen_fp = set()

    for job in raw_candidates:
        title = job["title"]
        company = job["company"]
        url = job["url"].rstrip("/")
        desc = job["description"]
        loc = job["location"]

        if not title or not url or not url.startswith("http"):
            continue

        # Strict 24-Hour Freshness Gate (Drop stale/junk jobs with no or >24h date)
        post_time = job.get("posted_at")
        is_fresh, hrs_old, dt_obj, fresh_msg = verify_24h_freshness(post_time, max_hours=24.0)
        if not is_fresh:
            continue
        job["hours_old"] = hrs_old
        job["date_posted"] = dt_obj.isoformat() if dt_obj else str(post_time or "")
        job["is_24h_fresh"] = True

        # Check against exclusions
        co_low = company.lower()
        if any(exc in co_low for exc in excluded_companies):
            continue

        fp = f"{co_low}:::{title.lower()}"
        if fp in excluded_fingerprints or fp in seen_fp:
            continue
        seen_fp.add(fp)

        if url in excluded_urls:
            continue

        # Check role match
        if not is_target_role(title):
            continue

        # Check experience (<3 years)
        exp_ok, _ = check_experience_is_junior(f"{title} {desc}")
        if not exp_ok:
            continue

        # Check location
        category, is_loc_eligible = classify_target_location(loc, desc)
        if not is_loc_eligible:
            continue

        job["category"] = category

        # Matcha Enrichment & Structuring
        job = enricher.enrich_job(job)
        job = structure_job_object(job)

        # Match score
        score = 65
        t_low = title.lower()
        if any(k in t_low for k in ["ai", "python", "full stack", "backend", "ml", "rag"]):
            score += 20
        if any(k in t_low for k in ["junior", "entry", "associate", "intern", "fresher"]):
            score += 15
        if "Twin Cities" in category:
            score += 10
        job["match_score"] = min(score, 100)

        eligible_candidates.append(job)

    print(f"Eligible candidates passing strict 24h filters: {len(eligible_candidates)}")

    # 3. Live URL Verification in parallel
    print("Live verifying job URLs (eliminating dead links and expired postings)...")
    verified_jobs = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_job = {executor.submit(verify_url_live, job["url"]): job for job in eligible_candidates}
        for future in concurrent.futures.as_completed(future_to_job):
            job = future_to_job[future]
            try:
                is_live, msg = future.result()
                if is_live:
                    job["verification_status"] = msg
                    verified_jobs.append(job)
                else:
                    print(f"  [REJECTED DEAD/EXPIRED] {job['title']} at {job['company']} -> {msg}")
            except Exception as e:
                pass

    print(f"Live Verification Complete! Fully verified active jobs: {len(verified_jobs)}")

    # Sort: Twin cities first, then by match score
    def sort_fn(j):
        is_tc = 1 if "Twin Cities" in j["category"] else 0
        return (is_tc, j["match_score"])

    verified_jobs.sort(key=sort_fn, reverse=True)

    # 4. Save to sweeps
    sweeps_dir = os.path.join(BASE_DIR, "sweeps")
    os.makedirs(sweeps_dir, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")

    out_json = os.path.join(sweeps_dir, f"new_verified_jobs_{today_str}.json")
    out_latest_json = os.path.join(sweeps_dir, "fresh_verified_jobs_latest.json")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(verified_jobs, f, indent=2, default=str)
    with open(out_latest_json, "w", encoding="utf-8") as f:
        json.dump(verified_jobs, f, indent=2, default=str)

    # Markdown export
    out_md = os.path.join(sweeps_dir, f"new_verified_jobs_{today_str}.md")
    twin_cities = [j for j in verified_jobs if "Twin Cities" in j["category"]]
    pak_remote = [j for j in verified_jobs if "Pakistan Remote" in j["category"]]
    worldwide = [j for j in verified_jobs if "Worldwide" in j["category"]]

    lines = [
        f"# Verified Fresh Job Sweep — {today_str}\n",
        f"> Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"> Total Live Verified Jobs: **{len(verified_jobs)}**",
        f"> Local Twin Cities (Islamabad/Rawalpindi): **{len(twin_cities)}**",
        f"> Worldwide Remote (< 3 yrs / AI / Full Stack / Python): **{len(worldwide)}**",
        f"> Pakistan Remote: **{len(pak_remote)}**\n",
        "---\n",
        "## 1. Local Twin Cities Jobs (Islamabad & Rawalpindi)\n",
        "| Title | Company | Location | Source | Score | Verified Link |",
        "| :--- | :--- | :--- | :--- | :---: | :--- |"
    ]
    for j in twin_cities:
        lines.append(f"| **{j['title']}** | {j['company']} | {j['location']} | `{j['source']}` | **{j['match_score']}%** | [Apply Link]({j['url']}) |")

    lines.extend([
        "\n---\n",
        "## 2. Worldwide International Remote Jobs\n",
        "| Title | Company | Type / Source | Pay | Score | Verified Link |",
        "| :--- | :--- | :--- | :--- | :---: | :--- |"
    ])
    for j in worldwide:
        pay = j['estimated_pay'] if j['estimated_pay'] != "Not Disclosed" else "Market / Undisclosed"
        lines.append(f"| **{j['title']}** | {j['company']} | {j['category']} (`{j['source']}`) | {pay} | **{j['match_score']}%** | [Apply Link]({j['url']}) |")

    if pak_remote:
        lines.extend([
            "\n---\n",
            "## 3. Pakistan Remote Tech Roles\n",
            "| Title | Company | Location | Source | Score | Verified Link |",
            "| :--- | :--- | :--- | :--- | :---: | :--- |"
        ])
        for j in pak_remote:
            lines.append(f"| **{j['title']}** | {j['company']} | {j['location']} | `{j['source']}` | **{j['match_score']}%** | [Apply Link]({j['url']}) |")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # 5. Persist to Database (SQLite & MongoDB)
    print(f"Persisting {len(verified_jobs)} verified fresh jobs to database...")
    for vj in verified_jobs:
        try:
            save_job_to_db(vj)
        except Exception as db_err:
            pass

    print(f"Results successfully exported to {out_md} and saved to database.")
    print(f"Summary: {len(twin_cities)} Twin Cities, {len(worldwide)} Worldwide Remote, {len(pak_remote)} Pak Remote.")

if __name__ == "__main__":
    main()
